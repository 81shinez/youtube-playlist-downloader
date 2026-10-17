import asyncio
import time
from pathlib import Path
from threading import RLock
from typing import Protocol

from youtube_music_downloader.bitrate import OutputMode, choose_target_bitrate
from youtube_music_downloader.filenames import sanitize_filename
from youtube_music_downloader.models import Job, JobStatus, MediaTrack, Track, TrackStatus


_COOKIE_SOURCE_UNSET = object()
AUTO_COOKIE_SOURCE = "auto"
AUTO_COOKIE_CANDIDATES: tuple[str | None, ...] = ("chrome", "edge", "firefox", "brave", None)
COOKIE_SOURCE_LABELS = {
    "chrome": "Chrome",
    "edge": "Edge",
    "firefox": "Firefox",
    "brave": "Brave",
    None: "쿠키 사용 안 함",
}
ACTIVE_TRACK_STATUSES = {
    TrackStatus.QUEUED,
    TrackStatus.ANALYZING,
    TrackStatus.DOWNLOADING,
    TrackStatus.CONVERTING,
}


def _log(message: str) -> None:
    print(f"[ymd] {time.strftime('%H:%M:%S')} {message}", flush=True)


class Downloader(Protocol):
    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        ...

    async def download_audio(self, track: MediaTrack, work_dir: Path, progress, cookie_source: str | None = None):
        ...

    async def source_bitrate(self, source_url: str, cookie_source: str | None = None) -> int | None:
        ...


class Encoder(Protocol):
    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        ...


class JobManager:
    def __init__(self, downloader: Downloader, encoder: Encoder, max_history: int = 100):
        self._downloader = downloader
        self._encoder = encoder
        self._max_history = max(0, max_history)
        self._jobs: dict[str, Job] = {}
        self._state_lock = RLock()
        self._run_pending_lock = asyncio.Lock()
        self._output_path_lock = asyncio.Lock()
        self._reserved_output_paths: set[Path] = set()

    def create_job(
        self,
        playlist_url: str,
        output_dir: Path,
        output_mode: OutputMode,
        concurrency: int,
        cookie_source: str | None = None,
    ) -> Job:
        job = Job(
            playlist_url=playlist_url,
            output_dir=output_dir,
            output_mode=output_mode,
            concurrency=concurrency,
            cookie_source=cookie_source,
        )
        with self._state_lock:
            self._jobs[job.id] = job
            self._prune_history_locked()
        return job

    def get_job(self, job_id: str) -> Job:
        with self._state_lock:
            return self._jobs[job_id]

    def latest_job(self) -> Job | None:
        with self._state_lock:
            jobs = list(self._jobs.values())
            for job in reversed(jobs):
                if not self._is_terminal_job(job):
                    return job
            return jobs[-1] if jobs else None

    def get_track(self, job_id: str, track_id: str) -> Track:
        with self._state_lock:
            return self._get_track_locked(self._jobs[job_id], track_id)

    def add_track(self, job_id: str, media_track: MediaTrack) -> Track:
        track = Track(
            source_url=media_track.source_url,
            title=media_track.title,
            artist=media_track.artist,
            source_bitrate_kbps=media_track.source_bitrate_kbps,
        )
        with self._state_lock:
            self._jobs[job_id].tracks.append(track)
        return track

    def ensure_encoder_available(self) -> None:
        self._ensure_encoder_available()

    async def run_job(self, job_id: str) -> None:
        with self._state_lock:
            job = self._jobs[job_id]
            if job.status is JobStatus.CANCELED:
                return

        try:
            self._ensure_encoder_available()
        except Exception as exc:
            with self._state_lock:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                self._prune_history_locked()
            _log(f"job {job_id}: encoder unavailable: {exc}")
            return

        with self._state_lock:
            job = self._jobs[job_id]
            if job.status is JobStatus.CANCELED:
                return
            job.error_message = None
            job.status = JobStatus.ANALYZING
        _log(f"job {job_id}: analyzing playlist")
        try:
            for media_track in await self._playlist_tracks_with_cookie_source(job):
                self.add_track(job.id, media_track)
        except Exception as exc:
            with self._state_lock:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                self._prune_history_locked()
            _log(f"job {job_id}: playlist analysis failed: {exc}")
            return
        _log(f"job {job_id}: playlist analysis completed with {len(job.tracks)} tracks")
        with self._state_lock:
            if job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
                return
        await self.run_pending(job_id)

    def _ensure_encoder_available(self) -> None:
        ensure_available = getattr(self._encoder, "ensure_available", None)
        if ensure_available is not None:
            ensure_available()

    async def _playlist_tracks_with_cookie_source(self, job: Job) -> list[MediaTrack]:
        if job.cookie_source != AUTO_COOKIE_SOURCE:
            return await self._downloader.playlist_tracks(job.playlist_url, job.cookie_source)

        errors: list[str] = []
        for candidate in AUTO_COOKIE_CANDIDATES:
            try:
                tracks = await self._downloader.playlist_tracks(job.playlist_url, candidate)
            except Exception as exc:
                errors.append(f"{COOKIE_SOURCE_LABELS[candidate]}: {exc}")
                continue

            with self._state_lock:
                job.cookie_source = candidate
            return tracks

        message = "; ".join(errors) if errors else "사용 가능한 쿠키 소스가 없습니다."
        raise RuntimeError(f"브라우저 쿠키 자동 선택 실패: {message}")

    async def run_pending(self, job_id: str) -> None:
        async with self._run_pending_lock:
            with self._state_lock:
                job = self._jobs[job_id]
                if job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
                    return

            try:
                self._ensure_encoder_available()
            except Exception as exc:
                with self._state_lock:
                    if job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
                        return
                    job.status = JobStatus.FAILED
                    job.error_message = str(exc)
                    self._prune_history_locked()
                _log(f"job {job_id}: encoder unavailable: {exc}")
                return

            with self._state_lock:
                if job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
                    return
                job.error_message = None
                job.status = JobStatus.RUNNING
                pending = [track for track in job.tracks if track.status is TrackStatus.QUEUED]
            semaphore = asyncio.Semaphore(max(1, job.concurrency))

            async def run_one(track: Track) -> None:
                async with semaphore:
                    with self._state_lock:
                        if job.status in {JobStatus.CANCELED, JobStatus.PAUSED}:
                            return
                        if track.status is not TrackStatus.QUEUED:
                            return
                    await self._process_track(job, track)

            await asyncio.gather(*(run_one(track) for track in pending))
            with self._state_lock:
                self._refresh_job_status_locked(job)
                self._prune_history_locked()

    async def _process_track(self, job: Job, track: Track) -> None:
        with self._state_lock:
            if track.status is TrackStatus.CANCELED:
                return
            if job.status is JobStatus.CANCELED:
                track.status = TrackStatus.CANCELED
                return
            if job.status is JobStatus.PAUSED:
                return

            track.attempts += 1
            self._reset_track_run_state_locked(track)
            track.status = TrackStatus.ANALYZING
            media_track = MediaTrack(track.source_url, track.title, track.artist, track.source_bitrate_kbps)
        work_dir = job.output_dir / ".ymd-work"
        reserved_output_path: Path | None = None

        try:
            if job.output_mode is OutputMode.MP3_MAX and media_track.source_bitrate_kbps is None:
                resolved_bitrate = await self._downloader.source_bitrate(media_track.source_url, job.cookie_source)
                with self._state_lock:
                    if track.status is TrackStatus.CANCELED:
                        return
                    track.source_bitrate_kbps = resolved_bitrate
                    media_track = MediaTrack(track.source_url, track.title, track.artist, track.source_bitrate_kbps)

            work_dir.mkdir(parents=True, exist_ok=True)
            with self._state_lock:
                if track.status is TrackStatus.CANCELED:
                    return
                track.status = TrackStatus.DOWNLOADING

            source_path = await self._downloader.download_audio(
                media_track,
                work_dir,
                lambda value: self._set_progress(track, value),
                job.cookie_source,
            )
            with self._state_lock:
                if track.status is TrackStatus.CANCELED:
                    return

                track.status = TrackStatus.CONVERTING
                track.target_bitrate_kbps = choose_target_bitrate(job.output_mode, track.source_bitrate_kbps)
                target_bitrate_kbps = track.target_bitrate_kbps
            output_path = await self._reserve_mp3_path(job.output_dir, track.title, track.artist)
            reserved_output_path = output_path
            with self._state_lock:
                if track.status is TrackStatus.CANCELED:
                    return

            encoded = await self._encoder.encode_mp3(source_path, output_path, target_bitrate_kbps)
            with self._state_lock:
                if track.status is TrackStatus.CANCELED:
                    return

                output_path_text = str(encoded)
                if track.status is TrackStatus.CANCELED:
                    return

                track.output_path = output_path_text
                track.progress = 100
                track.status = TrackStatus.COMPLETED
        except Exception as exc:
            with self._state_lock:
                if track.status is TrackStatus.CANCELED:
                    return
                track.status = TrackStatus.FAILED
                track.output_path = None
                track.target_bitrate_kbps = None
                track.error_message = str(exc)
        finally:
            if reserved_output_path is not None:
                await self._release_mp3_path(reserved_output_path)

    def _set_progress(self, track: Track, value: int) -> None:
        with self._state_lock:
            if track.status is not TrackStatus.CANCELED:
                track.progress = max(0, min(100, int(value)))

    async def _reserve_mp3_path(self, output_dir: Path, title: str, artist: str | None = None) -> Path:
        async with self._output_path_lock:
            safe_title = sanitize_filename(title)
            safe_artist = sanitize_filename(artist, fallback="") if artist else ""
            stem = f"{safe_artist} - {safe_title}" if safe_artist else safe_title
            candidate = output_dir / f"{stem}.mp3"
            suffix = 2

            while candidate.exists() or candidate in self._reserved_output_paths:
                candidate = output_dir / f"{stem} ({suffix}).mp3"
                suffix += 1

            self._reserved_output_paths.add(candidate)
            return candidate

    async def _release_mp3_path(self, output_path: Path) -> None:
        async with self._output_path_lock:
            self._reserved_output_paths.discard(output_path)

    def retry_track(
        self,
        job_id: str,
        track_id: str,
        cookie_source: str | None | object = _COOKIE_SOURCE_UNSET,
    ) -> Track:
        with self._state_lock:
            job = self._jobs[job_id]
            track = self._get_track_locked(job, track_id)
            if track.status not in {TrackStatus.FAILED, TrackStatus.COMPLETED}:
                raise ValueError("Only failed or completed tracks can be retried")
            if cookie_source is not _COOKIE_SOURCE_UNSET:
                job.cookie_source = cookie_source
            track.status = TrackStatus.QUEUED
            self._reset_track_run_state_locked(track)
            self._refresh_job_status_locked(job)
            return track

    def retry_failed(self, job_id: str, cookie_source: str | None | object = _COOKIE_SOURCE_UNSET) -> int:
        with self._state_lock:
            job = self._jobs[job_id]
            if cookie_source is not _COOKIE_SOURCE_UNSET:
                job.cookie_source = cookie_source
            reset = 0
            for track in job.tracks:
                if track.status is TrackStatus.FAILED:
                    track.status = TrackStatus.QUEUED
                    self._reset_track_run_state_locked(track)
                    reset += 1
            if reset:
                self._refresh_job_status_locked(job)
            return reset

    def pause_job(self, job_id: str) -> Job:
        with self._state_lock:
            job = self._jobs[job_id]
            if not self._is_terminal_job(job):
                job.status = JobStatus.PAUSED
            return job

    def resume_job(self, job_id: str) -> Job:
        with self._state_lock:
            job = self._jobs[job_id]
            if job.status is JobStatus.PAUSED:
                job.status = JobStatus.RUNNING
                self._refresh_job_status_locked(job)
            return job

    def cancel_job(self, job_id: str) -> Job:
        with self._state_lock:
            job = self._jobs[job_id]
            job.status = JobStatus.CANCELED
            for track in job.tracks:
                if track.status in ACTIVE_TRACK_STATUSES:
                    track.status = TrackStatus.CANCELED
            self._prune_history_locked()
            return job

    def set_cookie_source(self, job_id: str, cookie_source: str | None) -> Job:
        with self._state_lock:
            job = self._jobs[job_id]
            job.cookie_source = cookie_source
            return job

    def cancel_track(self, job_id: str, track_id: str) -> Track:
        with self._state_lock:
            job = self._jobs[job_id]
            track = self._get_track_locked(job, track_id)
            if track.status in ACTIVE_TRACK_STATUSES:
                track.status = TrackStatus.CANCELED
                self._refresh_job_status_locked(job)
                self._prune_history_locked()
            return track

    def _reset_track_run_state(self, track: Track) -> None:
        with self._state_lock:
            self._reset_track_run_state_locked(track)

    def _reset_track_run_state_locked(self, track: Track) -> None:
        track.target_bitrate_kbps = None
        track.progress = 0
        track.output_path = None
        track.error_message = None

    def _refresh_job_status(self, job: Job) -> None:
        with self._state_lock:
            self._refresh_job_status_locked(job)
            self._prune_history_locked()

    def _refresh_job_status_locked(self, job: Job) -> None:
        if job.status is JobStatus.CANCELED:
            return
        statuses = {track.status for track in job.tracks}
        if job.status is JobStatus.PAUSED and statuses & ACTIVE_TRACK_STATUSES:
            return
        if statuses & ACTIVE_TRACK_STATUSES:
            job.status = JobStatus.RUNNING
        elif TrackStatus.FAILED in statuses:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        elif not statuses or statuses <= {TrackStatus.COMPLETED, TrackStatus.CANCELED}:
            job.status = JobStatus.COMPLETED
        else:
            job.status = JobStatus.RUNNING

    def _get_track_locked(self, job: Job, track_id: str) -> Track:
        for track in job.tracks:
            if track.id == track_id:
                return track
        raise KeyError(track_id)

    def _prune_history_locked(self) -> None:
        while len(self._jobs) > self._max_history:
            for job_id, job in list(self._jobs.items()):
                if self._is_terminal_job(job):
                    del self._jobs[job_id]
                    break
            else:
                break

    def _is_terminal_job(self, job: Job) -> bool:
        return job.status in {
            JobStatus.COMPLETED,
            JobStatus.COMPLETED_WITH_ERRORS,
            JobStatus.FAILED,
            JobStatus.CANCELED,
        }
