import asyncio
import concurrent.futures
import ipaddress
import json
import os
import re
import secrets
import tempfile
import threading
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.media import FfmpegEncoder, YtDlpDownloader
from youtube_music_downloader.models import Job, JobStatus, Track, TrackStatus


STATIC_DIR = Path(__file__).resolve().parent / "static"
OUTPUT_DIR_CHECK_TIMEOUT_SECONDS = 3.0
SUPPORTED_COOKIE_SOURCES = {"auto", "chrome", "edge", "firefox", "brave"}
DEFAULT_COOKIE_SOURCE = "auto"


def _log(message: str) -> None:
    print(f"[ymd] {time.strftime('%H:%M:%S')} {message}", flush=True)


class BackgroundJobRunner:
    def __init__(self):
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._closed = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run_loop, name="ymd-background-jobs", daemon=True)
        self._thread.start()
        self._ready.wait()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> concurrent.futures.Future:
        with self._lock:
            if self._closed or self._loop is None:
                coro.close()
                raise RuntimeError("Background job runner is closed")
            return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            loop = self._loop

        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()

        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()


def create_app(manager: JobManager | None = None, auto_start_jobs: bool = True) -> FastAPI:
    manager = manager or JobManager(YtDlpDownloader(), FfmpegEncoder())
    app = FastAPI(title="YouTube Music Downloader")
    launch_token = secrets.token_urlsafe(32)

    @app.middleware("http")
    async def guard_web_requests(request: Request, call_next):
        try:
            _validate_web_origin(request)
            if request.url.path.startswith("/api"):
                token = _single_header(request, "x-ymd-token") or ""
                if not secrets.compare_digest(token.encode("utf-8"), launch_token.encode("ascii")):
                    raise HTTPException(status_code=401, detail="Invalid or missing app token")
                if request.method not in {"GET", "HEAD", "OPTIONS"}:
                    content_type = _single_header(request, "content-type") or ""
                    if content_type.partition(";")[0].strip().lower() != "application/json":
                        raise HTTPException(status_code=415, detail="Content-Type must be application/json")
        except HTTPException as exc:
            response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        else:
            response = await call_next(request)

        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.state.manager = manager
    app.state.job_runner = BackgroundJobRunner()
    app.state.background_tasks = set()
    app.state.run_sync = lambda job_id: asyncio.run(manager.run_job(job_id))

    def schedule_background(coro) -> None:
        future = app.state.job_runner.submit(coro)
        app.state.background_tasks.add(future)

        def cleanup(done_future: concurrent.futures.Future) -> None:
            app.state.background_tasks.discard(done_future)
            if not done_future.cancelled():
                done_future.exception()

        future.add_done_callback(cleanup)

    def shutdown_background_runner() -> None:
        app.state.job_runner.shutdown()

    app.router.add_event_handler("shutdown", shutdown_background_runner)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/session-token", include_in_schema=False)
    async def session_token(request: Request):
        # A non-simple header prevents cross-origin no-cors reads in older browsers.
        if _single_header(request, "x-ymd-bootstrap") != "1" or not (
            _single_header(request, "sec-fetch-site") == "same-origin"
            or _single_header(request, "origin") is not None
        ):
            raise HTTPException(status_code=403, detail="Same-origin bootstrap required")
        return {"token": launch_token}

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/jobs/latest")
    async def latest_job():
        job = manager.latest_job()
        if job is None:
            raise _not_found("Job not found")
        return _serialize_job(job)

    @app.post("/api/jobs")
    async def create_job(request: Request):
        data = await _json_object(request)
        _log("POST /api/jobs: request body parsed")
        playlist_url = _validated_playlist_url(_required_string(data, "playlist_url"))
        _log("POST /api/jobs: playlist URL validated")
        output_dir = await _validated_output_dir(_required_string(data, "output_dir"))
        _log(f"POST /api/jobs: output directory validated ({output_dir})")
        output_mode = _validated_output_mode(_required_string(data, "output_mode"))
        concurrency = _validated_concurrency(data.get("concurrency"))
        if "cookie_source" in data:
            cookie_source = _validated_cookie_source(data.get("cookie_source"))
        else:
            cookie_source = DEFAULT_COOKIE_SOURCE
        _log(
            "POST /api/jobs: options validated "
            f"mode={output_mode.value} concurrency={concurrency} cookie_source={cookie_source or 'none'}"
        )
        try:
            _ensure_encoder_available(manager)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job = manager.create_job(playlist_url, output_dir, output_mode, concurrency, cookie_source)
        _log(f"POST /api/jobs: created {job.id}")
        if auto_start_jobs:
            schedule_background(manager.run_job(job.id))
            _log(f"POST /api/jobs: scheduled background run for {job.id}")
        return {"job_id": job.id, "status": job.status.value}

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        return _serialize_job(_get_job_or_404(manager, job_id))

    @app.post("/api/jobs/{job_id}/tracks/{track_id}/retry")
    async def retry_track(job_id: str, track_id: str, request: Request):
        data = await _optional_json_object(request)
        try:
            if "cookie_source" in data:
                track = manager.retry_track(job_id, track_id, _validated_cookie_source(data.get("cookie_source")))
            else:
                track = manager.retry_track(job_id, track_id)
        except KeyError:
            raise _not_found("Job or track not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if auto_start_jobs:
            schedule_background(manager.run_pending(job_id))
        return _serialize_track(track)

    @app.post("/api/jobs/{job_id}/retry-failed")
    async def retry_failed(job_id: str, request: Request):
        data = await _optional_json_object(request)
        try:
            if "cookie_source" in data:
                reset_count = manager.retry_failed(job_id, _validated_cookie_source(data.get("cookie_source")))
            else:
                reset_count = manager.retry_failed(job_id)
        except KeyError:
            raise _not_found("Job not found") from None

        if auto_start_jobs and reset_count > 0:
            schedule_background(manager.run_pending(job_id))
        return {"reset_count": reset_count}

    @app.post("/api/jobs/{job_id}/pause")
    async def pause_job(job_id: str):
        try:
            job = manager.pause_job(job_id)
        except KeyError:
            raise _not_found("Job not found") from None
        return _serialize_job(job)

    @app.post("/api/jobs/{job_id}/resume")
    async def resume_job(job_id: str):
        try:
            job = manager.resume_job(job_id)
        except KeyError:
            raise _not_found("Job not found") from None

        if auto_start_jobs:
            schedule_background(manager.run_pending(job_id))
        return _serialize_job(job)

    @app.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str):
        try:
            job = manager.cancel_job(job_id)
        except KeyError:
            raise _not_found("Job not found") from None
        return _serialize_job(job)

    @app.post("/api/jobs/{job_id}/cookie-source")
    async def update_cookie_source(job_id: str, request: Request):
        data = await _json_object(request)
        if "cookie_source" not in data:
            raise HTTPException(status_code=400, detail="cookie_source is required")

        try:
            job = manager.set_cookie_source(job_id, _validated_cookie_source(data.get("cookie_source")))
            restart_failed_playlist = job.status is JobStatus.FAILED and not job.tracks
            reset_count = 0
            if not restart_failed_playlist and job.status not in {JobStatus.CANCELED, JobStatus.PAUSED}:
                reset_count = manager.retry_failed(job_id)
        except KeyError:
            raise _not_found("Job not found") from None

        if auto_start_jobs:
            if restart_failed_playlist:
                schedule_background(manager.run_job(job_id))
            elif reset_count > 0:
                schedule_background(manager.run_pending(job_id))
        return _serialize_job(job)

    @app.post("/api/jobs/{job_id}/tracks/{track_id}/cancel")
    async def cancel_track(job_id: str, track_id: str):
        try:
            track = manager.cancel_track(job_id, track_id)
        except KeyError:
            raise _not_found("Job or track not found") from None
        return _serialize_track(track)

    @app.post("/api/jobs/{job_id}/open-output-folder")
    async def open_output_folder(job_id: str, request: Request):
        _ensure_local_request(request)
        job = _get_job_or_404(manager, job_id)
        _validate_local_output_path(str(job.output_dir))
        if not job.output_dir.exists() or not job.output_dir.is_dir():
            raise HTTPException(status_code=400, detail="Output folder is not available")

        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise HTTPException(status_code=501, detail="Opening folders is only supported on Windows")

        try:
            startfile(str(job.output_dir))
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"Could not open output folder: {exc}") from exc
        return {"opened": True}

    return app


def _single_header(request: Request, name: str) -> str | None:
    values = request.headers.getlist(name)
    if len(values) > 1:
        raise HTTPException(status_code=403, detail="Ambiguous security headers")
    return values[0] if values else None


def _loopback_authority(authority: str, scheme: str) -> tuple[str, int]:
    # Validate the entire authority before parsing; never resolve a supplied hostname.
    if scheme not in {"http", "https"} or not re.fullmatch(
        r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?", authority
    ):
        raise HTTPException(status_code=403, detail="Invalid loopback Host or Origin")
    try:
        parsed = urlparse(f"{scheme}://{authority}")
        host = parsed.hostname or ""
        port = parsed.port if parsed.port is not None else (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid loopback Host or Origin") from exc
    if port == 0 or not _is_loopback_host(host):
        raise HTTPException(status_code=403, detail="Only loopback Host and Origin are allowed")
    return host, port


def _validate_web_origin(request: Request) -> None:
    scheme = request.url.scheme
    authority = _loopback_authority(_single_header(request, "host") or "", scheme)
    origin = _single_header(request, "origin")
    if origin is not None:
        origin_scheme, separator, origin_host = origin.partition("://")
        if separator != "://" or origin_scheme != scheme or _loopback_authority(origin_host, origin_scheme) != authority:
            raise HTTPException(status_code=403, detail="Same-origin requests required")
    fetch_site = _single_header(request, "sec-fetch-site")
    allowed_sites = {None, "same-origin"}
    if not request.url.path.startswith("/api") and request.url.path != "/session-token":
        allowed_sites.add("none")
    if fetch_site not in allowed_sites:
        raise HTTPException(status_code=403, detail="Same-origin requests required")


async def _json_object(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    return data


async def _optional_json_object(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body.strip():
        return {}

    try:
        data = json.loads(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    return data


def _required_string(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{field} is required")
    return value


def _validated_output_mode(value: str) -> OutputMode:
    try:
        return OutputMode.from_api_value(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validated_playlist_url(value: str) -> str:
    try:
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="playlist_url must be a valid URL") from exc

    query = parse_qs(parsed.query)

    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="playlist_url must use http or https")
    if host not in {"music.youtube.com", "www.youtube.com", "youtube.com", "m.youtube.com"}:
        raise HTTPException(status_code=400, detail="playlist_url must be a YouTube URL")
    if parsed.path == "/playlist" and query.get("list"):
        return value
    if parsed.path == "/watch" and query.get("list"):
        return value
    raise HTTPException(status_code=400, detail="playlist_url must be a YouTube playlist URL")


def _validated_concurrency(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=400, detail="concurrency must be an integer from 1 to 4")
    if value < 1 or value > 4:
        raise HTTPException(status_code=400, detail="concurrency must be an integer from 1 to 4")
    return value


def _validated_cookie_source(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="cookie_source must be a supported browser or empty")

    normalized = value.strip().lower()
    if normalized in {"", "none"}:
        return None
    if normalized not in SUPPORTED_COOKIE_SOURCES:
        raise HTTPException(status_code=400, detail="cookie_source must be auto, chrome, edge, firefox, brave, or empty")
    return normalized


async def _validated_output_dir(value: str) -> Path:
    _validate_local_output_path(value)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_validated_output_dir_sync, value),
            timeout=OUTPUT_DIR_CHECK_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=400, detail="output_dir validation timed out") from exc


def _validated_output_dir_sync(value: str) -> Path:
    _validate_local_output_path(value)
    output_dir = Path(value).expanduser()
    _validate_local_output_path(str(output_dir))
    if not output_dir.exists():
        raise HTTPException(status_code=400, detail="output_dir must exist")
    if not output_dir.is_dir():
        raise HTTPException(status_code=400, detail="output_dir must be a directory")
    if not _is_writable_dir(output_dir):
        raise HTTPException(status_code=400, detail="output_dir must be writable")
    return output_dir


def _validate_local_output_path(value: str) -> None:
    # Apply Windows syntax rules on every OS, before any stat/open/resolve call.
    normalized = value.replace("\\", "/").lower()
    path_without_drive = re.sub(r"^[a-z]:", "", normalized)
    device_names = {"con", "prn", "aux", "nul", "conin$", "conout$"}
    device_names.update(f"{prefix}{number}" for prefix in ("com", "lpt") for number in "123456789\u00b9\u00b2\u00b3")
    if (
        normalized.startswith(("//", "/??/", "/device/", "/global??/", "/dosdevices/"))
        or ":" in path_without_drive
        or any(ord(char) < 32 for char in value)
        or any(part.split(".", 1)[0].rstrip(" ") in device_names for part in path_without_drive.split("/"))
    ):
        raise HTTPException(status_code=400, detail="output_dir must be a local directory, not a network or device path")


def _ensure_encoder_available(manager: JobManager) -> None:
    ensure_available = getattr(manager, "ensure_encoder_available", None)
    if ensure_available is not None:
        ensure_available()


def _is_writable_dir(path: Path) -> bool:
    try:
        with tempfile.NamedTemporaryFile(prefix=".ymd-write-", dir=path, delete=True):
            return True
    except OSError:
        return False


def _ensure_local_request(request: Request) -> None:
    host = request.client.host if request.client else ""
    if _is_loopback_host(host):
        return
    raise HTTPException(status_code=403, detail="open-output-folder is only available to local clients")


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _get_job_or_404(manager: JobManager, job_id: str) -> Job:
    try:
        return manager.get_job(job_id)
    except KeyError:
        raise _not_found("Job not found") from None


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def _serialize_job(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "playlist_url": job.playlist_url,
        "output_dir": str(job.output_dir),
        "output_mode": job.output_mode.value,
        "concurrency": job.concurrency,
        "cookie_source": job.cookie_source,
        "status": job.status.value,
        "error_message": job.error_message,
        "tracks": [_serialize_track(track) for track in job.tracks],
        "summary": _serialize_summary(job.tracks),
    }


def _serialize_track(track: Track) -> dict[str, Any]:
    return {
        "id": track.id,
        "source_url": track.source_url,
        "title": track.title,
        "artist": track.artist,
        "source_bitrate_kbps": track.source_bitrate_kbps,
        "target_bitrate_kbps": track.target_bitrate_kbps,
        "status": track.status.value,
        "progress": track.progress,
        "output_path": track.output_path,
        "error_message": track.error_message,
        "attempts": track.attempts,
    }


def _serialize_summary(tracks: list[Track]) -> dict[str, int]:
    summary = {"total": len(tracks)}
    for status in TrackStatus:
        summary[status.value] = sum(1 for track in tracks if track.status is status)
    return summary
