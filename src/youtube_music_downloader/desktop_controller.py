import json
import sys
import time
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal
from youtube_music_downloader.desktop_runtime import worker_command


class DesktopController(QObject):
    snapshot = Signal(dict)
    error = Signal(str)
    ready = Signal(bool)
    busy = Signal(bool)
    stopped = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._read_errors)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.pending = {}
        self.buffer = b''
        self.diagnostics = ''
        self.is_ready = False
        self.closing = False
        self.started_at = time.monotonic()
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(500)
        self.watchdog.timeout.connect(self._check_timeout)
        self.watchdog.start()
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setSingleShot(True)
        self.shutdown_timer.timeout.connect(self._force_stop)
        QTimer.singleShot(0, self.start)

    def start(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.is_ready = False
        self.closing = False
        self.buffer = b''
        self.diagnostics = ''
        self.started_at = time.monotonic()
        self.watchdog.start()
        env = QProcessEnvironment.systemEnvironment()
        env.insert('PYTHONIOENCODING', 'utf-8')
        env.insert('PYTHONUNBUFFERED', '1')
        program, *arguments = worker_command('desktop-worker')
        if not getattr(sys, 'frozen', False):
            env.insert('PYTHONPATH', str(Path(__file__).resolve().parents[1]))
        self.process.setProcessEnvironment(env)
        self.process.start(program, arguments)

    def send(self, action, **options):
        if not self.is_ready:
            self.error.emit('작업 엔진을 준비 중입니다. 잠시 후 다시 시도해 주세요.')
            self.start()
            return
        request_id = uuid4().hex
        self.pending[request_id] = time.monotonic()
        self.busy.emit(True)
        self._write(dict(action=action, request_id=request_id, **options))

    def _write(self, command):
        self.process.write((json.dumps(command, ensure_ascii=True) + '\n').encode('utf-8'))

    def _read(self):
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                event = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            kind = event.get('type')
            if kind == 'ready':
                self.is_ready = True
                self.ready.emit(True)
            if kind in {'ack', 'error'}:
                self.pending.pop(event.get('request_id'), None)
                self.busy.emit(bool(self.pending))
            if kind in {'snapshot', 'ack'} and event.get('job'):
                self.snapshot.emit(event['job'])
            if kind == 'error':
                self.error.emit(event.get('message', '작업을 실행하지 못했습니다.'))

    def _read_errors(self):
        self.diagnostics = (self.diagnostics + bytes(self.process.readAllStandardError()).decode('utf-8', errors='replace'))[-8000:]

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.pending.clear()
            self.busy.emit(False)
            self.error.emit(f'작업 엔진을 실행하지 못했습니다: {self.process.errorString()}')
            self.ready.emit(False)

    def _finished(self, exit_code, status):
        self.shutdown_timer.stop()
        self.is_ready = False
        self.pending.clear()
        self.ready.emit(False)
        self.busy.emit(False)
        if not self.closing:
            detail = self.diagnostics.strip()[-1600:]
            self.error.emit(f'작업 엔진이 종료되었습니다. 앱을 다시 실행해 주세요.\n{detail}')
        self.stopped.emit()

    def _check_timeout(self):
        if self.closing or self.process.state() == QProcess.ProcessState.NotRunning:
            return
        now = time.monotonic()
        if ((not self.is_ready and now - self.started_at > 15) or
                any(now - started > 12 for started in self.pending.values())):
            self.error.emit('작업 엔진의 응답 시간이 초과되어 중단합니다. 저장 폴더와 접근 권한을 확인해 주세요.')
            self.shutdown()

    def shutdown(self):
        self.closing = True
        self.watchdog.stop()
        if self.process.state() == QProcess.ProcessState.NotRunning:
            self.stopped.emit()
            return
        self._write({'action': 'shutdown'})
        self.shutdown_timer.start(6000)

    def _force_stop(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
