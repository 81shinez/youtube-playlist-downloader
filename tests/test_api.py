import asyncio
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import youtube_music_downloader.api as api_module
from youtube_music_downloader.bitrate import OutputMode
from youtube_music_downloader.api import create_app
from youtube_music_downloader.job_manager import JobManager
from youtube_music_downloader.models import JobStatus, MediaTrack, TrackStatus


class FakeDownloader:
    def __init__(self, tracks: list[MediaTrack] | None = None):
        self.tracks = tracks or [
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

    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        return self.tracks

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


class SlowDownloader(FakeDownloader):
    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        await asyncio.sleep(0.5)
        return []


class CookieGateDownloader(FakeDownloader):
    def __init__(self):
        super().__init__()
        self.playlist_cookie_sources: list[str | None] = []

    async def playlist_tracks(self, playlist_url: str, cookie_source: str | None = None) -> list[MediaTrack]:
        self.playlist_cookie_sources.append(cookie_source)
        if cookie_source != "chrome":
            raise RuntimeError("auth required")
        return self.tracks


class BlockingRunManager:
    def __init__(self):
        self.jobs = {}

    def create_job(
        self,
        playlist_url: str,
        output_dir: Path,
        output_mode: OutputMode,
        concurrency: int,
        cookie_source: str | None = None,
    ):
        job = api_module.Job(playlist_url, output_dir, output_mode, concurrency, cookie_source=cookie_source)
        self.jobs[job.id] = job
        return job

    def get_job(self, job_id: str):
        return self.jobs[job_id]

    async def run_job(self, job_id: str) -> None:
        time.sleep(0.5)
        self.jobs[job_id].status = JobStatus.COMPLETED

    async def run_pending(self, job_id: str) -> None:
        await self.run_job(job_id)


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


def build_app(*, auto_start_jobs: bool = False, encoder: FakeEncoder | None = None):
    encoder = encoder or FakeEncoder()
    manager = JobManager(FakeDownloader(), encoder)
    app = create_app(manager=manager, auto_start_jobs=auto_start_jobs)
    return app, manager, encoder


@contextmanager
def authenticated_client(app, **kwargs):
    with TestClient(app, base_url="http://127.0.0.1:8000", **kwargs) as client:
        response = client.get("/session-token", headers={
            "Sec-Fetch-Site": "same-origin", "X-YMD-Bootstrap": "1",
        })
        assert response.status_code == 200
        client.headers.update({
            "X-YMD-Token": response.json()["token"],
            "Origin": "http://127.0.0.1:8000",
            "Content-Type": "application/json",
        })
        yield client


def wait_for(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate()


def create_job(
    client: TestClient,
    output_dir: Path,
    *,
    playlist_url: str = "https://music.youtube.com/playlist?list=abc",
    output_mode: str = "192",
    cookie_source: str | None = None,
) -> dict:
    payload = {
        "playlist_url": playlist_url,
        "output_dir": str(output_dir),
        "output_mode": output_mode,
        "concurrency": 2,
    }
    if cookie_source is not None:
        payload["cookie_source"] = cookie_source

    response = client.post(
        "/api/jobs",
        json=payload,
    )
    assert response.status_code == 200
    return response.json()


def test_create_job_accepts_youtube_music_playlist_url(tmp_path: Path):
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        payload = create_job(
            client,
            tmp_path,
            playlist_url="https://music.youtube.com/playlist?list=PL123",
        )

    assert payload["status"] == "queued"


def test_create_job_success_exposes_manager_and_serves_index(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        payload = create_job(client, tmp_path, output_mode="max")
        index = client.get("/")

    assert app.state.manager is manager
    assert payload["job_id"].startswith("job_")
    assert payload["status"] == "queued"
    assert index.status_code == 200
    assert "YouTube Music Downloader" in index.text


def test_latest_job_endpoint_returns_newest_active_job(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        completed = create_job(client, tmp_path, playlist_url="https://music.youtube.com/playlist?list=done")
        manager.get_job(completed["job_id"]).status = JobStatus.COMPLETED
        active = create_job(client, tmp_path, playlist_url="https://music.youtube.com/playlist?list=active")
        response = client.get("/api/jobs/latest")

    assert response.status_code == 200
    assert response.json()["id"] == active["job_id"]


def test_latest_job_endpoint_returns_404_without_jobs():
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        response = client.get("/api/jobs/latest")

    assert response.status_code == 404


def test_create_job_accepts_cookie_source_and_serializes_it(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path, cookie_source="chrome")
        response = client.get(f"/api/jobs/{created['job_id']}")

    assert manager.get_job(created["job_id"]).cookie_source == "chrome"
    assert response.status_code == 200
    assert response.json()["cookie_source"] == "chrome"


def test_create_job_defaults_to_auto_cookie_source(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        response = client.get(f"/api/jobs/{created['job_id']}")

    assert manager.get_job(created["job_id"]).cookie_source == "auto"
    assert response.status_code == 200
    assert response.json()["cookie_source"] == "auto"


def test_create_job_rejects_unavailable_encoder_before_creating_job(tmp_path: Path):
    app, manager, _encoder = build_app(encoder=MissingEncoder())

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "ffmpeg executable is not available"
    assert manager.latest_job() is None


def test_create_job_auto_start_returns_before_background_work_finishes(tmp_path: Path):
    manager = JobManager(SlowDownloader(), FakeEncoder())
    app = create_app(manager=manager, auto_start_jobs=True)

    with authenticated_client(app) as client:
        started = time.perf_counter()
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
            },
        )
        elapsed = time.perf_counter() - started
        job_id = response.json()["job_id"]

        assert response.status_code == 200
        assert elapsed < 0.25
        assert manager.get_job(job_id).status in {JobStatus.QUEUED, JobStatus.ANALYZING}
        wait_for(lambda: manager.get_job(job_id).status is JobStatus.COMPLETED)


def test_create_job_times_out_slow_output_dir_validation(monkeypatch, tmp_path: Path):
    app, _manager, _encoder = build_app()

    def slow_writable_check(_path: Path) -> bool:
        time.sleep(0.5)
        return True

    monkeypatch.setattr(api_module, "OUTPUT_DIR_CHECK_TIMEOUT_SECONDS", 0.05, raising=False)
    monkeypatch.setattr(api_module, "_is_writable_dir", slow_writable_check)

    with authenticated_client(app) as client:
        started = time.perf_counter()
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
            },
        )
        elapsed = time.perf_counter() - started

    assert response.status_code == 400
    assert "timed out" in response.json()["detail"]
    assert elapsed < 0.25


def test_auto_started_job_cannot_block_followup_requests():
    manager = BlockingRunManager()
    app = create_app(manager=manager, auto_start_jobs=True)

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(Path.cwd()),
                "output_mode": "192",
                "concurrency": 1,
            },
        )

        started = time.perf_counter()
        index = client.get("/")
        elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert index.status_code == 200
    assert elapsed < 0.25


def test_create_job_rejects_missing_output_dir(tmp_path: Path):
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path / "missing"),
                "output_mode": "192",
                "concurrency": 1,
            },
        )

    assert response.status_code == 400
    assert "must exist" in response.json()["detail"]


def test_create_job_rejects_invalid_output_mode(tmp_path: Path):
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "320",
                "concurrency": 1,
            },
        )

    assert response.status_code == 400
    assert "Unsupported output mode" in response.json()["detail"]


def test_create_job_rejects_invalid_cookie_source(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
                "cookie_source": "opera",
            },
        )

    assert response.status_code == 400
    assert "cookie_source" in response.json()["detail"]
    assert manager._jobs == {}


@pytest.mark.parametrize(
    "playlist_url",
    [
        "music.youtube.com/playlist?list=abc",
        "https://example.com/playlist?list=abc",
        "ftp://music.youtube.com/playlist?list=abc",
        "https://music.youtube.com/watch?v=abc",
    ],
)
def test_create_job_rejects_invalid_playlist_urls(tmp_path: Path, playlist_url: str):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": playlist_url,
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
            },
        )

    assert response.status_code == 400
    assert "playlist_url" in response.json()["detail"]
    assert manager._jobs == {}


def test_create_job_rejects_malformed_playlist_url_with_400(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://[music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
            },
        )

    assert response.status_code == 400
    assert "playlist_url" in response.json()["detail"]
    assert manager._jobs == {}


def test_manual_run_then_get_job_returns_tracks_and_summary(tmp_path: Path):
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        app.state.run_sync(created["job_id"])
        response = client.get(f"/api/jobs/{created['job_id']}")

    payload = response.json()
    assert response.status_code == 200
    assert payload["id"] == created["job_id"]
    assert payload["status"] == "completed"
    assert payload["output_mode"] == OutputMode.MP3_192.value
    assert payload["summary"] == {
        "total": 2,
        "queued": 0,
        "analyzing": 0,
        "downloading": 0,
        "converting": 0,
        "completed": 2,
        "failed": 0,
        "canceled": 0,
    }
    assert [track["title"] for track in payload["tracks"]] == ["One", "Two"]
    assert [track["status"] for track in payload["tracks"]] == ["completed", "completed"]
    assert all(track["output_path"].endswith(".mp3") for track in payload["tracks"])


def test_retry_failed_endpoint_resets_and_auto_runs_failed_tracks(tmp_path: Path):
    encoder = FakeEncoder()
    encoder.fail_titles.update({"One", "Two"})
    app, manager, _encoder = build_app(auto_start_jobs=True, encoder=encoder)

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        wait_for(
            lambda: [track.status for track in manager.get_job(created["job_id"]).tracks]
            == [TrackStatus.FAILED, TrackStatus.FAILED]
        )

        encoder.fail_titles.clear()
        response = client.post(f"/api/jobs/{created['job_id']}/retry-failed")
        wait_for(
            lambda: [track.status for track in manager.get_job(created["job_id"]).tracks]
            == [TrackStatus.COMPLETED, TrackStatus.COMPLETED]
        )

    assert response.status_code == 200
    assert response.json() == {"reset_count": 2}
    assert [track.status for track in manager.get_job(created["job_id"]).tracks] == [
        TrackStatus.COMPLETED,
        TrackStatus.COMPLETED,
    ]


def test_retry_track_endpoint_resets_track_and_auto_runs_it(tmp_path: Path):
    encoder = FakeEncoder()
    encoder.fail_titles.add("One")
    app, manager, _encoder = build_app(auto_start_jobs=True, encoder=encoder)

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        wait_for(lambda: manager.get_job(created["job_id"]).tracks)
        wait_for(lambda: manager.get_job(created["job_id"]).tracks[0].status is TrackStatus.FAILED)
        failed_track = manager.get_job(created["job_id"]).tracks[0]

        encoder.fail_titles.clear()
        response = client.post(f"/api/jobs/{created['job_id']}/tracks/{failed_track.id}/retry")
        wait_for(lambda: manager.get_track(created["job_id"], failed_track.id).status is TrackStatus.COMPLETED)

    payload = response.json()
    retried = manager.get_track(created["job_id"], failed_track.id)
    assert response.status_code == 200
    assert payload["id"] == failed_track.id
    assert payload["status"] == "queued"
    assert retried.status is TrackStatus.COMPLETED
    assert retried.attempts == 2


def test_retry_failed_endpoint_updates_cookie_source_override(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        track = manager.add_track(
            created["job_id"],
            MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None),
        )
        track.status = TrackStatus.FAILED
        response = client.post(f"/api/jobs/{created['job_id']}/retry-failed", json={"cookie_source": "chrome"})

    assert response.status_code == 200
    assert manager.get_job(created["job_id"]).cookie_source == "chrome"
    assert manager.get_track(created["job_id"], track.id).status is TrackStatus.QUEUED


def test_retry_track_endpoint_updates_cookie_source_override(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        track = manager.add_track(
            created["job_id"],
            MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None),
        )
        track.status = TrackStatus.FAILED
        response = client.post(
            f"/api/jobs/{created['job_id']}/tracks/{track.id}/retry",
            json={"cookie_source": "edge"},
        )

    assert response.status_code == 200
    assert manager.get_job(created["job_id"]).cookie_source == "edge"
    assert manager.get_track(created["job_id"], track.id).status is TrackStatus.QUEUED


def test_cookie_source_endpoint_updates_existing_job(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        response = client.post(f"/api/jobs/{created['job_id']}/cookie-source", json={"cookie_source": "chrome"})

    assert response.status_code == 200
    assert response.json()["cookie_source"] == "chrome"
    assert manager.get_job(created["job_id"]).cookie_source == "chrome"


def test_cookie_source_endpoint_can_clear_cookie_source(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path, cookie_source="chrome")
        response = client.post(f"/api/jobs/{created['job_id']}/cookie-source", json={"cookie_source": ""})

    assert response.status_code == 200
    assert response.json()["cookie_source"] is None
    assert manager.get_job(created["job_id"]).cookie_source is None


def test_cookie_source_endpoint_rejects_missing_cookie_source(tmp_path: Path):
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        response = client.post(f"/api/jobs/{created['job_id']}/cookie-source", json={})

    assert response.status_code == 400
    assert "cookie_source" in response.json()["detail"]


def test_cookie_source_endpoint_rejects_invalid_cookie_source(tmp_path: Path):
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        response = client.post(f"/api/jobs/{created['job_id']}/cookie-source", json={"cookie_source": "opera"})

    assert response.status_code == 400
    assert "cookie_source" in response.json()["detail"]


def test_cookie_source_endpoint_retries_failed_tracks_and_auto_runs(tmp_path: Path):
    encoder = FakeEncoder()
    encoder.fail_titles.update({"One", "Two"})
    app, manager, _encoder = build_app(auto_start_jobs=True, encoder=encoder)

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        wait_for(
            lambda: [track.status for track in manager.get_job(created["job_id"]).tracks]
            == [TrackStatus.FAILED, TrackStatus.FAILED]
        )

        encoder.fail_titles.clear()
        response = client.post(f"/api/jobs/{created['job_id']}/cookie-source", json={"cookie_source": "chrome"})
        wait_for(
            lambda: [track.status for track in manager.get_job(created["job_id"]).tracks]
            == [TrackStatus.COMPLETED, TrackStatus.COMPLETED]
        )

    assert response.status_code == 200
    assert manager.get_job(created["job_id"]).cookie_source == "chrome"


def test_cookie_source_endpoint_restarts_failed_playlist_analysis(tmp_path: Path):
    downloader = CookieGateDownloader()
    manager = JobManager(downloader, FakeEncoder())
    app = create_app(manager=manager, auto_start_jobs=True)

    with authenticated_client(app) as client:
        response = client.post(
            "/api/jobs",
            json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": str(tmp_path),
                "output_mode": "192",
                "concurrency": 1,
                "cookie_source": "",
            },
        )
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        wait_for(lambda: manager.get_job(job_id).status is JobStatus.FAILED)

        update = client.post(f"/api/jobs/{job_id}/cookie-source", json={"cookie_source": "chrome"})
        wait_for(lambda: manager.get_job(job_id).status is JobStatus.COMPLETED)

    assert update.status_code == 200
    assert downloader.playlist_cookie_sources == [None, "chrome"]
    assert [track.status for track in manager.get_job(job_id).tracks] == [
        TrackStatus.COMPLETED,
        TrackStatus.COMPLETED,
    ]


def test_cancel_track_endpoint_marks_track_canceled(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        track = manager.add_track(
            created["job_id"],
            MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None),
        )
        response = client.post(f"/api/jobs/{created['job_id']}/tracks/{track.id}/cancel")

    payload = response.json()
    assert response.status_code == 200
    assert payload["id"] == track.id
    assert payload["status"] == "canceled"


def test_pause_resume_and_cancel_job_endpoints(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        track = manager.add_track(
            created["job_id"],
            MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None),
        )

        pause = client.post(f"/api/jobs/{created['job_id']}/pause")
        resume = client.post(f"/api/jobs/{created['job_id']}/resume")
        cancel = client.post(f"/api/jobs/{created['job_id']}/cancel")

    assert pause.status_code == 200
    assert pause.json()["status"] == "paused"
    assert resume.status_code == 200
    assert resume.json()["status"] == "running"
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "canceled"
    assert manager.get_track(created["job_id"], track.id).status is TrackStatus.CANCELED


def test_retry_track_rejects_non_retryable_track(tmp_path: Path):
    app, manager, _encoder = build_app()

    with authenticated_client(app) as client:
        created = create_job(client, tmp_path)
        track = manager.add_track(
            created["job_id"],
            MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None),
        )
        response = client.post(f"/api/jobs/{created['job_id']}/tracks/{track.id}/retry")

    assert response.status_code == 400
    assert "Only failed or completed tracks can be retried" in response.json()["detail"]


def test_open_output_folder_rejects_non_loopback_without_startfile(tmp_path: Path, monkeypatch):
    app, _manager, _encoder = build_app()
    opened: list[str] = []
    monkeypatch.setattr(api_module.os, "startfile", lambda path: opened.append(path), raising=False)

    with authenticated_client(app, client=("203.0.113.10", 50000)) as client:
        created = create_job(client, tmp_path)
        response = client.post(f"/api/jobs/{created['job_id']}/open-output-folder")

    assert response.status_code == 403
    assert "local" in response.json()["detail"]
    assert opened == []


def test_open_output_folder_allows_loopback_client(tmp_path: Path, monkeypatch):
    app, _manager, _encoder = build_app()
    opened: list[str] = []
    monkeypatch.setattr(api_module.os, "startfile", lambda path: opened.append(path), raising=False)

    with authenticated_client(app, client=("127.0.0.1", 50000)) as client:
        created = create_job(client, tmp_path)
        response = client.post(f"/api/jobs/{created['job_id']}/open-output-folder")

    assert response.status_code == 200
    assert response.json() == {"opened": True}
    assert opened == [str(tmp_path)]


def test_missing_job_returns_404():
    app, _manager, _encoder = build_app()

    with authenticated_client(app) as client:
        response = client.get("/api/jobs/job_missing")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
