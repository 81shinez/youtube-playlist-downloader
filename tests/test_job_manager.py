import asyncio
from pathlib import Path

import pytest

from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.models import JobStatus, MediaTrack, TrackStatus


class FakeDownloader:
    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        return [
            MediaTrack(
                source_url="https://music.youtube.com/watch?v=one",
                title="One",
                artist="Artist",
                source_bitrate_kbps=256,
            ),
            MediaTrack(
                source_url="https://music.youtube.com/watch?v=two",
                title="Two",
                artist="Artist",
                source_bitrate_kbps=192,
            ),
        ]

    async def download_audio(
        self,
        track: MediaTrack,
        work_dir: Path,
        progress,
        cookie_source: str | None = None,
    ):
        progress(50)
        return work_dir / f"{track.title}.webm"

    async def source_bitrate(self, source_url: str, cookie_source: str | None = None) -> int | None:
        return None


class FakeEncoder:
    def __init__(self):
        self.fail_titles: set[str] = set()

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        if source_path.stem in self.fail_titles:
            raise RuntimeError("conversion failed")
        output_path.write_text(f"mp3 {bitrate_kbps}", encoding="utf-8")
        return output_path


class MissingEncoder(FakeEncoder):
    def ensure_available(self) -> None:
        raise RuntimeError("ffmpeg executable is not available")


class BlockingDownloader(FakeDownloader):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.downloaded_titles: list[str] = []

    async def download_audio(
        self,
        track: MediaTrack,
        work_dir: Path,
        progress,
        cookie_source: str | None = None,
    ):
        self.downloaded_titles.append(track.title)
        self.started.set()
        if track.title == "One":
            await self.release.wait()
        progress(50)
        return work_dir / f"{track.title}.webm"


class RecordingEncoder(FakeEncoder):
    def __init__(self):
        super().__init__()
        self.encoded_titles: list[str] = []

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        self.encoded_titles.append(source_path.stem)
        return await super().encode_mp3(source_path, output_path, bitrate_kbps)


class ResolvingDownloader(FakeDownloader):
    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        return [MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", None)]

    async def source_bitrate(self, source_url: str, cookie_source: str | None = None) -> int | None:
        assert source_url == "https://music.youtube.com/watch?v=one"
        return 224


class CookieRecordingDownloader(FakeDownloader):
    def __init__(self):
        self.playlist_cookie_source: str | None = None
        self.bitrate_cookie_sources: list[str | None] = []
        self.download_cookie_sources: list[str | None] = []

    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        self.playlist_cookie_source = cookie_source
        return [MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", None)]

    async def source_bitrate(self, source_url: str, cookie_source: str | None = None) -> int | None:
        self.bitrate_cookie_sources.append(cookie_source)
        return 256

    async def download_audio(
        self,
        track: MediaTrack,
        work_dir: Path,
        progress,
        cookie_source: str | None = None,
    ):
        self.download_cookie_sources.append(cookie_source)
        progress(50)
        return work_dir / f"{track.title}.webm"


class AutoCookieFallbackDownloader(FakeDownloader):
    def __init__(self):
        self.playlist_cookie_sources: list[str | None] = []

    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        self.playlist_cookie_sources.append(cookie_source)
        if cookie_source == "chrome":
            raise RuntimeError("Could not copy Chrome cookie database")
        if cookie_source == "edge":
            return [MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192)]
        raise RuntimeError(f"unexpected cookie source {cookie_source}")


class CountingDownloader(FakeDownloader):
    def __init__(self):
        self.download_count = 0

    async def download_audio(
        self,
        track: MediaTrack,
        work_dir: Path,
        progress,
        cookie_source: str | None = None,
    ):
        self.download_count += 1
        await asyncio.sleep(0)
        progress(50)
        return work_dir / f"{track.title}.webm"


class BarrierEncoder(FakeEncoder):
    def __init__(self, expected_calls: int):
        super().__init__()
        self.expected_calls = expected_calls
        self.called = 0
        self.all_called = asyncio.Event()
        self.output_paths: list[Path] = []

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        self.called += 1
        self.output_paths.append(output_path)
        if self.called == self.expected_calls:
            self.all_called.set()
        await self.all_called.wait()
        output_path.write_text(f"mp3 {bitrate_kbps}", encoding="utf-8")
        return output_path


class CancelOnStrPath:
    def __init__(self, path: Path, cancel):
        self.path = path
        self.cancel = cancel

    def __str__(self) -> str:
        self.cancel()
        return str(self.path)


@pytest.mark.asyncio
async def test_create_job_processes_tracks_to_completion(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())

    job = manager.create_job(
        playlist_url="https://music.youtube.com/playlist?list=abc",
        output_dir=tmp_path,
        output_mode=OutputMode.MP3_MAX,
        concurrency=2,
    )
    await manager.run_job(job.id)

    saved = manager.get_job(job.id)
    assert saved.status is JobStatus.COMPLETED
    assert [track.status for track in saved.tracks] == [TrackStatus.COMPLETED, TrackStatus.COMPLETED]
    assert [track.target_bitrate_kbps for track in saved.tracks] == [256, 192]
    assert all(track.output_path and track.output_path.endswith(".mp3") for track in saved.tracks)


@pytest.mark.asyncio
async def test_max_mode_resolves_missing_bitrate_when_processing_track(tmp_path: Path):
    manager = JobManager(ResolvingDownloader(), FakeEncoder())

    job = manager.create_job(
        playlist_url="https://music.youtube.com/playlist?list=abc",
        output_dir=tmp_path,
        output_mode=OutputMode.MP3_MAX,
        concurrency=1,
    )
    await manager.run_job(job.id)

    track = manager.get_job(job.id).tracks[0]
    assert track.source_bitrate_kbps == 224
    assert track.target_bitrate_kbps == 224


@pytest.mark.asyncio
async def test_job_cookie_source_is_passed_to_all_yt_dlp_steps(tmp_path: Path):
    downloader = CookieRecordingDownloader()
    manager = JobManager(downloader, FakeEncoder())

    job = manager.create_job(
        playlist_url="https://music.youtube.com/playlist?list=abc",
        output_dir=tmp_path,
        output_mode=OutputMode.MP3_MAX,
        concurrency=1,
        cookie_source="chrome",
    )
    await manager.run_job(job.id)

    assert downloader.playlist_cookie_source == "chrome"
    assert downloader.bitrate_cookie_sources == ["chrome"]
    assert downloader.download_cookie_sources == ["chrome"]


@pytest.mark.asyncio
async def test_failed_track_does_not_stop_remaining_tracks(tmp_path: Path):
    encoder = FakeEncoder()
    encoder.fail_titles.add("One")
    manager = JobManager(FakeDownloader(), encoder)

    job = manager.create_job(
        playlist_url="https://music.youtube.com/playlist?list=abc",
        output_dir=tmp_path,
        output_mode=OutputMode.MP3_192,
        concurrency=1,
    )
    await manager.run_job(job.id)

    saved = manager.get_job(job.id)
    assert saved.status is JobStatus.COMPLETED_WITH_ERRORS
    assert saved.tracks[0].status is TrackStatus.FAILED
    assert saved.tracks[0].error_message == "conversion failed"
    assert saved.tracks[1].status is TrackStatus.COMPLETED


@pytest.mark.asyncio
async def test_retry_track_resets_failed_track_and_runs_again(tmp_path: Path):
    encoder = FakeEncoder()
    encoder.fail_titles.add("One")
    manager = JobManager(FakeDownloader(), encoder)

    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    await manager.run_job(job.id)
    failed_track_id = manager.get_job(job.id).tracks[0].id

    encoder.fail_titles.clear()
    manager.retry_track(job.id, failed_track_id)
    await manager.run_pending(job.id)

    track = manager.get_track(job.id, failed_track_id)
    assert track.status is TrackStatus.COMPLETED
    assert track.attempts == 2


@pytest.mark.asyncio
async def test_retry_failed_resets_all_failed_tracks(tmp_path: Path):
    encoder = FakeEncoder()
    encoder.fail_titles.update({"One", "Two"})
    manager = JobManager(FakeDownloader(), encoder)

    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    await manager.run_job(job.id)

    encoder.fail_titles.clear()
    reset_count = manager.retry_failed(job.id)
    await manager.run_pending(job.id)

    assert reset_count == 2
    assert [track.status for track in manager.get_job(job.id).tracks] == [TrackStatus.COMPLETED, TrackStatus.COMPLETED]


def test_cancel_queued_track_marks_it_canceled(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None))

    manager.cancel_track(job.id, track.id)

    assert manager.get_track(job.id, track.id).status is TrackStatus.CANCELED


@pytest.mark.asyncio
async def test_cancel_queued_track_captured_by_pending_skips_processing(tmp_path: Path):
    downloader = BlockingDownloader()
    manager = JobManager(downloader, FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    first = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192))
    second = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=two", "Two", "Artist", 192))

    run_task = asyncio.create_task(manager.run_pending(job.id))
    await downloader.started.wait()
    manager.cancel_track(job.id, second.id)
    downloader.release.set()
    await run_task

    assert manager.get_track(job.id, first.id).status is TrackStatus.COMPLETED
    assert manager.get_track(job.id, second.id).status is TrackStatus.CANCELED
    assert downloader.downloaded_titles == ["One"]


@pytest.mark.asyncio
async def test_cancel_running_track_stays_canceled_after_download_finishes(tmp_path: Path):
    downloader = BlockingDownloader()
    encoder = RecordingEncoder()
    manager = JobManager(downloader, encoder)
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192))

    run_task = asyncio.create_task(manager.run_pending(job.id))
    await downloader.started.wait()
    manager.cancel_track(job.id, track.id)
    downloader.release.set()
    await run_task

    saved = manager.get_track(job.id, track.id)
    assert saved.status is TrackStatus.CANCELED
    assert saved.output_path is None
    assert encoder.encoded_titles == []


@pytest.mark.asyncio
async def test_concurrent_run_pending_calls_do_not_process_same_track_twice(tmp_path: Path):
    downloader = CountingDownloader()
    manager = JobManager(downloader, FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 2)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192))

    await asyncio.gather(manager.run_pending(job.id), manager.run_pending(job.id))

    assert downloader.download_count == 1
    assert manager.get_track(job.id, track.id).attempts == 1


@pytest.mark.asyncio
async def test_parallel_duplicate_titles_get_distinct_output_paths(tmp_path: Path):
    class DuplicateDownloader(FakeDownloader):
        async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
            return [
                MediaTrack("https://music.youtube.com/watch?v=one", "Same", "Artist", 192),
                MediaTrack("https://music.youtube.com/watch?v=two", "Same", "Artist", 192),
            ]

    encoder = BarrierEncoder(expected_calls=2)
    manager = JobManager(DuplicateDownloader(), encoder)
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 2)

    await manager.run_job(job.id)

    assert len(set(encoder.output_paths)) == 2
    assert sorted(path.name for path in encoder.output_paths) == ["Artist - Same (2).mp3", "Artist - Same.mp3"]


@pytest.mark.asyncio
async def test_work_dir_creation_failure_marks_track_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192))
    original_mkdir = Path.mkdir

    def fail_work_dir_mkdir(self, *args, **kwargs):
        if self.name == ".ymd-work":
            raise OSError("cannot create work dir")
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_work_dir_mkdir)

    await manager.run_pending(job.id)

    saved = manager.get_track(job.id, track.id)
    assert saved.status is TrackStatus.FAILED
    assert saved.error_message == "cannot create work dir"
    assert manager.get_job(job.id).status is JobStatus.COMPLETED_WITH_ERRORS


@pytest.mark.asyncio
async def test_empty_playlist_completes_without_tracks(tmp_path: Path):
    class EmptyDownloader(FakeDownloader):
        async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
            return []

    manager = JobManager(EmptyDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)

    await manager.run_job(job.id)

    assert manager.get_job(job.id).status is JobStatus.COMPLETED
    assert manager.get_job(job.id).tracks == []


@pytest.mark.asyncio
async def test_run_job_fails_before_download_when_encoder_is_unavailable(tmp_path: Path):
    manager = JobManager(FakeDownloader(), MissingEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)

    await manager.run_job(job.id)

    saved = manager.get_job(job.id)
    assert saved.status is JobStatus.FAILED
    assert saved.error_message == "ffmpeg executable is not available"
    assert saved.tracks == []


@pytest.mark.asyncio
async def test_run_pending_fails_before_download_when_encoder_is_unavailable(tmp_path: Path):
    downloader = CountingDownloader()
    manager = JobManager(downloader, MissingEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", None, 192))

    await manager.run_pending(job.id)

    saved = manager.get_job(job.id)
    assert saved.status is JobStatus.FAILED
    assert saved.error_message == "ffmpeg executable is not available"
    assert manager.get_track(job.id, track.id).status is TrackStatus.QUEUED
    assert downloader.download_count == 0


@pytest.mark.asyncio
async def test_retry_completed_track_clears_stale_output_when_retry_fails(tmp_path: Path):
    encoder = FakeEncoder()
    manager = JobManager(FakeDownloader(), encoder)
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    await manager.run_job(job.id)
    track = manager.get_job(job.id).tracks[0]
    assert track.status is TrackStatus.COMPLETED
    assert track.output_path is not None

    encoder.fail_titles.add("One")
    manager.retry_track(job.id, track.id)
    await manager.run_pending(job.id)

    retried = manager.get_track(job.id, track.id)
    assert retried.status is TrackStatus.FAILED
    assert retried.output_path is None
    assert retried.target_bitrate_kbps is None


def test_cancel_track_refreshes_job_status(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None))

    manager.cancel_track(job.id, track.id)

    assert manager.get_job(job.id).status is JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_pause_job_prevents_queued_tracks_from_starting(tmp_path: Path):
    downloader = CountingDownloader()
    manager = JobManager(downloader, FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", None, 192))

    manager.pause_job(job.id)
    await manager.run_pending(job.id)

    assert manager.get_job(job.id).status is JobStatus.PAUSED
    assert manager.get_track(job.id, track.id).status is TrackStatus.QUEUED
    assert downloader.download_count == 0


@pytest.mark.asyncio
async def test_resume_job_allows_paused_tracks_to_continue(tmp_path: Path):
    downloader = CountingDownloader()
    manager = JobManager(downloader, FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", None, 192))

    manager.pause_job(job.id)
    manager.resume_job(job.id)
    await manager.run_pending(job.id)

    assert manager.get_job(job.id).status is JobStatus.COMPLETED
    assert manager.get_track(job.id, track.id).status is TrackStatus.COMPLETED
    assert downloader.download_count == 1


def test_cancel_job_marks_pending_and_active_tracks_canceled(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    queued = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=queued", "Queued", None, 192))
    analyzing = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=analyzing", "Analyzing", None, 192))
    downloading = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=downloading", "Downloading", None, 192))
    converting = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=converting", "Converting", None, 192))
    completed = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=completed", "Completed", None, 192))
    failed = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=failed", "Failed", None, 192))
    analyzing.status = TrackStatus.ANALYZING
    downloading.status = TrackStatus.DOWNLOADING
    converting.status = TrackStatus.CONVERTING
    completed.status = TrackStatus.COMPLETED
    failed.status = TrackStatus.FAILED

    manager.cancel_job(job.id)

    assert manager.get_job(job.id).status is JobStatus.CANCELED
    assert [manager.get_track(job.id, track.id).status for track in [queued, analyzing, downloading, converting]] == [
        TrackStatus.CANCELED,
        TrackStatus.CANCELED,
        TrackStatus.CANCELED,
        TrackStatus.CANCELED,
    ]
    assert manager.get_track(job.id, completed.id).status is TrackStatus.COMPLETED
    assert manager.get_track(job.id, failed.id).status is TrackStatus.FAILED


def test_failed_and_queued_tracks_keep_job_running(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    failed = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=failed", "Failed", None, 192))
    queued = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=queued", "Queued", None, 192))
    failed.status = TrackStatus.FAILED
    queued.status = TrackStatus.QUEUED

    manager._refresh_job_status(job)

    assert job.status is JobStatus.RUNNING


def test_retry_track_refreshes_parent_job_to_running(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=failed", "Failed", None, 192))
    track.status = TrackStatus.FAILED
    manager._refresh_job_status(job)
    assert job.status is JobStatus.COMPLETED_WITH_ERRORS

    manager.retry_track(job.id, track.id)

    assert manager.get_job(job.id).status is JobStatus.RUNNING


def test_retry_failed_refreshes_parent_job_to_running(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=failed", "Failed", None, 192))
    track.status = TrackStatus.FAILED
    manager._refresh_job_status(job)
    assert job.status is JobStatus.COMPLETED_WITH_ERRORS

    manager.retry_failed(job.id)

    assert manager.get_job(job.id).status is JobStatus.RUNNING


def test_retry_track_can_update_job_cookie_source(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=failed", "Failed", None, 192))
    track.status = TrackStatus.FAILED

    manager.retry_track(job.id, track.id, cookie_source="chrome")

    assert manager.get_job(job.id).cookie_source == "chrome"


def test_retry_failed_can_update_job_cookie_source(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=failed", "Failed", None, 192))
    track.status = TrackStatus.FAILED

    manager.retry_failed(job.id, cookie_source="edge")

    assert manager.get_job(job.id).cookie_source == "edge"


def test_set_cookie_source_updates_existing_job(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)

    updated = manager.set_cookie_source(job.id, "chrome")

    assert updated is job
    assert manager.get_job(job.id).cookie_source == "chrome"


@pytest.mark.asyncio
async def test_auto_cookie_source_falls_back_when_chrome_cookie_database_is_locked(tmp_path: Path):
    downloader = AutoCookieFallbackDownloader()
    manager = JobManager(downloader, FakeEncoder())
    job = manager.create_job(
        "https://music.youtube.com/playlist?list=abc",
        tmp_path,
        OutputMode.MP3_192,
        1,
        cookie_source="auto",
    )

    await manager.run_job(job.id)

    saved = manager.get_job(job.id)
    assert downloader.playlist_cookie_sources == ["chrome", "edge"]
    assert saved.cookie_source == "edge"
    assert saved.status is JobStatus.COMPLETED


def test_latest_job_prefers_newest_active_job(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    completed = manager.create_job("https://music.youtube.com/playlist?list=done", tmp_path, OutputMode.MP3_192, 1)
    completed.status = JobStatus.COMPLETED
    active = manager.create_job("https://music.youtube.com/playlist?list=active", tmp_path, OutputMode.MP3_192, 1)

    assert manager.latest_job() is active


@pytest.mark.asyncio
async def test_set_cookie_source_is_used_by_next_pending_download(tmp_path: Path):
    downloader = CookieRecordingDownloader()
    manager = JobManager(downloader, FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192))

    manager.set_cookie_source(job.id, "chrome")
    await manager.run_pending(job.id)

    assert downloader.download_cookie_sources == ["chrome"]


def test_terminal_job_history_prunes_oldest_terminal_jobs(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder(), max_history=2)
    first = manager.create_job("https://music.youtube.com/playlist?list=one", tmp_path, OutputMode.MP3_192, 1)
    first.status = JobStatus.COMPLETED
    second = manager.create_job("https://music.youtube.com/playlist?list=two", tmp_path, OutputMode.MP3_192, 1)
    second.status = JobStatus.COMPLETED

    third = manager.create_job("https://music.youtube.com/playlist?list=three", tmp_path, OutputMode.MP3_192, 1)

    with pytest.raises(KeyError):
        manager.get_job(first.id)
    assert manager.get_job(second.id) is second
    assert manager.get_job(third.id) is third


def test_history_pruning_keeps_active_jobs_even_over_limit(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder(), max_history=1)
    active = manager.create_job("https://music.youtube.com/playlist?list=active", tmp_path, OutputMode.MP3_192, 1)
    terminal = manager.create_job("https://music.youtube.com/playlist?list=terminal", tmp_path, OutputMode.MP3_192, 1)
    terminal.status = JobStatus.COMPLETED

    newer_active = manager.create_job("https://music.youtube.com/playlist?list=newer", tmp_path, OutputMode.MP3_192, 1)

    assert manager.get_job(active.id) is active
    assert manager.get_job(newer_active.id) is newer_active
    with pytest.raises(KeyError):
        manager.get_job(terminal.id)


@pytest.mark.asyncio
async def test_cancel_during_completion_transition_is_not_overwritten(tmp_path: Path):
    class SingleDownloader(FakeDownloader):
        async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
            return [MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 192)]

    class CancelDuringCompletionEncoder(FakeEncoder):
        def __init__(self):
            super().__init__()
            self.cancel = lambda: None

        async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int):
            output_path.write_text(f"mp3 {bitrate_kbps}", encoding="utf-8")
            return CancelOnStrPath(output_path, self.cancel)

    encoder = CancelDuringCompletionEncoder()
    manager = JobManager(SingleDownloader(), encoder)
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    encoder.cancel = lambda: manager.cancel_track(job.id, manager.get_job(job.id).tracks[0].id)

    await manager.run_job(job.id)

    track = manager.get_job(job.id).tracks[0]
    assert track.status is TrackStatus.CANCELED
    assert track.output_path is None


def test_progress_after_cancel_does_not_mutate_canceled_track(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None))

    manager.cancel_track(job.id, track.id)
    manager._set_progress(track, 75)

    assert track.status is TrackStatus.CANCELED
    assert track.progress == 0
