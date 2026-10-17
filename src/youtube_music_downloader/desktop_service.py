"""Desktop commands run on one asyncio loop, separate from the GUI process."""
import asyncio
from dataclasses import asdict
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.models import JobStatus, TrackStatus

TERMINAL = {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS,
            JobStatus.FAILED, JobStatus.CANCELED}


class DesktopService:
    def __init__(self, manager: JobManager):
        self.manager = manager
        self.job = None
        self.tasks = set()
        self.analysis = None

    def snapshot(self):
        if self.job is None:
            return None
        result = asdict(self.job)
        result['output_dir'] = str(self.job.output_dir)
        result['summary'] = {'total': len(self.job.tracks)}
        for status in TrackStatus:
            result['summary'][status.value] = sum(t.status is status for t in self.job.tracks)
        return result

    def _schedule(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)

        def finished(done):
            self.tasks.discard(done)
            if not done.cancelled() and done.exception() is not None and self.job:
                self.job.status = JobStatus.FAILED
                self.job.error_message = str(done.exception())

        task.add_done_callback(finished)
        return task

    async def dispatch(self, command):
        action = command['action']
        if action == 'start':
            if self.job is not None and self.job.status not in TERMINAL:
                raise ValueError('진행 중인 작업을 완료하거나 취소해 주세요.')
            url = str(command.get('playlist_url', '')).strip()
            parsed = urlparse(url)
            if (parsed.scheme not in {'http', 'https'} or
                    parsed.hostname not in {'music.youtube.com', 'youtube.com', 'www.youtube.com', 'm.youtube.com'} or
                    parsed.path not in {'/playlist', '/watch'} or not parse_qs(parsed.query).get('list')):
                raise ValueError('YouTube Music 재생목록 URL을 입력해 주세요.')
            mode = OutputMode(command.get('output_mode', 'max'))
            concurrency = command.get('concurrency', 2)
            if type(concurrency) is not int or not 1 <= concurrency <= 4:
                raise ValueError('동시 다운로드 수는 1~4개여야 합니다.')
            cookie = self._cookie(command)
            raw_path = str(command.get('output_dir', '')).strip()
            if not raw_path:
                raise ValueError('저장 폴더를 선택해 주세요.')
            output = Path(raw_path).expanduser().resolve()
            output.mkdir(parents=True, exist_ok=True)
            # A single exclusive probe avoids tempfile retry loops on inaccessible drives.
            probe = output / f'.ymd-check-{uuid4().hex}'
            try:
                with probe.open('xb'):
                    pass
            finally:
                if probe.exists():
                    probe.unlink()
            self.manager.ensure_encoder_available()
            self.job = self.manager.create_job(url, output, mode, concurrency, cookie)
            self.analysis = self._schedule(self.manager.run_job(self.job.id))
        elif self.job is None:
            raise ValueError('먼저 다운로드를 시작해 주세요.')
        elif action == 'pause':
            self.manager.pause_job(self.job.id)
        elif action == 'resume':
            if self.analysis and not self.analysis.done() and not self.job.tracks:
                self.job.status = JobStatus.ANALYZING
            else:
                self.manager.resume_job(self.job.id)
            self._schedule(self._resume_after_analysis())
        elif action == 'cancel':
            self.manager.cancel_job(self.job.id)
            await self._cancel_tasks()
        elif action in {'retry', 'retry_failed'}:
            if self.job.status is JobStatus.CANCELED:
                raise ValueError('취소한 작업은 새 다운로드로 시작해 주세요.')
            cookie = self._cookie(command)
            if cookie != 'auto':
                self.manager.set_cookie_source(self.job.id, cookie)
            if not self.job.tracks and self.job.status is JobStatus.FAILED:
                self.job.cookie_source = cookie
                self.job.status = JobStatus.QUEUED
                self.analysis = self._schedule(self.manager.run_job(self.job.id))
            else:
                if action == 'retry':
                    self.manager.retry_track(self.job.id, command['track_id'])
                else:
                    self.manager.retry_failed(self.job.id)
                self._schedule(self.manager.run_pending(self.job.id))
        else:
            raise ValueError(f'지원하지 않는 작업: {action}')
        return self.snapshot()

    @staticmethod
    def _cookie(command):
        cookie = command.get('cookie_source', 'auto')
        if cookie not in {None, 'auto', 'chrome', 'edge', 'firefox', 'brave'}:
            raise ValueError('지원하지 않는 브라우저입니다.')
        return cookie

    async def _resume_after_analysis(self):
        if self.analysis and not self.analysis.done():
            await asyncio.shield(self.analysis)
        if self.job.status not in TERMINAL:
            await self.manager.run_pending(self.job.id)

    async def _cancel_tasks(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def wait_idle(self):
        while self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def shutdown(self):
        if self.job and self.job.status not in TERMINAL:
            self.manager.cancel_job(self.job.id)
        await self._cancel_tasks()
