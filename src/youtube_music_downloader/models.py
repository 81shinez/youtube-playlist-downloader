from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

from youtube_music_downloader.bitrate import OutputMode


class JobStatus(str, Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    RUNNING = "running"
    PAUSED = "paused"
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
    cookie_source: str | None = None
    id: str = field(default_factory=lambda: f"job_{uuid4().hex}")
    status: JobStatus = JobStatus.QUEUED
    tracks: list[Track] = field(default_factory=list)
    error_message: str | None = None
