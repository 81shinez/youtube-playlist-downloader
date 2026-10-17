"""Cancellable subprocess adapters for the desktop worker."""

import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from youtube_music_downloader.media import FfmpegEncoder, MISSING_FFMPEG_MESSAGE, ProgressCallback
from youtube_music_downloader.models import MediaTrack
from youtube_music_downloader.desktop_runtime import worker_command


_STDERR_LIMIT = 64 * 1024
_EVENT_LIMIT = 8 * 1024 * 1024
_CLEANUP_TIMEOUT = 5
_MISSING = object()


def _timeout(value: float) -> float:
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Media operation timeout must be finite and positive")
    return value


def _media_command() -> list[str]:
    return worker_command('media-process')


async def _drain(stream: asyncio.StreamReader | None, tail: bytearray | None = None) -> None:
    if stream is None:
        return
    while chunk := await stream.read(8192):
        if tail is not None:
            tail.extend(chunk)
            del tail[:-_STDERR_LIMIT]


async def _read_events(stream: asyncio.StreamReader, progress: ProgressCallback | None) -> Any:
    result = _MISSING
    while True:
        try:
            line = await stream.readline()
        except ValueError as exc:
            raise RuntimeError("Media process response exceeds the size limit") from exc
        if not line:
            break
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeError) as exc:
            raise RuntimeError("Invalid media process response") from exc
        if not isinstance(event, dict):
            raise RuntimeError("Invalid media process response")
        kind = event.get("type")
        if kind == "error":
            raise RuntimeError(str(event.get("value", event.get("message", "Media process failed")))[-_STDERR_LIMIT:])
        if result is not _MISSING:
            raise RuntimeError("Unexpected media process response after result")
        if kind == "progress" and type(event.get("value")) is int:
            if progress is not None:
                progress(max(0, min(100, event["value"])))
        elif kind == "result" and "value" in event:
            result = event["value"]
        else:
            raise RuntimeError("Invalid media process response")
    if result is _MISSING:
        raise RuntimeError("Media process exited without a result")
    return result


async def _await_cleanup(task: asyncio.Task) -> None:
    # Shutdown may cancel the owning task again while its child is being reaped.
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    task.result()
    if cancelled:
        raise asyncio.CancelledError


async def _run_process(
    command: list[str],
    *,
    timeout: float,
    label: str,
    request: dict[str, Any] | None = None,
    progress: ProgressCallback | None = None,
    env: dict[str, str] | None = None,
) -> Any:
    stderr_tail = bytearray()
    stderr_task = None
    stdout_task = None
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE if request is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE if request is not None else asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        limit=_EVENT_LIMIT,
        env=env,
        **options,
    ))

    async def communicate() -> Any:
        nonlocal stderr_task, stdout_task
        # Shield creation so cancellation never loses a newly created process.
        process = await asyncio.shield(spawn)
        stderr_task = asyncio.create_task(_drain(process.stderr, stderr_tail))
        value = None
        if request is not None:
            stdout_task = asyncio.create_task(_read_events(process.stdout, progress))
            try:
                process.stdin.write((json.dumps(request, ensure_ascii=True) + "\n").encode("utf-8"))
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()
            value = await stdout_task
        await process.wait()
        await asyncio.shield(stderr_task)
        if process.returncode != 0:
            raise RuntimeError(f"{label} failed with exit code {process.returncode}")
        return value

    async def cleanup() -> None:
        try:
            process = await asyncio.wait_for(spawn, _CLEANUP_TIMEOUT)
        except Exception:
            return
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        if process.stdin is not None:
            process.stdin.close()
        if stdout_task is not None:
            stdout_task.cancel()
            await asyncio.gather(stdout_task, return_exceptions=True)
        # Drain even a rejected/oversized response: a full pipe can delay wait().
        try:
            await asyncio.wait_for(asyncio.gather(
                _drain(process.stdout),
                stderr_task if stderr_task is not None else _drain(process.stderr, stderr_tail),
                process.wait(),
            ), _CLEANUP_TIMEOUT)
        except TimeoutError:
            # Process has no public close(): close inherited pipes if EOF never arrives.
            process._transport.close()
            await asyncio.wait_for(process.wait(), _CLEANUP_TIMEOUT)

    def diagnostic(message: str) -> str:
        detail = stderr_tail.decode("utf-8", errors="replace").strip()
        return f"{message}\n{detail}" if detail else message

    try:
        try:
            return await asyncio.wait_for(communicate(), timeout)
        finally:
            await _await_cleanup(asyncio.create_task(cleanup()))
    except TimeoutError as exc:
        raise TimeoutError(diagnostic(f"{label} timed out after {timeout:g} seconds")) from exc
    except RuntimeError as exc:
        raise RuntimeError(diagnostic(str(exc))) from exc


class DesktopDownloader:
    def __init__(
        self, *, playlist_timeout: float = 90, metadata_timeout: float = 45, download_timeout: float = 600
    ):
        self.playlist_timeout = _timeout(playlist_timeout)
        self.metadata_timeout = _timeout(metadata_timeout)
        self.download_timeout = _timeout(download_timeout)

    async def _request(
        self, request: dict[str, Any], timeout: float, progress: ProgressCallback | None = None
    ) -> Any:
        env = None
        if not getattr(sys, "frozen", False):
            env = os.environ.copy()
            source_root = str(Path(__file__).resolve().parent.parent)
            env["PYTHONPATH"] = os.pathsep.join(filter(None, (source_root, env.get("PYTHONPATH"))))
        return await _run_process(
            _media_command(), timeout=timeout, label=request["operation"], request=request, progress=progress, env=env
        )

    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        value = await self._request(
            {"operation": "playlist_tracks", "playlist_url": playlist_url, "cookie_source": cookie_source},
            self.playlist_timeout,
        )
        if not isinstance(value, list):
            raise RuntimeError("Invalid playlist result from media process")
        try:
            return [MediaTrack(**entry) for entry in value]
        except TypeError as exc:
            raise RuntimeError("Invalid playlist result from media process") from exc

    async def source_bitrate(self, source_url: str, cookie_source: str | None = None) -> int | None:
        value = await self._request(
            {"operation": "source_bitrate", "source_url": source_url, "cookie_source": cookie_source},
            self.metadata_timeout,
        )
        if value is not None and type(value) is not int:
            raise RuntimeError("Invalid bitrate result from media process")
        return value

    async def download_audio(
        self, track: MediaTrack, work_dir: Path, progress: ProgressCallback, cookie_source: str | None = None
    ) -> Path:
        value = await self._request(
            {"operation": "download_audio", "track": asdict(track), "work_dir": str(work_dir),
             "cookie_source": cookie_source},
            self.download_timeout,
            progress,
        )
        if not isinstance(value, str) or not value:
            raise RuntimeError("Invalid download result from media process")
        return Path(value)


def resolve_ffmpeg(ffmpeg_path: str | None = None) -> str:
    """Use the audited packaged helper, with development-only fallbacks."""
    if ffmpeg_path is None:
        if getattr(sys, 'frozen', False):
            suffix = '.exe' if sys.platform == 'win32' else ''
            packaged = Path(sys._MEIPASS) / 'media' / ('ffmpeg' + suffix)
            if packaged.is_file():
                return str(packaged.resolve())
            raise RuntimeError(MISSING_FFMPEG_MESSAGE)
        try:
            import imageio_ffmpeg

            bundled = shutil.which(imageio_ffmpeg.get_ffmpeg_exe())
        except (ImportError, OSError, RuntimeError):
            bundled = None
        if bundled:
            return str(Path(bundled).resolve())
        ffmpeg_path = "ffmpeg"
    resolved = shutil.which(ffmpeg_path)
    if resolved is None:
        raise RuntimeError(MISSING_FFMPEG_MESSAGE)
    return str(Path(resolved).resolve())


class DesktopEncoder(FfmpegEncoder):
    def __init__(self, ffmpeg_path: str | None = None, *, timeout: float = 600):
        self.ffmpeg_path = ffmpeg_path
        self.timeout = _timeout(timeout)

    def ensure_available(self) -> None:
        self.ffmpeg_path = resolve_ffmpeg(self.ffmpeg_path)

    def build_command(self, source: Path, output: Path, bitrate_kbps: int) -> list[str]:
        self.ensure_available()
        command = super().build_command(source, output, bitrate_kbps)
        return [command[0], "-nostdin", "-hide_banner", "-loglevel", "error", *command[1:]]

    async def encode_mp3(self, source_path: Path, output_path: Path, bitrate_kbps: int) -> Path:
        self.ensure_available()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".ymd-", suffix=".mp3", dir=output_path.parent, delete=False) as file:
            partial_path = Path(file.name)
        try:
            command = self.build_command(source_path, partial_path, bitrate_kbps)
            try:
                await _run_process(command, timeout=self.timeout, label="ffmpeg")
            except FileNotFoundError as exc:
                raise RuntimeError(MISSING_FFMPEG_MESSAGE) from exc
            partial_path.replace(output_path)
        finally:
            partial_path.unlink(missing_ok=True)
        return output_path
