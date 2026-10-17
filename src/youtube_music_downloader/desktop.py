import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QSplitter,
    QStyle, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from youtube_music_downloader.legal_resources import LegalResources

STATUS = {'queued': '대기', 'analyzing': '분석 중', 'running': '진행 중',
          'paused': '일시정지', 'downloading': '다운로드 중', 'converting': 'MP3 변환 중',
          'completed': '완료', 'completed_with_errors': '일부 실패',
          'failed': '실패', 'canceled': '취소됨'}
TERMINAL = {'completed', 'completed_with_errors', 'failed', 'canceled'}


class OpenSourceLicensesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resources = LegalResources()
        self.setWindowTitle('오픈소스 라이선스')
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.resize(900, 620)
        self.setMinimumSize(540, 400)
        layout = QVBoxLayout(self)
        notice = QLabel(
            '이 앱은 GNU Lesser General Public License version 3 (LGPL-3.0)에 따라 '
            'PySide6와 Qt를 사용합니다. 프로젝트 자체 소스에는 MIT 라이선스가 적용되며, '
            '외부 구성요소에는 각자의 라이선스가 적용됩니다.'
        )
        notice.setObjectName('qt_license_notice')
        notice.setWordWrap(True)
        notice.setTextFormat(Qt.TextFormat.PlainText)
        notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                       Qt.TextInteractionFlag.TextSelectableByKeyboard)
        layout.addWidget(notice)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.files = QListWidget()
        self.files.setObjectName('legal_files')
        self.files.setAccessibleName('라이선스 파일')
        self.text = QPlainTextEdit()
        self.text.setObjectName('legal_text')
        self.text.setAccessibleName('라이선스 전문')
        self.text.setReadOnly(True)
        self.text.setTabChangesFocus(True)
        for title, widget in (('라이선스 파일(&F)', self.files), ('라이선스 전문(&T)', self.text)):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(title)
            label.setBuddy(widget)
            panel_layout.addWidget(label)
            panel_layout.addWidget(widget)
            splitter.addWidget(panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 600])
        layout.addWidget(splitter, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.files.currentTextChanged.connect(self.show_license)
        self.files.addItems(self.resources.names())
        for row in range(self.files.count()):
            item = self.files.item(row)
            item.setToolTip(item.text())
        self.files.setCurrentRow(0)
        self.files.setFocus()

    def show_license(self, name):
        self.text.setAccessibleDescription(name)
        self.text.setPlainText(self.resources.read(name))


class MainWindow(QMainWindow):
    def __init__(self, controller, settings=None):
        super().__init__()
        self.controller = controller
        self.settings = settings if settings is not None else QSettings('YTMDownloader', 'Desktop')
        self.job = None
        self.engine_ready = False
        self.request_busy = False
        self.closing = False
        self.allow_close = False
        self.licenses_dialog = None
        self.menuBar().setNativeMenuBar(True)
        help_menu = self.menuBar().addMenu('도움말(&H)')
        licenses_action = help_menu.addAction('오픈소스 라이선스(&L)')
        licenses_action.setMenuRole(QAction.MenuRole.NoRole)
        licenses_action.triggered.connect(self.show_licenses)
        self.close_timer = QTimer(self)
        self.close_timer.setSingleShot(True)
        self.close_timer.timeout.connect(self.close)
        self.setWindowTitle('YouTube Music Downloader')
        self.resize(1100, 760)
        self.setMinimumSize(880, 620)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)
        heading = QLabel('YouTube Music Downloader')
        heading.setObjectName('heading')
        layout.addWidget(heading)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.url = QLineEdit()
        self.url.setPlaceholderText('https://music.youtube.com/playlist?list=...')
        self.url.setText(self.settings.value('playlist_url', '', str))
        self.url.setClearButtonEnabled(True)
        self.start_button = self._button('다운로드 시작', QStyle.StandardPixmap.SP_MediaPlay, self.start_download)
        self.start_button.setObjectName('primary')
        form.addWidget(QLabel('재생목록'), 0, 0)
        form.addWidget(self.url, 0, 1, 1, 5)
        form.addWidget(self.start_button, 0, 6)
        default_dir = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation) or Path.home()) / 'YouTube Music')
        self.output = QLineEdit(self.settings.value('output_dir', default_dir, str))
        browse = self._button('', QStyle.StandardPixmap.SP_DirOpenIcon, self.choose_folder)
        browse.setToolTip('저장 폴더 선택')
        browse.setAccessibleName('저장 폴더 선택')
        form.addWidget(QLabel('저장 폴더'), 1, 0)
        form.addWidget(self.output, 1, 1, 1, 5)
        form.addWidget(browse, 1, 6)
        self.mode = QComboBox()
        self.mode.addItem('MP3 · 최대 (원본 기준, 최대 320kbps)', 'max')
        self.mode.addItem('MP3 · 192kbps', '192')
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.settings.value('output_mode', 'max'))))
        self.cookies = QComboBox()
        for label, value in [('자동 선택', 'auto'), ('Chrome', 'chrome'), ('Edge', 'edge'),
                             ('Firefox', 'firefox'), ('Brave', 'brave'), ('사용 안 함', None)]:
            self.cookies.addItem(label, value)
        self.cookies.setCurrentIndex(max(0, self.cookies.findData(self.settings.value('cookie_source', 'auto'))))
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 4)
        self.concurrency.setValue(self.settings.value('concurrency', 2, int))
        self.concurrency.setSuffix('개')
        form.addWidget(QLabel('출력 방식'), 2, 0)
        form.addWidget(self.mode, 2, 1)
        form.addWidget(QLabel('브라우저 쿠키'), 2, 2)
        form.addWidget(self.cookies, 2, 3)
        form.addWidget(QLabel('동시 다운로드'), 2, 4)
        form.addWidget(self.concurrency, 2, 5, 1, 2)
        form.setColumnStretch(1, 3)
        form.setColumnStretch(3, 1)
        layout.addLayout(form)
        self.message = QLabel('작업 엔진 준비 중...')
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)

        toolbar = QHBoxLayout()
        self.status = QLabel('작업 없음')
        self.status.setObjectName('status')
        toolbar.addWidget(self.status)
        toolbar.addStretch()
        self.pause_button = self._button('일시정지', QStyle.StandardPixmap.SP_MediaPause, self.toggle_pause)
        self.pause_button.setToolTip('진행 중인 곡은 마무리하고 다음 곡부터 대기합니다.')
        self.cancel_button = self._button('작업 취소', QStyle.StandardPixmap.SP_MediaStop, lambda: controller.send('cancel'))
        self.retry_button = self._button('실패 모두 재시도', QStyle.StandardPixmap.SP_BrowserReload, lambda: controller.send('retry_failed', cookie_source=self.cookies.currentData()))
        folder = self._button('', QStyle.StandardPixmap.SP_DirOpenIcon, self.open_folder)
        folder.setToolTip('저장 폴더 열기')
        folder.setAccessibleName('저장 폴더 열기')
        for button in (self.pause_button, self.cancel_button, self.retry_button, folder):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        layout.addWidget(self.progress)
        self.summary = QLabel('전체 0곡    완료 0    실패 0    취소 0')
        layout.addWidget(self.summary)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['#', '곡', '아티스트', '상태', '진행', 'MP3', ''])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for column, width in [(0, 40), (2, 140), (3, 120), (4, 70), (5, 85), (6, 50)]:
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self.show_details)
        layout.addWidget(self.table, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('선택한 곡의 저장 경로 또는 오류')
        self.details.setMaximumHeight(96)
        layout.addWidget(self.details)
        self.setStyleSheet('''
            QMainWindow { background: #f7f8fa; }
            QWidget { font-size: 13px; color: #24292f; }
            QLabel#heading { font-size: 23px; font-weight: 600; margin-bottom: 8px; }
            QLabel#status { font-weight: 600; }
            QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #cdd3da;
                border-radius: 4px; padding: 7px; min-height: 20px; }
            QPushButton { background: #ffffff; border: 1px solid #cdd3da; border-radius: 4px;
                padding: 7px 10px; min-height: 20px; }
            QPushButton:hover { background: #edf2f5; }
            QPushButton:disabled { color: #9ca3aa; background: #f1f3f5; }
            QPushButton#primary { background: #147d64; color: white; border-color: #147d64; }
            QPushButton#primary:disabled { background: #94b5ab; border-color: #94b5ab; }
            QTableWidget, QPlainTextEdit { background: white; alternate-background-color: #f6f8fa;
                border: 1px solid #d6dce2; border-radius: 4px; }
            QTableWidget::item { padding: 4px; }
            QTableWidget::item:selected { background: #dcefe9; color: #202a28; }
            QHeaderView::section { background: #eef1f4; padding: 8px; border: none;
                border-bottom: 1px solid #d6dce2; font-weight: 600; }
            QProgressBar { border: none; background: #e2e8ec; text-align: center; border-radius: 3px; }
            QProgressBar::chunk { background: #56b59b; border-radius: 3px; }
        ''')
        controller.snapshot.connect(self.render_job)
        controller.error.connect(self.show_error)
        controller.ready.connect(self.on_ready)
        controller.busy.connect(self.on_busy)
        controller.stopped.connect(self.on_stopped)
        self.update_controls()

    def _button(self, text, icon, callback):
        button = QPushButton(self.style().standardIcon(icon), text)
        button.clicked.connect(callback)
        return button

    def show_licenses(self):
        if self.licenses_dialog is None:
            self.licenses_dialog = OpenSourceLicensesDialog(self)
        self.licenses_dialog.show()
        self.licenses_dialog.raise_()
        self.licenses_dialog.activateWindow()

    def on_ready(self, ready):
        self.engine_ready = ready
        if ready and not self.job:
            self.message.setText('준비')
        self.update_controls()

    def on_busy(self, busy):
        self.request_busy = busy
        self.update_controls()

    def update_controls(self):
        status = self.job['status'] if self.job else None
        active = status is not None and status not in TERMINAL
        self.start_button.setEnabled(self.engine_ready and not active and not self.request_busy)
        self.pause_button.setEnabled(self.engine_ready and active)
        self.cancel_button.setEnabled(self.engine_ready and active)
        self.pause_button.setText('계속' if status == 'paused' else '일시정지')
        self.pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay if status == 'paused' else QStyle.StandardPixmap.SP_MediaPause))
        failed = self.job and (self.job['summary'].get('failed', 0) or status == 'failed')
        self.retry_button.setEnabled(bool(self.engine_ready and failed and status != 'canceled'))

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'MP3 저장 폴더', self.output.text())
        if folder:
            self.output.setText(folder)

    def open_folder(self):
        path = Path(self.job['output_dir'] if self.job else self.output.text()).expanduser()
        if not path.is_dir():
            self.show_error('저장 폴더가 아직 없습니다.')
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            self.show_error('저장 폴더를 열지 못했습니다.')

    def start_download(self):
        options = dict(playlist_url=self.url.text().strip(), output_dir=self.output.text().strip(),
                       output_mode=self.mode.currentData(), concurrency=self.concurrency.value(),
                       cookie_source=self.cookies.currentData())
        for key, value in options.items():
            self.settings.setValue(key, value)
        self.message.setStyleSheet('')
        self.message.setText('작업 준비 중...')
        self.controller.send('start', **options)

    def toggle_pause(self):
        self.controller.send('resume' if self.job and self.job['status'] == 'paused' else 'pause')

    def show_error(self, text):
        self.message.setStyleSheet('color: #b42332;')
        self.message.setText(text[:700])
        self.message.setToolTip(text)
        self.details.setPlainText(text)

    def render_job(self, job):
        self.job = job
        status = job['status']
        self.status.setText('작업 상태: ' + STATUS.get(status, status))
        counts = job['summary']
        total = counts['total']
        complete, failed, canceled = (counts.get(key, 0) for key in ('completed', 'failed', 'canceled'))
        self.summary.setText(f'전체 {total}곡    완료 {complete}    실패 {failed}    취소 {canceled}')
        if status in {'queued', 'analyzing'} and total == 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, max(1, total))
            self.progress.setValue(complete + failed + canceled)
        if job.get('error_message'):
            self.show_error(job['error_message'])
        else:
            self.message.setStyleSheet('')
            self.message.setText('진행 중인 곡을 마무리한 뒤 대기합니다.' if status == 'paused' else STATUS.get(status, status))
        self.table.setRowCount(len(job['tracks']))
        for row, track in enumerate(job['tracks']):
            bitrate = track.get('target_bitrate_kbps')
            values = [str(row + 1), track['title'], track.get('artist') or '',
                      STATUS.get(track['status'], track['status']), f"{track['progress']}%",
                      f'{bitrate}k' if bitrate else '']
            for column, value in enumerate(values):
                item = self.table.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(row, column, item)
                item.setText(value)
                item.setToolTip(track.get('error_message') or track.get('output_path') or value)
                item.setForeground(QColor('#b42332' if track['status'] == 'failed' else '#24292f'))
            retry = self.table.cellWidget(row, 6)
            if retry is None:
                retry = self._button('', QStyle.StandardPixmap.SP_BrowserReload,
                                     lambda checked=False, tid=track['id']: self.controller.send('retry', track_id=tid, cookie_source=self.cookies.currentData()))
                retry.setToolTip('이 곡 다시 시도')
                retry.setAccessibleName('이 곡 다시 시도')
                retry.setProperty('track_id', track['id'])
                self.table.setCellWidget(row, 6, retry)
            elif retry.property('track_id') != track['id']:
                retry.clicked.disconnect()
                retry.clicked.connect(lambda checked=False, tid=track['id']: self.controller.send('retry', track_id=tid, cookie_source=self.cookies.currentData()))
                retry.setProperty('track_id', track['id'])
            retry.setEnabled(track['status'] in {'failed', 'completed'} and status != 'canceled')
        self.show_details()
        self.update_controls()

    def show_details(self):
        row = self.table.currentRow()
        if self.job and 0 <= row < len(self.job['tracks']):
            track = self.job['tracks'][row]
            self.details.setPlainText(track.get('error_message') or track.get('output_path') or track['title'])

    def on_stopped(self):
        if self.closing:
            self.allow_close = True
            self.close_timer.start(0)

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
            return
        if not self.closing and self.job and self.job['status'] not in TERMINAL and self.isVisible():
            answer = QMessageBox.question(self, '앱 종료', '진행 중인 작업을 취소하고 종료할까요?',
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        event.ignore()
        self.closing = True
        self.setEnabled(False)
        self.controller.shutdown()


def main():
    from youtube_music_downloader.desktop_controller import DesktopController
    app = QApplication(sys.argv)
    app.setApplicationName('YouTube Music Downloader')
    app.setOrganizationName('YTMDownloader')
    controller = DesktopController()
    window = MainWindow(controller)
    window.show()
    return app.exec()
