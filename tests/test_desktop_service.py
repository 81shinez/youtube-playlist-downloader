import asyncio
from pathlib import Path

import pytest

from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.models import MediaTrack


class Downloader:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.stopped = asyncio.Event()

    async def playlist_tracks(self, url, cookie_source=None):
        return [MediaTrack('https://youtube.com/watch?v=a', 'A', None, 192)]

    async def download_audio(self, track, work_dir, progress, cookie_source=None):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.stopped.set()
            raise
        return work_dir / 'audio.wav'


class Encoder:
    async def encode_mp3(self, source, output, bitrate):
        return output


def service():
    from youtube_music_downloader.desktop_service import DesktopService
    downloader = Downloader()
    return DesktopService(JobManager(downloader, Encoder())), downloader


def payload(tmp_path):
    return dict(playlist_url='https://music.youtube.com/playlist?list=demo',
                output_dir=str(tmp_path), output_mode='192', concurrency=1,
                cookie_source=None)


@pytest.mark.asyncio
async def test_cancel_stops_active_work_and_preserves_canceled_snapshot(tmp_path):
    app, downloader = service()
    await app.dispatch({'action': 'start', **payload(tmp_path)})
    await asyncio.wait_for(downloader.started.wait(), 1)
    await app.dispatch({'action': 'cancel'})
    assert downloader.stopped.is_set()
    assert app.snapshot()['status'] == 'canceled'
    assert app.snapshot()['tracks'][0]['status'] == 'canceled'
    await app.shutdown()


@pytest.mark.asyncio
async def test_pause_resume_and_completion(tmp_path):
    app, downloader = service()
    await app.dispatch({'action': 'start', **payload(tmp_path)})
    await asyncio.wait_for(downloader.started.wait(), 1)
    await app.dispatch({'action': 'pause'})
    assert app.snapshot()['status'] == 'paused'
    await app.dispatch({'action': 'resume'})
    assert app.snapshot()['status'] == 'running'
    downloader.release.set()
    await app.wait_idle()
    assert app.snapshot()['status'] == 'completed'
    await app.shutdown()


@pytest.mark.asyncio
async def test_rejects_duplicate_active_job_and_invalid_url(tmp_path):
    app, downloader = service()
    with pytest.raises(ValueError, match='YouTube'):
        await app.dispatch({'action': 'start', **{**payload(tmp_path), 'playlist_url': 'https://example.com/'}})
    await app.dispatch({'action': 'start', **payload(tmp_path)})
    with pytest.raises(ValueError):
        await app.dispatch({'action': 'start', **payload(tmp_path)})
    await app.shutdown()


@pytest.mark.asyncio
async def test_pause_resume_during_analysis_does_not_complete_early(tmp_path):
    app, downloader = service()
    analyzing = asyncio.Event()
    finish_analysis = asyncio.Event()
    original = downloader.playlist_tracks

    async def delayed(url, cookie_source=None):
        analyzing.set()
        await finish_analysis.wait()
        return await original(url, cookie_source)

    downloader.playlist_tracks = delayed
    await app.dispatch({'action': 'start', **payload(tmp_path)})
    await asyncio.wait_for(analyzing.wait(), 1)
    await app.dispatch({'action': 'pause'})
    await app.dispatch({'action': 'resume'})
    await asyncio.sleep(0)
    assert app.snapshot()['status'] not in {'completed', 'failed'}
    finish_analysis.set()
    await asyncio.wait_for(downloader.started.wait(), 1)
    await app.shutdown()


@pytest.mark.asyncio
async def test_retry_failed_and_single_track_complete(tmp_path):
    app, downloader = service()
    downloader.release.set()
    original = downloader.download_audio

    async def fail(*args, **kwargs):
        raise RuntimeError('temporary failure')

    downloader.download_audio = fail
    await app.dispatch({'action': 'start', **payload(tmp_path)})
    await app.wait_idle()
    assert app.snapshot()['status'] == 'completed_with_errors'
    downloader.download_audio = original
    await app.dispatch({'action': 'retry_failed', 'cookie_source': None})
    await app.wait_idle()
    assert app.snapshot()['summary']['completed'] == 1
    track_id = app.snapshot()['tracks'][0]['id']
    await app.dispatch({'action': 'retry', 'track_id': track_id, 'cookie_source': None})
    await app.wait_idle()
    assert app.snapshot()['tracks'][0]['attempts'] == 3
    assert app.snapshot()['status'] == 'completed'
    await app.shutdown()
