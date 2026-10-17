# YouTube Music Downloader Implementation Plan

> 과거 구현 계획: 아래 체크리스트와 작업 지시는 초기 웹 앱 구현 당시의 기록입니다.
> 현재 미완료 작업이나 개발 절차는 아니며, [개발자 문서](../../development/README.md)를 참고하세요.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a localhost FastAPI web app that accepts a YouTube Music playlist URL and writes authorized tracks as MP3 files using either 192kbps or source-aware maximum bitrate mode.

**Architecture:** The backend owns job state, playlist processing, retry/cancel actions, and static asset serving. Media operations sit behind small interfaces so tests can use fakes and avoid real network downloads. The frontend is static HTML/CSS/JS that polls the API and renders the job table.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic, pytest, httpx, yt-dlp, ffmpeg executable, plain HTML/CSS/JavaScript.

---

## File Structure

- Create `pyproject.toml`: project metadata, runtime dependencies, dev dependencies, pytest config.
- Create `README.md`: local setup, run command, output mode explanation, authorized-use note.
- Create `src/youtube_music_downloader/__init__.py`: package marker and version.
- Create `src/youtube_music_downloader/bitrate.py`: bitrate mode enum and target bitrate policy.
- Create `src/youtube_music_downloader/filenames.py`: filename sanitization and collision-safe MP3 path selection.
- Create `src/youtube_music_downloader/models.py`: dataclasses and enums for jobs, tracks, requests, media metadata, and summaries.
- Create `src/youtube_music_downloader/job_manager.py`: in-memory job registry, worker scheduling, state transitions, retry/cancel behavior.
- Create `src/youtube_music_downloader/media.py`: downloader/encoder protocols plus yt-dlp and ffmpeg adapters.
- Create `src/youtube_music_downloader/api.py`: FastAPI app factory and API routes.
- Create `src/youtube_music_downloader/main.py`: Uvicorn entrypoint.
- Create `src/youtube_music_downloader/static/index.html`: utility dashboard markup.
- Create `src/youtube_music_downloader/static/styles.css`: responsive app styling.
- Create `src/youtube_music_downloader/static/app.js`: form handling, polling, row actions.
- Create `tests/test_bitrate.py`: bitrate policy tests.
- Create `tests/test_filenames.py`: filename policy tests.
- Create `tests/test_job_manager.py`: state transition and retry tests using fake media services.
- Create `tests/test_api.py`: FastAPI route tests using fake job manager dependencies.

## Task 1: Tooling And Package Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/youtube_music_downloader/__init__.py`
- Create: `src/youtube_music_downloader/main.py`
- Create: `src/youtube_music_downloader/static/index.html`
- Create: `src/youtube_music_downloader/static/styles.css`
- Create: `src/youtube_music_downloader/static/app.js`

- [ ] **Step 1: Add project metadata and dependencies**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "youtube-music-downloader"
version = "0.1.0"
description = "Local web utility for saving authorized YouTube Music playlists as MP3 files."
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn[standard]>=0.30,<1",
  "pydantic>=2,<3",
  "yt-dlp>=2025.1.1",
]

[project.optional-dependencies]
dev = [
  "pytest>=8,<9",
  "pytest-asyncio>=0.23,<1",
  "httpx>=0.27,<1",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
youtube_music_downloader = ["static/*.html", "static/*.css", "static/*.js"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Add README**

Create `README.md`:

```markdown
# YouTube Music Downloader

Local web utility for saving authorized YouTube Music playlists as MP3 files.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

`ffmpeg` must be installed and available on `PATH`.

## Run

```powershell
.\.venv\Scripts\python -m youtube_music_downloader.main
```

Open `http://127.0.0.1:8000`.

## Output Modes

- `MP3 192kbps`: writes every completed file as 192kbps MP3.
- `MP3 maximum`: chooses `min(source_bitrate_kbps, 320)` and uses 256kbps when source bitrate is unknown.

MP3 conversion improves compatibility. It does not create audio quality beyond the downloaded source.

Use this only for playlists and tracks you have permission to download or archive.
```

- [ ] **Step 3: Add package marker and temporary entrypoint**

Create `src/youtube_music_downloader/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/youtube_music_downloader/main.py`:

```python
import uvicorn


def main() -> None:
    uvicorn.run("youtube_music_downloader.api:create_app", factory=True, host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add initial static shell**

Create `src/youtube_music_downloader/static/index.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>YouTube Music Downloader</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <main class="app">
    <h1>YouTube Music Downloader</h1>
    <p>Local MP3 download utility.</p>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

Create `src/youtube_music_downloader/static/styles.css`:

```css
body {
  margin: 0;
  font-family: "Segoe UI", system-ui, sans-serif;
}

.app {
  padding: 24px;
}
```

Create `src/youtube_music_downloader/static/app.js`:

```javascript
console.log("YouTube Music Downloader UI loaded");
```

- [ ] **Step 5: Install dependencies**

Run:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Expected: pip installs FastAPI, Uvicorn, pytest, pytest-asyncio, httpx, and yt-dlp without errors.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml README.md src/youtube_music_downloader
git commit -m "chore: scaffold local web app"
```

## Task 2: Bitrate Policy

**Files:**
- Create: `src/youtube_music_downloader/bitrate.py`
- Test: `tests/test_bitrate.py`

- [ ] **Step 1: Write failing bitrate tests**

Create `tests/test_bitrate.py`:

```python
import pytest

from youtube_music_downloader.bitrate import OutputMode, choose_target_bitrate


def test_192_mode_always_returns_192():
    assert choose_target_bitrate(OutputMode.MP3_192, source_bitrate_kbps=256) == 192
    assert choose_target_bitrate(OutputMode.MP3_192, source_bitrate_kbps=None) == 192


def test_max_mode_uses_source_bitrate_when_present():
    assert choose_target_bitrate(OutputMode.MP3_MAX, source_bitrate_kbps=256) == 256


def test_max_mode_caps_above_320():
    assert choose_target_bitrate(OutputMode.MP3_MAX, source_bitrate_kbps=384) == 320


def test_max_mode_preserves_low_source_bitrate():
    assert choose_target_bitrate(OutputMode.MP3_MAX, source_bitrate_kbps=128) == 128


def test_max_mode_uses_256_when_source_bitrate_missing():
    assert choose_target_bitrate(OutputMode.MP3_MAX, source_bitrate_kbps=None) == 256


def test_output_mode_parses_api_values():
    assert OutputMode.from_api_value("192") is OutputMode.MP3_192
    assert OutputMode.from_api_value("max") is OutputMode.MP3_MAX


def test_output_mode_rejects_unknown_api_value():
    with pytest.raises(ValueError, match="Unsupported output mode"):
        OutputMode.from_api_value("320")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_bitrate.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'youtube_music_downloader.bitrate'`.

- [ ] **Step 3: Implement bitrate policy**

Create `src/youtube_music_downloader/bitrate.py`:

```python
from enum import Enum


class OutputMode(str, Enum):
    MP3_192 = "192"
    MP3_MAX = "max"

    @classmethod
    def from_api_value(cls, value: str) -> "OutputMode":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"Unsupported output mode: {value}") from exc


def choose_target_bitrate(mode: OutputMode, source_bitrate_kbps: int | None) -> int:
    if mode is OutputMode.MP3_192:
        return 192
    if source_bitrate_kbps is None:
        return 256
    return min(source_bitrate_kbps, 320)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_bitrate.py -v
```

Expected: PASS, 7 tests.

- [ ] **Step 5: Commit**

```powershell
git add src/youtube_music_downloader/bitrate.py tests/test_bitrate.py
git commit -m "feat: add mp3 bitrate policy"
```

## Task 3: Filename Policy

**Files:**
- Create: `src/youtube_music_downloader/filenames.py`
- Test: `tests/test_filenames.py`

- [ ] **Step 1: Write failing filename tests**

Create `tests/test_filenames.py`:

```python
from pathlib import Path

from youtube_music_downloader.filenames import resolve_mp3_path, sanitize_filename


def test_sanitize_filename_removes_windows_reserved_characters():
    assert sanitize_filename('A:B*C?D"E<F>G|H') == "A_B_C_D_E_F_G_H"


def test_sanitize_filename_collapses_whitespace_and_strips_edges():
    assert sanitize_filename("  hello   world  ") == "hello world"


def test_sanitize_filename_returns_fallback_for_empty_value():
    assert sanitize_filename("   ...   ") == "track"


def test_resolve_mp3_path_uses_artist_and_title(tmp_path: Path):
    path = resolve_mp3_path(tmp_path, title="Song", artist="Artist")
    assert path == tmp_path / "Artist - Song.mp3"


def test_resolve_mp3_path_adds_suffix_when_file_exists(tmp_path: Path):
    first = tmp_path / "Artist - Song.mp3"
    second = tmp_path / "Artist - Song (2).mp3"
    first.write_text("already here", encoding="utf-8")

    path = resolve_mp3_path(tmp_path, title="Song", artist="Artist")

    assert path == second
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_filenames.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'youtube_music_downloader.filenames'`.

- [ ] **Step 3: Implement filename policy**

Create `src/youtube_music_downloader/filenames.py`:

```python
from pathlib import Path
import re

RESERVED_CHARS = re.compile(r'[<>:"/\\|?*]')
WHITESPACE = re.compile(r"\s+")


def sanitize_filename(value: str, fallback: str = "track") -> str:
    cleaned = RESERVED_CHARS.sub("_", value)
    cleaned = WHITESPACE.sub(" ", cleaned).strip(" .")
    return cleaned or fallback


def resolve_mp3_path(output_dir: Path, title: str, artist: str | None = None) -> Path:
    safe_title = sanitize_filename(title)
    safe_artist = sanitize_filename(artist or "")
    stem = f"{safe_artist} - {safe_title}" if safe_artist else safe_title
    candidate = output_dir / f"{stem}.mp3"
    suffix = 2
    while candidate.exists():
        candidate = output_dir / f"{stem} ({suffix}).mp3"
        suffix += 1
    return candidate
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_filenames.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```powershell
git add src/youtube_music_downloader/filenames.py tests/test_filenames.py
git commit -m "feat: add mp3 filename policy"
```

## Task 4: Domain Models And Job Manager

**Files:**
- Create: `src/youtube_music_downloader/models.py`
- Create: `src/youtube_music_downloader/job_manager.py`
- Test: `tests/test_job_manager.py`

- [ ] **Step 1: Write failing job manager tests**

Create `tests/test_job_manager.py`:

```python
import asyncio
from pathlib import Path

import pytest

from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.models import JobStatus, MediaTrack, TrackStatus


class FakeDownloader:
    async def playlist_tracks(self, playlist_url: str) -> list[MediaTrack]:
        return [
            MediaTrack(source_url="https://music.youtube.com/watch?v=one", title="One", artist="Artist", source_bitrate_kbps=256),
            MediaTrack(source_url="https://music.youtube.com/watch?v=two", title="Two", artist="Artist", source_bitrate_kbps=192),
        ]

    async def download_audio(self, track: MediaTrack, work_dir: Path, progress):
        progress(50)
        return work_dir / f"{track.title}.webm"


class FakeEncoder:
    def __init__(self):
        self.fail_titles: set[str] = set()

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        if source_path.stem in self.fail_titles:
            raise RuntimeError("conversion failed")
        output_path.write_text(f"mp3 {bitrate_kbps}", encoding="utf-8")
        return output_path


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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_job_manager.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'youtube_music_downloader.job_manager'`.

- [ ] **Step 3: Implement models**

Create `src/youtube_music_downloader/models.py`:

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

from youtube_music_downloader.bitrate import OutputMode


class JobStatus(str, Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELED = "canceled"


class TrackStatus(str, Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class MediaTrack:
    source_url: str
    title: str
    artist: str | None
    source_bitrate_kbps: int | None


@dataclass
class Track:
    source_url: str
    title: str
    artist: str | None = None
    source_bitrate_kbps: int | None = None
    id: str = field(default_factory=lambda: f"track_{uuid4().hex}")
    target_bitrate_kbps: int | None = None
    status: TrackStatus = TrackStatus.QUEUED
    progress: int = 0
    output_path: str | None = None
    error_message: str | None = None
    attempts: int = 0


@dataclass
class Job:
    playlist_url: str
    output_dir: Path
    output_mode: OutputMode
    concurrency: int
    id: str = field(default_factory=lambda: f"job_{uuid4().hex}")
    status: JobStatus = JobStatus.QUEUED
    tracks: list[Track] = field(default_factory=list)
    error_message: str | None = None
```

- [ ] **Step 4: Implement job manager**

Create `src/youtube_music_downloader/job_manager.py`:

```python
import asyncio
from pathlib import Path
from typing import Protocol

from youtube_music_downloader.bitrate import OutputMode, choose_target_bitrate
from youtube_music_downloader.filenames import resolve_mp3_path
from youtube_music_downloader.models import Job, JobStatus, MediaTrack, Track, TrackStatus


class Downloader(Protocol):
    async def playlist_tracks(self, playlist_url: str) -> list[MediaTrack]:
        ...

    async def download_audio(self, track: MediaTrack, work_dir: Path, progress):
        ...


class Encoder(Protocol):
    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        ...


class JobManager:
    def __init__(self, downloader: Downloader, encoder: Encoder):
        self._downloader = downloader
        self._encoder = encoder
        self._jobs: dict[str, Job] = {}

    def create_job(self, playlist_url: str, output_dir: Path, output_mode: OutputMode, concurrency: int) -> Job:
        job = Job(playlist_url=playlist_url, output_dir=output_dir, output_mode=output_mode, concurrency=concurrency)
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> Job:
        return self._jobs[job_id]

    def get_track(self, job_id: str, track_id: str) -> Track:
        for track in self.get_job(job_id).tracks:
            if track.id == track_id:
                return track
        raise KeyError(track_id)

    def add_track(self, job_id: str, media_track: MediaTrack) -> Track:
        track = Track(
            source_url=media_track.source_url,
            title=media_track.title,
            artist=media_track.artist,
            source_bitrate_kbps=media_track.source_bitrate_kbps,
        )
        self.get_job(job_id).tracks.append(track)
        return track

    async def run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job.status = JobStatus.ANALYZING
        try:
            for media_track in await self._downloader.playlist_tracks(job.playlist_url):
                self.add_track(job.id, media_track)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            return
        await self.run_pending(job_id)

    async def run_pending(self, job_id: str) -> None:
        job = self.get_job(job_id)
        job.status = JobStatus.RUNNING
        semaphore = asyncio.Semaphore(max(1, job.concurrency))
        pending = [track for track in job.tracks if track.status is TrackStatus.QUEUED]

        async def run_one(track: Track) -> None:
            async with semaphore:
                await self._process_track(job, track)

        await asyncio.gather(*(run_one(track) for track in pending))
        self._refresh_job_status(job)

    async def _process_track(self, job: Job, track: Track) -> None:
        track.attempts += 1
        track.error_message = None
        track.progress = 0
        track.status = TrackStatus.DOWNLOADING
        media_track = MediaTrack(track.source_url, track.title, track.artist, track.source_bitrate_kbps)
        work_dir = job.output_dir / ".ymd-work"
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            source_path = await self._downloader.download_audio(media_track, work_dir, lambda value: self._set_progress(track, value))
            track.status = TrackStatus.CONVERTING
            track.target_bitrate_kbps = choose_target_bitrate(job.output_mode, track.source_bitrate_kbps)
            output_path = resolve_mp3_path(job.output_dir, track.title, track.artist)
            encoded = await self._encoder.encode_mp3(source_path, output_path, track.target_bitrate_kbps)
            track.output_path = str(encoded)
            track.progress = 100
            track.status = TrackStatus.COMPLETED
        except Exception as exc:
            track.status = TrackStatus.FAILED
            track.error_message = str(exc)

    def _set_progress(self, track: Track, value: int) -> None:
        track.progress = max(0, min(100, int(value)))

    def retry_track(self, job_id: str, track_id: str) -> Track:
        track = self.get_track(job_id, track_id)
        if track.status not in {TrackStatus.FAILED, TrackStatus.COMPLETED}:
            raise ValueError("Only failed or completed tracks can be retried")
        track.status = TrackStatus.QUEUED
        track.progress = 0
        track.error_message = None
        return track

    def retry_failed(self, job_id: str) -> int:
        reset = 0
        for track in self.get_job(job_id).tracks:
            if track.status is TrackStatus.FAILED:
                track.status = TrackStatus.QUEUED
                track.progress = 0
                track.error_message = None
                reset += 1
        return reset

    def cancel_track(self, job_id: str, track_id: str) -> Track:
        track = self.get_track(job_id, track_id)
        if track.status in {TrackStatus.QUEUED, TrackStatus.DOWNLOADING, TrackStatus.CONVERTING}:
            track.status = TrackStatus.CANCELED
        return track

    def _refresh_job_status(self, job: Job) -> None:
        statuses = {track.status for track in job.tracks}
        if TrackStatus.FAILED in statuses:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
        elif statuses and statuses <= {TrackStatus.COMPLETED, TrackStatus.CANCELED}:
            job.status = JobStatus.COMPLETED
        else:
            job.status = JobStatus.RUNNING
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_job_manager.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```powershell
git add src/youtube_music_downloader/models.py src/youtube_music_downloader/job_manager.py tests/test_job_manager.py
git commit -m "feat: add in-memory job manager"
```

## Task 5: Media Adapters

**Files:**
- Create: `src/youtube_music_downloader/media.py`
- Test: `tests/test_media.py`

- [ ] **Step 1: Write failing media adapter tests**

Create `tests/test_media.py`:

```python
from pathlib import Path

from youtube_music_downloader.media import FfmpegEncoder, YtDlpDownloader
from youtube_music_downloader.models import MediaTrack, TrackStatus


def test_yt_dlp_playlist_options_are_extract_flat():
    downloader = YtDlpDownloader()

    options = downloader.playlist_options()

    assert options["extract_flat"] == "in_playlist"
    assert options["quiet"] is True


def test_yt_dlp_download_options_include_best_audio_and_progress_hook(tmp_path: Path):
    downloader = YtDlpDownloader()

    options = downloader.download_options(tmp_path, lambda value: None)

    assert options["format"] == "bestaudio/best"
    assert options["outtmpl"].endswith("%(id)s.%(ext)s")
    assert len(options["progress_hooks"]) == 1


def test_ffmpeg_command_uses_mp3_codec_and_target_bitrate(tmp_path: Path):
    encoder = FfmpegEncoder(ffmpeg_path="ffmpeg")
    source = tmp_path / "input.webm"
    output = tmp_path / "output.mp3"

    command = encoder.build_command(source, output, bitrate_kbps=256)

    assert command == [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        "256k",
        str(output),
    ]


def test_progress_hook_reports_percent():
    values = []
    downloader = YtDlpDownloader()
    hook = downloader.progress_hook(lambda value: values.append(value))

    hook({"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100})
    hook({"status": "finished"})

    assert values == [25, 100]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_media.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'youtube_music_downloader.media'`.

- [ ] **Step 3: Implement media adapters**

Create `src/youtube_music_downloader/media.py`:

```python
import asyncio
from pathlib import Path
from typing import Callable

import yt_dlp

from youtube_music_downloader.models import MediaTrack

ProgressCallback = Callable[[int], None]


class YtDlpDownloader:
    def playlist_options(self) -> dict:
        return {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True}

    def download_options(self, output_dir: Path, progress: ProgressCallback) -> dict:
        return {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [self.progress_hook(progress)],
        }

    def progress_hook(self, progress: ProgressCallback):
        def hook(data: dict) -> None:
            if data.get("status") == "finished":
                progress(100)
                return
            downloaded = data.get("downloaded_bytes")
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            if downloaded and total:
                progress(int(downloaded * 100 / total))

        return hook

    async def playlist_tracks(self, playlist_url: str) -> list[MediaTrack]:
        def extract() -> list[MediaTrack]:
            with yt_dlp.YoutubeDL(self.playlist_options()) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
            entries = info.get("entries") or []
            tracks: list[MediaTrack] = []
            for entry in entries:
                if not entry:
                    continue
                title = entry.get("title") or entry.get("id") or "track"
                artist = entry.get("artist") or entry.get("uploader")
                source_url = entry.get("url") or entry.get("webpage_url") or entry.get("id")
                bitrate = entry.get("abr") or entry.get("tbr")
                tracks.append(MediaTrack(str(source_url), title, artist, int(bitrate) if bitrate else None))
            return tracks

        return await asyncio.to_thread(extract)

    async def download_audio(self, track: MediaTrack, work_dir: Path, progress: ProgressCallback) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)

        def download() -> Path:
            before = set(work_dir.iterdir())
            with yt_dlp.YoutubeDL(self.download_options(work_dir, progress)) as ydl:
                ydl.download([track.source_url])
            after = [path for path in work_dir.iterdir() if path not in before and path.is_file()]
            if not after:
                raise RuntimeError("download finished without an output file")
            return max(after, key=lambda path: path.stat().st_mtime)

        return await asyncio.to_thread(download)


class FfmpegEncoder:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def build_command(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> list[str]:
        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(output_path),
        ]

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            *self.build_command(source_path, output_path, bitrate_kbps),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip() or "ffmpeg failed"
            raise RuntimeError(message)
        return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_media.py -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```powershell
git add src/youtube_music_downloader/media.py tests/test_media.py
git commit -m "feat: add media adapters"
```

## Task 6: FastAPI Routes

**Files:**
- Create: `src/youtube_music_downloader/api.py`
- Modify: `src/youtube_music_downloader/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from youtube_music_downloader.api import create_app
from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.models import MediaTrack


class FakeDownloader:
    async def playlist_tracks(self, playlist_url: str) -> list[MediaTrack]:
        return [MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 256)]

    async def download_audio(self, track: MediaTrack, work_dir: Path, progress):
        progress(100)
        path = work_dir / "one.webm"
        path.write_text("audio", encoding="utf-8")
        return path


class FakeEncoder:
    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        output_path.write_text(f"mp3 {bitrate_kbps}", encoding="utf-8")
        return output_path


def make_client() -> TestClient:
    manager = JobManager(FakeDownloader(), FakeEncoder())
    return TestClient(create_app(manager=manager, auto_start_jobs=False))


def test_create_job_returns_job_id(tmp_path: Path):
    client = make_client()

    response = client.post(
        "/api/jobs",
        json={
            "playlist_url": "https://music.youtube.com/playlist?list=abc",
            "output_dir": str(tmp_path),
            "output_mode": "max",
            "concurrency": 2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"].startswith("job_")
    assert body["status"] == "queued"


def test_create_job_rejects_missing_output_dir(tmp_path: Path):
    client = make_client()

    response = client.post(
        "/api/jobs",
        json={
            "playlist_url": "https://music.youtube.com/playlist?list=abc",
            "output_dir": str(tmp_path / "missing"),
            "output_mode": "max",
            "concurrency": 2,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Output folder does not exist"


def test_get_job_returns_tracks_after_manual_run(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    app = create_app(manager=manager, auto_start_jobs=False)
    client = TestClient(app)

    created = client.post(
        "/api/jobs",
        json={
            "playlist_url": "https://music.youtube.com/playlist?list=abc",
            "output_dir": str(tmp_path),
            "output_mode": "192",
            "concurrency": 1,
        },
    ).json()
    job_id = created["job_id"]
    app.state.run_sync(job_id)

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["tracks"][0]["target_bitrate_kbps"] == 192


def test_retry_failed_endpoint_returns_reset_count(tmp_path: Path):
    manager = JobManager(FakeDownloader(), FakeEncoder())
    app = create_app(manager=manager, auto_start_jobs=False)
    client = TestClient(app)
    job = manager.create_job("https://music.youtube.com/playlist?list=abc", tmp_path, OutputMode.MP3_192, 1)
    track = manager.add_track(job.id, MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist", 256))
    track.status = TrackStatus.FAILED

    response = client.post(f"/api/jobs/{job.id}/retry-failed")

    assert response.status_code == 200
    assert response.json() == {"reset_count": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_api.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'youtube_music_downloader.api'`.

- [ ] **Step 3: Implement FastAPI app**

Create `src/youtube_music_downloader/api.py`:

```python
import asyncio
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.media import FfmpegEncoder, YtDlpDownloader
from youtube_music_downloader.models import Job, Track


class CreateJobRequest(BaseModel):
    playlist_url: str = Field(min_length=1)
    output_dir: str = Field(min_length=1)
    output_mode: str
    concurrency: int = Field(default=2, ge=1, le=4)


def serialize_track(track: Track) -> dict[str, Any]:
    data = asdict(track)
    data["status"] = track.status.value if hasattr(track.status, "value") else track.status
    return data


def serialize_job(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "playlist_url": job.playlist_url,
        "output_dir": str(job.output_dir),
        "output_mode": job.output_mode.value,
        "concurrency": job.concurrency,
        "status": job.status.value,
        "error_message": job.error_message,
        "tracks": [serialize_track(track) for track in job.tracks],
        "summary": {
            "total": len(job.tracks),
            "completed": sum(1 for track in job.tracks if serialize_track(track)["status"] == "completed"),
            "failed": sum(1 for track in job.tracks if serialize_track(track)["status"] == "failed"),
        },
    }


def create_app(manager: JobManager | None = None, auto_start_jobs: bool = True) -> FastAPI:
    app = FastAPI(title="YouTube Music Downloader")
    media_manager = manager or JobManager(YtDlpDownloader(), FfmpegEncoder())
    app.state.manager = media_manager

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    @app.post("/api/jobs")
    async def create_job(request: CreateJobRequest, background_tasks: BackgroundTasks):
        output_dir = Path(request.output_dir).expanduser()
        if not output_dir.exists():
            raise HTTPException(status_code=400, detail="Output folder does not exist")
        if not output_dir.is_dir():
            raise HTTPException(status_code=400, detail="Output path is not a folder")
        if not os.access(output_dir, os.W_OK):
            raise HTTPException(status_code=400, detail="Output folder is not writable")
        try:
            output_mode = OutputMode.from_api_value(request.output_mode)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job = media_manager.create_job(request.playlist_url, output_dir, output_mode, request.concurrency)
        if auto_start_jobs:
            background_tasks.add_task(media_manager.run_job, job.id)
        return {"job_id": job.id, "status": job.status.value}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        try:
            return serialize_job(media_manager.get_job(job_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/jobs/{job_id}/tracks/{track_id}/retry")
    def retry_track(job_id: str, track_id: str, background_tasks: BackgroundTasks):
        try:
            track = media_manager.retry_track(job_id, track_id)
            if auto_start_jobs:
                background_tasks.add_task(media_manager.run_pending, job_id)
            return serialize_track(track)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Track not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/retry-failed")
    def retry_failed(job_id: str, background_tasks: BackgroundTasks):
        try:
            reset_count = media_manager.retry_failed(job_id)
            if auto_start_jobs and reset_count:
                background_tasks.add_task(media_manager.run_pending, job_id)
            return {"reset_count": reset_count}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/jobs/{job_id}/tracks/{track_id}/cancel")
    def cancel_track(job_id: str, track_id: str):
        try:
            return serialize_track(media_manager.cancel_track(job_id, track_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Track not found") from exc

    @app.post("/api/jobs/{job_id}/open-output-folder")
    def open_output_folder(job_id: str):
        try:
            job = media_manager.get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        os.startfile(job.output_dir)
        return {"opened": str(job.output_dir)}

    def run_sync(job_id: str) -> None:
        asyncio.run(media_manager.run_job(job_id))

    app.state.run_sync = run_sync
    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_api.py -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```powershell
git add src/youtube_music_downloader/api.py src/youtube_music_downloader/main.py tests/test_api.py
git commit -m "feat: add fastapi job api"
```

## Task 7: Frontend Dashboard

**Files:**
- Modify: `src/youtube_music_downloader/static/index.html`
- Modify: `src/youtube_music_downloader/static/styles.css`
- Modify: `src/youtube_music_downloader/static/app.js`
- Test: `tests/test_static_assets.py`

- [ ] **Step 1: Write failing static asset tests**

Create `tests/test_static_assets.py`:

```python
from pathlib import Path


STATIC_DIR = Path("src/youtube_music_downloader/static")


def test_index_contains_required_controls():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    assert 'id="playlist-url"' in html
    assert 'id="output-dir"' in html
    assert 'value="192"' in html
    assert 'value="max"' in html
    assert 'id="retry-failed"' in html
    assert 'id="tracks-body"' in html


def test_javascript_wires_retry_failed_endpoint():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "/retry-failed" in script
    assert "renderTracks" in script
    assert "createJob" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_static_assets.py -v
```

Expected: FAIL because the initial UI lacks `playlist-url`, `retry-failed`, and `tracks-body`.

- [ ] **Step 3: Replace HTML**

Replace `src/youtube_music_downloader/static/index.html`:

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>YouTube Music Downloader</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <div class="shell">
    <aside>
      <div class="brand"><span class="brand-mark">YM</span><span>YouTube Music Downloader</span></div>
      <p>권한이 있는 플레이리스트를 MP3 파일로 저장합니다.</p>
      <dl class="summary">
        <div><dt>전체</dt><dd id="summary-total">0</dd></div>
        <div><dt>완료</dt><dd id="summary-completed">0</dd></div>
        <div><dt>실패</dt><dd id="summary-failed">0</dd></div>
      </dl>
    </aside>

    <main>
      <header>
        <div>
          <h1>플레이리스트 다운로드</h1>
          <p>원본보다 음질이 좋아지지는 않으며, MP3 호환성을 위해 변환합니다.</p>
        </div>
        <button id="open-folder" type="button" disabled>폴더 열기</button>
      </header>

      <section class="panel">
        <form id="job-form">
          <label>Playlist URL<input id="playlist-url" name="playlist_url" required></label>
          <label>저장 폴더<input id="output-dir" name="output_dir" required></label>
          <fieldset>
            <legend>출력 방식</legend>
            <label class="radio"><input type="radio" name="output_mode" value="192"> MP3 192kbps</label>
            <label class="radio"><input type="radio" name="output_mode" value="max" checked> MP3 최대</label>
          </fieldset>
          <label>동시 다운로드<input id="concurrency" name="concurrency" type="number" min="1" max="4" value="2"></label>
          <button type="submit">시작</button>
        </form>
      </section>

      <section class="panel">
        <div class="panel-title-row">
          <h2>작업 진행</h2>
          <button id="retry-failed" type="button" disabled>실패 항목 모두 재시도</button>
        </div>
        <p id="message" role="status"></p>
        <table>
          <thead>
            <tr><th>곡</th><th>상태</th><th>진행률</th><th>출력</th><th>작업</th></tr>
          </thead>
          <tbody id="tracks-body"></tbody>
        </table>
      </section>
    </main>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Replace CSS**

Replace `src/youtube_music_downloader/static/styles.css`:

```css
:root {
  --bg: #f6f7f8;
  --panel: #ffffff;
  --ink: #1d252c;
  --muted: #65717c;
  --line: #d9e0e6;
  --red: #d84444;
  --teal: #168476;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: var(--bg);
  color: var(--ink);
  font-family: "Segoe UI", system-ui, sans-serif;
  letter-spacing: 0;
}
.shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  min-height: 100vh;
}
aside {
  background: #18222c;
  color: #f8fafc;
  padding: 28px 22px;
}
.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  font-weight: 700;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--red);
}
.summary div {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255,255,255,.12);
  padding: 10px 0;
}
main {
  padding: 30px;
  display: grid;
  gap: 22px;
  align-content: start;
}
header, .panel-title-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}
h1, h2 { margin: 0; }
p { color: var(--muted); }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 18px;
}
form {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) minmax(220px, 320px);
  gap: 14px;
  align-items: end;
}
label, fieldset {
  display: grid;
  gap: 7px;
  border: 0;
  margin: 0;
  padding: 0;
  font-size: 13px;
  font-weight: 650;
}
.radio {
  display: inline-flex;
  margin-right: 14px;
  font-weight: 500;
}
input {
  width: 100%;
  border: 1px solid #c7d0d8;
  border-radius: 7px;
  min-height: 40px;
  padding: 9px 11px;
  font: inherit;
}
button {
  border: 1px solid #c7d0d8;
  border-radius: 8px;
  min-height: 40px;
  padding: 0 14px;
  background: white;
  color: #34424e;
  font: inherit;
  font-weight: 700;
}
form button[type="submit"] {
  background: var(--red);
  border-color: var(--red);
  color: white;
}
button:disabled {
  opacity: .45;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid var(--line);
}
.progress {
  height: 8px;
  border-radius: 999px;
  background: #e6ebef;
  overflow: hidden;
}
.progress span {
  display: block;
  height: 100%;
  background: var(--teal);
}
.error {
  color: #7d2727;
}
@media (max-width: 900px) {
  .shell, form {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 5: Replace JavaScript**

Replace `src/youtube_music_downloader/static/app.js`:

```javascript
let currentJobId = null;
let pollTimer = null;

const form = document.querySelector("#job-form");
const message = document.querySelector("#message");
const tracksBody = document.querySelector("#tracks-body");
const retryFailedButton = document.querySelector("#retry-failed");
const openFolderButton = document.querySelector("#open-folder");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await createJob();
});

retryFailedButton.addEventListener("click", async () => {
  if (!currentJobId) return;
  await fetch(`/api/jobs/${currentJobId}/retry-failed`, { method: "POST" });
  await refreshJob();
});

openFolderButton.addEventListener("click", async () => {
  if (!currentJobId) return;
  await fetch(`/api/jobs/${currentJobId}/open-output-folder`, { method: "POST" });
});

async function createJob() {
  const formData = new FormData(form);
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      playlist_url: formData.get("playlist_url"),
      output_dir: formData.get("output_dir"),
      output_mode: formData.get("output_mode"),
      concurrency: Number(formData.get("concurrency"))
    })
  });

  if (!response.ok) {
    const error = await response.json();
    message.textContent = error.detail || "작업을 만들 수 없습니다.";
    return;
  }

  const body = await response.json();
  currentJobId = body.job_id;
  openFolderButton.disabled = false;
  retryFailedButton.disabled = false;
  startPolling();
}

function startPolling() {
  if (pollTimer) window.clearInterval(pollTimer);
  refreshJob();
  pollTimer = window.setInterval(refreshJob, 1500);
}

async function refreshJob() {
  if (!currentJobId) return;
  const response = await fetch(`/api/jobs/${currentJobId}`);
  if (!response.ok) return;
  const job = await response.json();
  document.querySelector("#summary-total").textContent = job.summary.total;
  document.querySelector("#summary-completed").textContent = job.summary.completed;
  document.querySelector("#summary-failed").textContent = job.summary.failed;
  message.textContent = `작업 상태: ${job.status}`;
  renderTracks(job.tracks);
}

function renderTracks(tracks) {
  tracksBody.innerHTML = "";
  for (const track of tracks) {
    const row = document.createElement("tr");
    const output = track.target_bitrate_kbps ? `mp3 ${track.target_bitrate_kbps}` : "-";
    row.innerHTML = `
      <td><strong>${escapeHtml(track.title)}</strong><br><span>${escapeHtml(track.artist || "")}</span>${track.error_message ? `<br><span class="error">${escapeHtml(track.error_message)}</span>` : ""}</td>
      <td>${track.status}</td>
      <td><div class="progress"><span style="width:${track.progress}%"></span></div></td>
      <td>${output}</td>
      <td>${actionButton(track)}</td>
    `;
    tracksBody.appendChild(row);
  }
}

function actionButton(track) {
  if (track.status === "failed" || track.status === "completed") {
    return `<button type="button" data-action="retry" data-track-id="${track.id}">재시도</button>`;
  }
  if (track.status === "queued" || track.status === "downloading" || track.status === "converting") {
    return `<button type="button" data-action="cancel" data-track-id="${track.id}">취소</button>`;
  }
  return "";
}

tracksBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || !currentJobId) return;
  const trackId = button.dataset.trackId;
  const action = button.dataset.action;
  const endpoint = action === "retry"
    ? `/api/jobs/${currentJobId}/tracks/${trackId}/retry`
    : `/api/jobs/${currentJobId}/tracks/${trackId}/cancel`;
  await fetch(endpoint, { method: "POST" });
  await refreshJob();
});

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;"
  })[char]);
}
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python -m pytest tests/test_static_assets.py -v
```

Expected: PASS, 2 tests.

- [ ] **Step 7: Commit**

```powershell
git add src/youtube_music_downloader/static tests/test_static_assets.py
git commit -m "feat: add local web dashboard"
```

## Task 8: End-To-End Verification And Docs

**Files:**
- Modify: `README.md`
- Test command: full pytest suite.

- [ ] **Step 1: Add final README API notes**

Append to `README.md`:

```markdown
## API

- `POST /api/jobs`: create a playlist job.
- `GET /api/jobs/{job_id}`: read job status and tracks.
- `POST /api/jobs/{job_id}/tracks/{track_id}/retry`: retry one track.
- `POST /api/jobs/{job_id}/retry-failed`: retry all failed tracks.
- `POST /api/jobs/{job_id}/tracks/{track_id}/cancel`: cancel or remove a track.
- `POST /api/jobs/{job_id}/open-output-folder`: open the local output folder.

Automated tests use fake downloader and encoder objects. They do not download from YouTube Music.
```

- [ ] **Step 2: Run the full automated suite**

Run:

```powershell
.\.venv\Scripts\python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Start the local server**

Run:

```powershell
.\.venv\Scripts\python -m youtube_music_downloader.main
```

Expected: Uvicorn reports it is serving on `http://127.0.0.1:8000`.

- [ ] **Step 4: Open the app in a browser**

Open:

```text
http://127.0.0.1:8000
```

Expected: the form, output mode controls, summary, job table, and retry-all-failed button render without console errors.

- [ ] **Step 5: Commit**

```powershell
git add README.md
git commit -m "docs: add usage and api notes"
```

## Self Review

Spec coverage:

- Local FastAPI web app: Tasks 1, 6, and 7.
- MP3 output modes 192 and maximum: Tasks 2, 4, and 5.
- Best source audio via yt-dlp and MP3 encoding via ffmpeg: Task 5.
- In-memory jobs and track state model: Task 4.
- Create job, get job, retry one, retry failed, cancel, open folder APIs: Task 6.
- UI form, polling table, row actions, retry-all-failed action: Task 7.
- Fakes for tests instead of real downloads: Tasks 4, 5, and 6.
- Authorized-use note and no bypass language: Task 1.

Banned-marker scan:

- No banned markers are intentionally present.

Type consistency:

- `OutputMode`, `JobStatus`, `TrackStatus`, `MediaTrack`, `Track`, and `Job` names are consistent across tasks.
- API output mode values are `192` and `max` across tests, models, and UI.
