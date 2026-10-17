from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import youtube_music_downloader.api as api_module
from test_api import authenticated_client, build_app, create_job
from youtube_music_downloader.models import MediaTrack, TrackStatus


BASE_URL = "http://127.0.0.1:8000"
BOOTSTRAP_HEADERS = {"Sec-Fetch-Site": "same-origin", "X-YMD-Bootstrap": "1"}
ACTION_PATHS = [
    "/api/jobs", "/api/jobs/missing/pause", "/api/jobs/missing/resume",
    "/api/jobs/missing/cancel", "/api/jobs/missing/retry-failed",
    "/api/jobs/missing/cookie-source", "/api/jobs/missing/open-output-folder",
    "/api/jobs/missing/tracks/missing/retry", "/api/jobs/missing/tracks/missing/cancel",
]
UNSAFE_PATHS = [
    r"\\server\share", "//server/share", r"\/server/share", r"/\server/share",
    r"\\?\UNC\server\share", "//?/UNC/server/share", r"\\?\C:\Music", "//?/C:/Music",
    r"\\.\pipe\music", "//./pipe/music", r"\??\C:\Music", "/??/C:/Music",
    r"\Device\HarddiskVolume1\Music", "/Device/HarddiskVolume1/Music",
    r"\GLOBAL??\C:\Music", r"\DosDevices\C:\Music", "smb://server/share",
    "file://server/share", "https://server/share", "NUL", "C:/Music/CON.txt", "C:/AUX",
]


@pytest.mark.parametrize("method,path", [
    ("GET", "/api"), ("GET", "/api/jobs/latest"), ("GET", "/api/jobs/missing"),
    ("GET", "/api/not-a-route"), ("HEAD", "/api/jobs/latest"),
    ("OPTIONS", "/api/jobs"), *[("POST", path) for path in ACTION_PATHS],
])
@pytest.mark.parametrize("token", [None, "wrong-token", "non-ascii-\xff"])
def test_every_api_request_requires_launch_token(method, path, token):
    app, manager, _ = build_app()
    headers = {"Origin": BASE_URL, "Content-Type": "application/json"}
    if token is not None:
        headers["X-YMD-Token"] = token.encode("latin-1")
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.request(method, path, headers=headers, content="{}")
    assert response.status_code == 401
    assert manager.latest_job() is None


@pytest.mark.parametrize("host", [
    "attacker.example", "127.0.0.1.attacker.example", "localhost.attacker.example",
    "192.168.1.10:8000", "0.0.0.0:8000", "localhost.:8000", "127.1:8000",
    "2130706433:8000", "127.0.0.1:bad", "127.0.0.1:65536", "127.0.0.1:",
    "user@127.0.0.1:8000", "127.0.0.1:8000/path", "[::]:8000", "[::1]junk:8000",
    "127.0.0.1:8000,attacker.example", "127.0.0.1:8000 ", "", "[::1", "[invalid]:8000",
])
@pytest.mark.parametrize("path", ["/", "/session-token", "/api/jobs/latest"])
def test_invalid_host_rejected_before_routing(host, path):
    app, _, _ = build_app()
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get(path, headers={**BOOTSTRAP_HEADERS, "Host": host})
    assert response.status_code == 403


@pytest.mark.parametrize("origin", [
    "https://attacker.example", "null", "http://localhost:8000", "http://127.0.0.1:8001",
    "https://127.0.0.1:8000", "http://127.0.0.1:8000/", "http://127.0.0.1:8000?x=1",
    "http://127.0.0.1:8000#x", "http://user@127.0.0.1:8000", " http://127.0.0.1:8000",
    "http://127.0.0.1:8000 http://attacker.example", "",
])
def test_cross_origin_read_and_write_rejected_even_with_token(origin):
    app, manager, _ = build_app()
    with authenticated_client(app) as client:
        for method in ("GET", "POST"):
            response = client.request(method, "/api/jobs/latest", headers={"Origin": origin})
            assert response.status_code == 403
    assert manager.latest_job() is None


@pytest.mark.parametrize("site", ["same-site", "cross-site", "none"])
def test_api_rejects_other_fetch_sites_without_origin_even_with_token(site):
    app, _, _ = build_app()
    with authenticated_client(app) as client:
        del client.headers["Origin"]
        response = client.get("/api/jobs/latest", headers={"Sec-Fetch-Site": site})
    assert response.status_code == 403


def test_token_in_query_is_not_authentication():
    app, _, _ = build_app()
    with authenticated_client(app) as client:
        token = client.headers.pop("X-YMD-Token")
        response = client.get("/api/jobs/latest", params={"token": token})
    assert response.status_code == 401


def test_duplicate_token_and_content_type_are_rejected():
    app, _, _ = build_app()
    with authenticated_client(app) as client:
        token = client.headers.pop("X-YMD-Token")
        response = client.get("/api/jobs/latest", headers=[("X-YMD-Token", token), ("X-YMD-Token", token)])
        assert response.status_code == 403
        response = client.post("/api/jobs", content="{}", headers=[
            ("X-YMD-Token", token), ("Content-Type", "application/json"), ("Content-Type", "text/plain"),
        ])
        assert response.status_code == 403


@pytest.mark.parametrize("headers", [
    {}, {"Origin": BASE_URL}, {"X-YMD-Bootstrap": "1"},
    {**BOOTSTRAP_HEADERS, "Origin": "null"},
    {**BOOTSTRAP_HEADERS, "Origin": "https://attacker.example"},
    {**BOOTSTRAP_HEADERS, "Sec-Fetch-Site": "cross-site"},
    {**BOOTSTRAP_HEADERS, "Sec-Fetch-Site": "same-site"},
    {**BOOTSTRAP_HEADERS, "Sec-Fetch-Site": "none"},
])
def test_bootstrap_is_same_origin_only(headers):
    app, _, _ = build_app()
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/session-token", headers=headers)
    assert response.status_code == 403
    assert "token" not in response.json()
    assert "access-control-allow-origin" not in response.headers


def test_bootstrap_token_is_launch_scoped_not_cached_or_logged(capsys):
    tokens = []
    for _ in range(2):
        app, _, _ = build_app()
        with TestClient(app, base_url=BASE_URL) as client:
            response = client.get("/session-token", headers=BOOTSTRAP_HEADERS)
            assert response.status_code == 200
            token = response.json()["token"]
            assert len(token) >= 43
            assert client.get("/session-token", headers=BOOTSTRAP_HEADERS).json()["token"] == token
            for path in ("/", "/static/index.html", "/session-token"):
                page = client.get(path, headers=BOOTSTRAP_HEADERS)
                assert "no-store" in page.headers["Cache-Control"]
                assert page.headers["X-Frame-Options"] == "DENY"
                assert page.headers["Referrer-Policy"] == "no-referrer"
                assert "access-control-allow-origin" not in page.headers
                if path != "/session-token":
                    assert token not in page.text
            assert client.get("/api/jobs/latest", headers={"X-YMD-Token": token}).status_code == 404
            if tokens:
                assert client.get("/api/jobs/latest", headers={"X-YMD-Token": tokens[0]}).status_code == 401
            tokens.append(token)
    assert tokens[0] != tokens[1]
    output = capsys.readouterr().out
    assert all(token not in output for token in tokens)


@pytest.mark.parametrize("base_url", ["http://localhost:8000", "http://127.0.0.1", "http://[::1]:8000"])
def test_canonical_loopback_origins_can_bootstrap_and_authenticate(base_url):
    app, _, _ = build_app()
    # This Starlette version cannot parse an IPv6 base_url in its test transport.
    with TestClient(app, base_url=BASE_URL, headers={"Host": base_url.split("://")[1]}) as client:
        response = client.get("/session-token", headers={"Origin": base_url, "X-YMD-Bootstrap": "1"})
        assert response.status_code == 200
        assert client.get("/api/jobs/latest", headers={
            "Origin": base_url, "X-YMD-Token": response.json()["token"],
        }).status_code == 404


@pytest.mark.parametrize("name,values", [
    ("Host", ["127.0.0.1:8000", "attacker.example"]),
    ("Origin", [BASE_URL, "https://attacker.example"]),
    ("Sec-Fetch-Site", ["same-origin", "cross-site"]),
])
def test_ambiguous_security_headers_are_rejected(name, values):
    app, _, _ = build_app()
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/session-token", headers=[
            ("X-YMD-Bootstrap", "1"), *[(name, value) for value in values],
        ])
    assert response.status_code == 403


@pytest.mark.parametrize("path", ACTION_PATHS)
def test_cross_site_text_plain_cannot_mutate(path):
    app, manager, _ = build_app()
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.post(path, content="{}", headers={
            "Origin": "https://attacker.example", "Content-Type": "text/plain",
            "Sec-Fetch-Site": "cross-site",
        })
    assert response.status_code == 403
    assert manager.latest_job() is None


@pytest.mark.parametrize("path", ACTION_PATHS)
@pytest.mark.parametrize("content_type", [None, "text/plain", "application/x-www-form-urlencoded"])
def test_authenticated_actions_require_json_content_type(path, content_type):
    app, _, _ = build_app()
    with authenticated_client(app) as client:
        del client.headers["Content-Type"]
        headers = {} if content_type is None else {"Content-Type": content_type}
        response = client.post(path, headers=headers, content="{}")
    assert response.status_code == 415


def test_valid_ui_create_poll_retry_and_actions(tmp_path: Path, monkeypatch):
    app, manager, _ = build_app()
    opened = []
    monkeypatch.setattr(api_module.os, "startfile", opened.append, raising=False)
    with authenticated_client(app, client=("127.0.0.1", 50000)) as client:
        created = create_job(client, tmp_path)
        job_id = created["job_id"]
        track = manager.add_track(job_id, MediaTrack("https://music.youtube.com/watch?v=x", "X", None, None))
        track.status = TrackStatus.FAILED
        for path in (f"/api/jobs/{job_id}", "/api/jobs/latest"):
            assert client.get(path).json()["id"] == job_id
        for action in ("pause", "resume", "retry-failed", "open-output-folder", "cancel"):
            assert client.post(f"/api/jobs/{job_id}/{action}", json={}).status_code == 200
    assert opened == [str(tmp_path)]


def test_open_output_rechecks_stored_network_path_before_filesystem(tmp_path: Path, monkeypatch):
    app, manager, _ = build_app()
    with authenticated_client(app, client=("127.0.0.1", 50000)) as client:
        created = create_job(client, tmp_path)
        manager.get_job(created["job_id"]).output_dir = Path("//server/share")

        def forbidden(*args, **kwargs):
            pytest.fail("unsafe stored path reached a filesystem operation")

        with monkeypatch.context() as patch:
            patch.setattr(Path, "exists", forbidden)
            patch.setattr(Path, "is_dir", forbidden)
            patch.setattr(api_module.os, "startfile", forbidden, raising=False)
            response = client.post(f"/api/jobs/{created['job_id']}/open-output-folder", json={})
        assert response.status_code == 400


@pytest.mark.parametrize("output_dir", UNSAFE_PATHS)
def test_network_and_device_output_paths_never_reach_filesystem(output_dir, monkeypatch):
    app, manager, _ = build_app()
    with authenticated_client(app) as client:
        def forbidden(*args, **kwargs):
            pytest.fail("unsafe output path reached filesystem validation")

        with monkeypatch.context() as patch:
            patch.setattr(api_module, "_validated_output_dir_sync", forbidden)
            response = client.post("/api/jobs", json={
                "playlist_url": "https://music.youtube.com/playlist?list=abc",
                "output_dir": output_dir, "output_mode": "192", "concurrency": 1,
            })
        assert response.status_code == 400
        assert "local" in response.json()["detail"]
    assert manager.latest_job() is None


@pytest.mark.parametrize("output_dir", UNSAFE_PATHS)
def test_sync_path_validation_rejects_before_path_operations(output_dir, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unsafe path reached a filesystem operation")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "exists", forbidden)
        patch.setattr(Path, "is_dir", forbidden)
        patch.setattr(api_module.tempfile, "NamedTemporaryFile", forbidden)
        with pytest.raises(HTTPException) as error:
            api_module._validated_output_dir_sync(output_dir)
    assert error.value.status_code == 400


def test_expanded_home_network_path_is_rejected_before_filesystem(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("expanded network path reached a filesystem operation")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "expanduser", lambda self: Path("//server/share/music"))
        patch.setattr(Path, "exists", forbidden)
        with pytest.raises(HTTPException, match="local"):
            api_module._validated_output_dir_sync("~/music")
