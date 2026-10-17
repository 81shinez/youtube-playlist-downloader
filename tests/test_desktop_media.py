import asyncio
import importlib
import io
import json
import os
import struct
import sys
import wave
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from youtube_music_downloader.models import MediaTrack


@pytest.fixture
def desktop():
    return importlib.import_module("youtube_music_downloader.desktop_media")


def substitute_child(monkeypatch, script):
    original = asyncio.create_subprocess_exec
    state = SimpleNamespace(calls=[], processes=[], started=asyncio.Event())

    async def launch(*command, **kwargs):
        state.calls.append((command, kwargs))
        process = await original(sys.executable, "-u", "-c", script, *command[1:], **kwargs)
        state.processes.append(process)
        state.started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    return state


async def invoke(downloader, operation, tmp_path, progress=lambda value: None):
    if operation == "playlist":
        return await downloader.playlist_tracks("playlist-url", "chrome")
    if operation == "metadata":
        return await downloader.source_bitrate("track-url", "edge")
    return await downloader.download_audio(
        MediaTrack("track-url", "Song", "Artist", 128), tmp_path, progress, "firefox"
    )


@pytest.mark.asyncio
async def test_downloader_round_trips_requests_progress_and_typed_results(desktop, monkeypatch, tmp_path):
    state = substitute_child(monkeypatch, """
import json, sys
request = json.load(sys.stdin)
operation = request['operation']
if operation == 'playlist_tracks':
    assert request['playlist_url'] == 'playlist-url'
    assert request['cookie_source'] == 'chrome'
    value = [{'source_url': 'track-url', 'title': '\\u97f3', 'artist': None, 'source_bitrate_kbps': 128}]
elif operation == 'source_bitrate':
    assert request['source_url'] == 'track-url'
    assert request['cookie_source'] == 'edge'
    value = 192
else:
    assert operation == 'download_audio'
    assert request['track'] == {'source_url': 'track-url', 'title': 'Song', 'artist': 'Artist', 'source_bitrate_kbps': 128}
    assert request['cookie_source'] == 'firefox'
    print(json.dumps({'type': 'progress', 'value': 35}), flush=True)
    print(json.dumps({'type': 'progress', 'value': 100}), flush=True)
    value = request['work_dir'] + '/download.webm'
print(json.dumps({'type': 'result', 'value': value}), flush=True)
"""
    )
    downloader = desktop.DesktopDownloader()
    progress = []

    assert await invoke(downloader, "playlist", tmp_path) == [MediaTrack("track-url", "\u97f3", None, 128)]
    assert await invoke(downloader, "metadata", tmp_path) == 192
    assert await invoke(downloader, "download", tmp_path, progress.append) == tmp_path / "download.webm"
    assert progress == [35, 100]
    assert len(state.processes) == 3
    for command, kwargs in state.calls:
        assert command == (sys.executable, "-m", "youtube_music_downloader.media_process")
        if os.name == "nt":
            assert kwargs["creationflags"] & 0x08000000
    assert all(process.returncode == 0 for process in state.processes)


@pytest.mark.asyncio
async def test_frozen_downloader_launches_sibling_console_helper(desktop, monkeypatch):
    state = substitute_child(monkeypatch, "import json; print(json.dumps({'type': 'result', 'value': None}))")
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert await desktop.DesktopDownloader().source_bitrate("url") is None

    helper = Path(sys.executable).parent / ("ytm-worker.exe" if os.name == "nt" else "ytm-worker")
    assert state.calls[0][0] == (str(helper), "--media-process")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["playlist", "metadata", "download"])
async def test_downloader_cancellation_kills_and_reaps_child(desktop, monkeypatch, tmp_path, operation):
    state = substitute_child(monkeypatch, "import time; time.sleep(10)")
    task = asyncio.create_task(invoke(desktop.DesktopDownloader(), operation, tmp_path))
    try:
        await asyncio.wait_for(state.started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert state.processes[0].returncode is not None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["playlist", "metadata", "download"])
async def test_downloader_timeout_kills_and_reaps_child(desktop, monkeypatch, tmp_path, operation):
    state = substitute_child(monkeypatch, "import time; time.sleep(10)")
    downloader = desktop.DesktopDownloader(playlist_timeout=0.15, metadata_timeout=0.15, download_timeout=0.15)

    with pytest.raises(TimeoutError, match="timed out"):
        await asyncio.wait_for(invoke(downloader, operation, tmp_path), 3)

    assert state.processes[0].returncode is not None


@pytest.mark.asyncio
async def test_cancellation_during_spawn_still_reaps_child(desktop, monkeypatch):
    original = asyncio.create_subprocess_exec
    started, release = asyncio.Event(), asyncio.Event()
    processes = []

    async def delayed_spawn(*command, **kwargs):
        process = await original(sys.executable, "-c", "import time; time.sleep(10)", **kwargs)
        processes.append(process)
        started.set()
        await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    task = asyncio.create_task(desktop.DesktopDownloader().source_bitrate("url"))
    try:
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert processes[0].returncode is not None
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("script, message", [
    ("print('not json')", "response"),
    ("print('{}')", "response"),
    ("pass", "result"),
    ("print('{\"type\":\"error\",\"value\":\"cookie unavailable\"}')", "cookie unavailable"),
    ("import sys; print('{\"type\":\"result\",\"value\":128}'); sys.exit(3)", "3"),
])
async def test_downloader_rejects_failed_or_malformed_protocol(desktop, monkeypatch, script, message):
    state = substitute_child(monkeypatch, script)

    with pytest.raises(RuntimeError, match=message):
        await asyncio.wait_for(desktop.DesktopDownloader().source_bitrate("url"), 3)

    assert state.processes[0].returncode is not None


@pytest.mark.asyncio
async def test_stderr_is_drained_and_only_bounded_tail_is_reported(desktop, monkeypatch):
    substitute_child(monkeypatch, """
import sys
sys.stderr.write('discard-this-prefix' + 'x' * 200000 + 'keep-this-tail')
sys.stderr.flush()
sys.exit(7)
"""
    )

    with pytest.raises(RuntimeError) as error:
        await asyncio.wait_for(desktop.DesktopDownloader().source_bitrate("url"), 3)

    assert "keep-this-tail" in str(error.value)
    assert "discard-this-prefix" not in str(error.value)
    assert len(str(error.value)) < 66000


@pytest.mark.asyncio
async def test_playlist_result_can_exceed_default_stream_line_limit(desktop, monkeypatch):
    substitute_child(monkeypatch, """
import json
track = {'source_url': 'url', 'title': 'x' * 200, 'artist': None, 'source_bitrate_kbps': None}
print(json.dumps({'type': 'result', 'value': [track] * 1000}))
"""
    )

    tracks = await asyncio.wait_for(desktop.DesktopDownloader().playlist_tracks("url"), 3)

    assert len(tracks) == 1000
    assert tracks[-1].title == "x" * 200


@pytest.mark.parametrize("operation, expected", [
    ("playlist_tracks", [{"source_url": "url", "title": "Song", "artist": "Artist", "source_bitrate_kbps": 128}]),
    ("source_bitrate", 128),
    ("download_audio", "download"),
])
def test_child_dispatch_serializes_results_and_keeps_logs_off_stdout(monkeypatch, tmp_path, capsys, operation, expected):
    media_process = importlib.import_module("youtube_music_downloader.media_process")
    options_seen = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            options_seen.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            assert url == "url"
            assert download is False
            print("extractor diagnostic")
            return {"url": "url", "title": "Song", "artist": "Artist", "abr": 128}

        def download(self, urls):
            assert urls == ["url"]
            print("download diagnostic")
            output = Path(self.options["outtmpl"].replace("%(id)s", "track").replace("%(ext)s", "webm"))
            output.write_bytes(b"audio")
            for hook in self.options["progress_hooks"]:
                hook({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})
                hook({"status": "finished"})
            return 0

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    request = {"operation": operation, "playlist_url": "url", "source_url": "url", "cookie_source": "chrome",
               "track": asdict(MediaTrack("url", "Song", "Artist", 128)), "work_dir": str(tmp_path)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(request)))

    assert media_process.main() == 0

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.out.splitlines()]
    assert "diagnostic" in captured.err
    assert options_seen[0]["cookiesfrombrowser"] == ("chrome",)
    if operation == "download_audio":
        assert options_seen[0]["fixup"] == "never"
        assert options_seen[0]["external_downloader"] == {"default": "native"}
        assert events[:-1] == [{"type": "progress", "value": 50}, {"type": "progress", "value": 100}]
        assert Path(events[-1]["value"]).read_bytes() == b"audio"
    else:
        assert events == [{"type": "result", "value": expected}]


def test_child_invalid_request_emits_error_and_nonzero_exit(monkeypatch, capsys):
    media_process = importlib.import_module("youtube_music_downloader.media_process")
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"operation":"unsupported"}'))

    assert media_process.main() == 1

    event = json.loads(capsys.readouterr().out)
    assert event["type"] == "error"
    assert "unsupported" in event["value"]


def test_ffmpeg_resolver_prefers_imageio_absolute_executable(desktop, monkeypatch):
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", SimpleNamespace(get_ffmpeg_exe=lambda: sys.executable))

    assert desktop.resolve_ffmpeg() == str(Path(sys.executable).resolve())


def test_frozen_ffmpeg_resolver_uses_packaged_media(desktop, monkeypatch, tmp_path):
    executable = tmp_path / 'media' / ('ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg')
    executable.parent.mkdir()
    executable.write_bytes(b'packaged executable')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    assert desktop.resolve_ffmpeg() == str(executable.resolve())


def test_missing_frozen_ffmpeg_does_not_use_untracked_fallback(desktop, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg', SimpleNamespace(get_ffmpeg_exe=lambda: sys.executable))
    with pytest.raises(RuntimeError, match='ffmpeg'):
        desktop.resolve_ffmpeg()


@pytest.mark.parametrize("bundled", [None, "missing-ffmpeg-binary"])
def test_ffmpeg_resolver_falls_back_to_path(desktop, monkeypatch, bundled):
    module = None if bundled is None else SimpleNamespace(get_ffmpeg_exe=lambda: bundled)
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", module)
    monkeypatch.setattr(desktop.shutil, "which", lambda command: sys.executable if command == "ffmpeg" else None)

    assert desktop.resolve_ffmpeg() == str(Path(sys.executable).resolve())


def test_ffmpeg_resolver_reports_missing_executable(desktop, monkeypatch):
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", None)
    monkeypatch.setattr(desktop.shutil, "which", lambda command: None)

    with pytest.raises(RuntimeError, match="ffmpeg"):
        desktop.DesktopEncoder().ensure_available()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [True, False])
async def test_encoder_cancellation_and_timeout_reap_ffmpeg(desktop, monkeypatch, tmp_path, cancel):
    state = substitute_child(monkeypatch, "import time; time.sleep(10)")
    encoder = desktop.DesktopEncoder(ffmpeg_path=sys.executable, timeout=10 if cancel else 0.15)
    task = asyncio.create_task(encoder.encode_mp3(tmp_path / "in.wav", tmp_path / "out.mp3", 192))
    try:
        await asyncio.wait_for(state.started.wait(), 2)
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await asyncio.wait_for(task, 3)
        assert state.processes[0].returncode is not None
        command, kwargs = state.calls[0]
        assert "-nostdin" in command
        if os.name == "nt":
            assert kwargs["creationflags"] & 0x08000000
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_encoder_repeated_cancellation_waits_for_reaping(desktop, monkeypatch, tmp_path):
    state = substitute_child(monkeypatch, "import time; time.sleep(10)")
    waiting, release = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(desktop.DesktopEncoder(ffmpeg_path=sys.executable).encode_mp3(
        tmp_path / "in.wav", tmp_path / "out.mp3", 192
    ))
    try:
        await asyncio.wait_for(state.started.wait(), 2)
        process = state.processes[0]
        original_wait = process.wait

        async def delayed_wait():
            waiting.set()
            await release.wait()
            return await original_wait()

        monkeypatch.setattr(process, "wait", delayed_wait)
        task.cancel()
        await asyncio.wait_for(waiting.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert process.returncode is not None
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancellation_during_final_stderr_drain_does_not_cancel_cleanup(desktop, monkeypatch, tmp_path):
    state = substitute_child(monkeypatch, "pass")
    original_drain = desktop._drain
    drained, release = asyncio.Event(), asyncio.Event()
    drain_tasks = []

    async def delayed_drain(stream, tail=None):
        await original_drain(stream, tail)
        if tail is not None:
            drain_tasks.append(asyncio.current_task())
            drained.set()
            await release.wait()

    monkeypatch.setattr(desktop, "_drain", delayed_drain)
    task = asyncio.create_task(desktop.DesktopEncoder(sys.executable).encode_mp3(
        tmp_path / "in.wav", tmp_path / "out.mp3", 192
    ))
    try:
        await asyncio.wait_for(drained.wait(), 2)
        await asyncio.wait_for(state.processes[0].wait(), 2)
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert not drain_tasks[0].cancelled()
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_progress_callback_failure_reaps_child(desktop, monkeypatch, tmp_path):
    state = substitute_child(monkeypatch, """
import json, time
print(json.dumps({'type': 'progress', 'value': 10}), flush=True)
time.sleep(10)
"""
    )

    def fail_progress(value):
        raise ValueError("callback failed")

    with pytest.raises(ValueError, match="callback failed"):
        await asyncio.wait_for(invoke(desktop.DesktopDownloader(), "download", tmp_path, fail_progress), 3)

    assert state.processes[0].returncode is not None


@pytest.mark.asyncio
async def test_encoder_failure_reports_stderr(desktop, monkeypatch, tmp_path):
    state = substitute_child(monkeypatch, "import sys; sys.stderr.write('invalid input audio'); sys.exit(2)")

    with pytest.raises(RuntimeError, match="invalid input audio"):
        await desktop.DesktopEncoder(sys.executable).encode_mp3(tmp_path / "in.wav", tmp_path / "out.mp3", 128)

    assert state.processes[0].returncode == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["error", "cancel", "timeout"])
async def test_encoder_removes_attempt_partial_and_preserves_existing_destination(
    desktop, monkeypatch, tmp_path, existing, failure
):
    output = tmp_path / "out.mp3"
    if existing:
        output.write_bytes(b"original audio")
    state = substitute_child(monkeypatch, """
import sys, time
from pathlib import Path
Path(sys.argv[-1]).write_bytes(b'partial audio')
""" + ("sys.exit(1)" if failure == "error" else "time.sleep(10)"))
    task = asyncio.create_task(desktop.DesktopEncoder(
        sys.executable, timeout=0.3 if failure == "timeout" else 5
    ).encode_mp3(tmp_path / "in.wav", output, 128))
    try:
        await asyncio.wait_for(state.started.wait(), 2)
        if failure == "cancel":
            partial = Path(state.calls[0][0][-1])

            async def wait_for_partial():
                while not partial.exists() or partial.read_bytes() != b"partial audio":
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_partial(), 2)
            task.cancel()
        error = {"error": RuntimeError, "cancel": asyncio.CancelledError, "timeout": TimeoutError}[failure]
        with pytest.raises(error):
            await asyncio.wait_for(task, 3)
        assert state.processes[0].returncode is not None
        assert list(tmp_path.iterdir()) == ([output] if existing else [])
        if existing:
            assert output.read_bytes() == b"original audio"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancellation_has_bounded_cleanup_when_pipe_drain_stalls(desktop, monkeypatch, tmp_path):
    state = substitute_child(monkeypatch, "import time; time.sleep(10)")
    original_drain = desktop._drain
    drain_tasks = []

    async def stalled_drain(stream, tail=None):
        if tail is not None:
            drain_tasks.append(asyncio.current_task())
            await asyncio.Event().wait()
        await original_drain(stream, tail)

    monkeypatch.setattr(desktop, "_drain", stalled_drain)
    monkeypatch.setattr(desktop, "_CLEANUP_TIMEOUT", 0.05, raising=False)
    task = asyncio.create_task(desktop.DesktopEncoder(sys.executable).encode_mp3(
        tmp_path / "in.wav", tmp_path / "out.mp3", 128
    ))
    try:
        await asyncio.wait_for(state.started.wait(), 2)
        await asyncio.sleep(0)
        task.cancel()
        done, _ = await asyncio.wait([task], timeout=0.5)
        assert task in done
        with pytest.raises(asyncio.CancelledError):
            await task
        assert state.processes[0].returncode is not None
        assert all(reader.done() for reader in drain_tasks)
    finally:
        for reader in drain_tasks:
            reader.cancel()
        task.cancel()
        await asyncio.gather(task, *drain_tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_real_source_helper_runs_from_another_working_directory(desktop, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="Unknown media operation: unsupported"):
        await desktop.DesktopDownloader()._request({"operation": "unsupported"}, timeout=3)


@pytest.mark.parametrize("field", ["playlist_timeout", "metadata_timeout", "download_timeout"])
@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_downloader_rejects_unbounded_timeouts(desktop, field, value):
    with pytest.raises(ValueError, match="timeout"):
        desktop.DesktopDownloader(**{field: value})


@pytest.mark.asyncio
async def test_encoder_produces_real_mp3_from_synthetic_wav(desktop, tmp_path):
    try:
        executable = desktop.resolve_ffmpeg()
    except RuntimeError:
        pytest.skip("No local FFmpeg executable available")
    source = tmp_path / "tone.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"".join(struct.pack("<h", 2000 if index % 16 < 8 else -2000) for index in range(2000)))
    output = tmp_path / "nested" / "tone.mp3"

    result = await desktop.DesktopEncoder(executable, timeout=5).encode_mp3(source, output, 128)

    assert result == output
    data = output.read_bytes()
    assert len(data) > 1000
    assert data.startswith(b"ID3") or data[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
