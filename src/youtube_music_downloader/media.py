import asyncio
import shutil
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from youtube_music_downloader.models import MediaTrack

ProgressCallback = Callable[[int], None]
MISSING_FFMPEG_MESSAGE = "ffmpeg 실행 파일을 찾을 수 없습니다. ffmpeg를 설치하고 PATH에 추가한 뒤 다시 시도하세요."


def _log(message: str) -> None:
    print(f"[ymd] {time.strftime('%H:%M:%S')} {message}", flush=True)


class YtDlpDownloader:
    @staticmethod
    def playlist_options(cookie_source: str | None = None) -> dict[str, Any]:
        return {
            "extract_flat": "in_playlist",
            "quiet": True,
            "no_warnings": True,
            **_cookie_options(cookie_source),
        }

    @staticmethod
    def metadata_options(cookie_source: str | None = None) -> dict[str, Any]:
        return {"quiet": True, "no_warnings": True, **_cookie_options(cookie_source)}

    @classmethod
    def download_options(
        cls,
        output_dir: Path,
        progress: ProgressCallback,
        cookie_source: str | None = None,
    ) -> dict[str, Any]:
        return {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [cls.progress_hook(progress)],
            **_cookie_options(cookie_source),
        }

    @staticmethod
    def progress_hook(progress: ProgressCallback) -> Callable[[dict[str, Any]], None]:
        def hook(status: dict[str, Any]) -> None:
            if status.get("status") == "finished":
                progress(100)
                return

            if status.get("status") != "downloading":
                return

            downloaded = status.get("downloaded_bytes")
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if downloaded is None or not total:
                return

            percent = int((float(downloaded) / float(total)) * 100)
            progress(max(0, min(100, percent)))

        return hook

    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        yt_dlp = _load_yt_dlp()
        _log("yt-dlp: extracting playlist")

        def extract() -> dict[str, Any] | None:
            with yt_dlp.YoutubeDL(self.playlist_options(cookie_source)) as ydl:
                return ydl.extract_info(playlist_url, download=False)

        info = await asyncio.to_thread(extract)
        _log("yt-dlp: playlist extraction returned")
        if not info:
            return []

        entries = info.get("entries") if isinstance(info, dict) else None
        if entries is None:
            entries = [info]

        tracks: list[MediaTrack] = []
        for entry in entries:
            if not entry:
                continue

            source_url = entry.get("url") or entry.get("webpage_url") or entry.get("id")
            if not source_url:
                continue

            title = entry.get("title") or entry.get("id") or "track"
            artist = entry.get("artist") or entry.get("uploader")
            bitrate = _entry_bitrate(entry)
            tracks.append(MediaTrack(str(source_url), str(title), artist, bitrate))

        return tracks

    async def source_bitrate(self, source_url: str, cookie_source: str | None = None) -> int | None:
        yt_dlp = _load_yt_dlp()
        _log(f"yt-dlp: resolving bitrate for {source_url}")

        def extract() -> dict[str, Any] | None:
            with yt_dlp.YoutubeDL(self.metadata_options(cookie_source)) as ydl:
                return ydl.extract_info(source_url, download=False)

        try:
            metadata = await asyncio.to_thread(extract)
        except Exception:
            _log(f"yt-dlp: bitrate resolve failed for {source_url}")
            return None

        if not isinstance(metadata, dict):
            return None
        _log(f"yt-dlp: bitrate resolve returned for {source_url}")
        return _entry_bitrate(metadata)

    async def download_audio(
        self,
        track: MediaTrack,
        work_dir: Path,
        progress: ProgressCallback,
        cookie_source: str | None = None,
    ) -> Path:
        yt_dlp = _load_yt_dlp()
        _log(f"yt-dlp: downloading {track.source_url}")
        work_dir.mkdir(parents=True, exist_ok=True)
        download_dir = work_dir / f"download-{uuid4().hex}"
        download_dir.mkdir(parents=True)
        before = _files_in(download_dir)

        def download() -> int:
            with yt_dlp.YoutubeDL(self.download_options(download_dir, progress, cookie_source)) as ydl:
                return ydl.download([track.source_url])

        result = await asyncio.to_thread(download)
        if result:
            raise RuntimeError(f"yt-dlp failed with exit code {result}")
        _log(f"yt-dlp: download returned for {track.source_url}")

        created = sorted(_files_in(download_dir) - before, key=lambda path: path.stat().st_mtime, reverse=True)
        if not created:
            raise RuntimeError("yt-dlp did not create an output file")
        return created[0]


class FfmpegEncoder:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def ensure_available(self) -> None:
        if shutil.which(self.ffmpeg_path) is None:
            raise RuntimeError(MISSING_FFMPEG_MESSAGE)

    def build_command(self, source: Path, output: Path, bitrate_kbps: int) -> list[str]:
        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(output),
        ]

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            process = await asyncio.create_subprocess_exec(
                *self.build_command(source_path, output_path, bitrate_kbps),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(MISSING_FFMPEG_MESSAGE) from exc
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
            raise RuntimeError(message or f"ffmpeg failed with exit code {process.returncode}")
        return output_path


def _load_yt_dlp():
    import yt_dlp

    return yt_dlp


def _cookie_options(cookie_source: str | None) -> dict[str, Any]:
    if not cookie_source or cookie_source == "auto":
        return {}
    return {"cookiesfrombrowser": (cookie_source,)}


def _bitrate_kbps(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _entry_bitrate(entry: dict[str, Any]) -> int | None:
    abr_candidates: list[int] = []
    top_level_abr = _bitrate_kbps(entry.get("abr"))
    if top_level_abr is not None:
        abr_candidates.append(top_level_abr)

    tbr_candidates: list[int] = []
    top_level_tbr = _bitrate_kbps(entry.get("tbr"))
    if top_level_tbr is not None and _is_audio_only(entry):
        tbr_candidates.append(top_level_tbr)

    for media_format in entry.get("formats") or []:
        if not isinstance(media_format, dict):
            continue
        if not _is_audio_bearing(media_format):
            continue

        format_abr = _bitrate_kbps(media_format.get("abr"))
        if format_abr is not None:
            abr_candidates.append(format_abr)
            continue

        format_tbr = _bitrate_kbps(media_format.get("tbr"))
        if format_tbr is not None and _is_audio_only(media_format):
            tbr_candidates.append(format_tbr)

    if abr_candidates:
        return max(abr_candidates)
    return max(tbr_candidates, default=None)


def _is_audio_bearing(entry: dict[str, Any]) -> bool:
    acodec = entry.get("acodec")
    return acodec is not None and acodec != "none"


def _is_audio_only(entry: dict[str, Any]) -> bool:
    if not _is_audio_bearing(entry):
        return False
    vcodec = entry.get("vcodec")
    return vcodec is None or vcodec == "none"


def _files_in(path: Path) -> set[Path]:
    return {item for item in path.iterdir() if item.is_file()}
