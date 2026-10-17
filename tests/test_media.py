import asyncio
import sys
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest

from youtube_music_downloader.media import FfmpegEncoder, YtDlpDownloader
from youtube_music_downloader.models import MediaTrack


def test_playlist_options_extracts_flat_playlist_quietly():
    options = YtDlpDownloader.playlist_options()

    assert options["extract_flat"] == "in_playlist"
    assert options["quiet"] is True


def test_yt_dlp_options_use_selected_browser_cookies(tmp_path: Path):
    def progress(value: int) -> None:
        pass

    assert YtDlpDownloader.playlist_options("chrome")["cookiesfrombrowser"] == ("chrome",)
    assert YtDlpDownloader.metadata_options("edge")["cookiesfrombrowser"] == ("edge",)
    assert YtDlpDownloader.download_options(tmp_path, progress, "firefox")["cookiesfrombrowser"] == ("firefox",)
    assert "cookiesfrombrowser" not in YtDlpDownloader.playlist_options("auto")


def test_download_options_uses_best_audio_template_and_progress_hook(tmp_path: Path):
    def progress(value: int) -> None:
        pass

    options = YtDlpDownloader.download_options(tmp_path, progress)

    assert options["format"] == "bestaudio/best"
    assert options["outtmpl"].endswith("%(id)s.%(ext)s")
    assert len(options["progress_hooks"]) == 1


def test_ffmpeg_command_encodes_mp3_at_requested_bitrate(tmp_path: Path):
    source = tmp_path / "source.webm"
    output = tmp_path / "output.mp3"

    assert FfmpegEncoder().build_command(source, output, bitrate_kbps=256) == [
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


def test_ffmpeg_command_uses_custom_executable_path(tmp_path: Path):
    source = tmp_path / "source.webm"
    output = tmp_path / "output.mp3"

    assert FfmpegEncoder("C:/tools/ffmpeg.exe").build_command(source, output, bitrate_kbps=192)[0] == (
        "C:/tools/ffmpeg.exe"
    )


def test_progress_hook_reports_download_percentage_and_finished():
    reported: list[int] = []
    hook = YtDlpDownloader.progress_hook(reported.append)

    hook({"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100})
    hook({"status": "finished"})

    assert reported == [25, 100]


@pytest.mark.asyncio
async def test_playlist_tracks_maps_yt_dlp_entries_without_downloading(monkeypatch):
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            captured["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def extract_info(self, playlist_url, download):
            captured["playlist_url"] = playlist_url
            captured["download"] = download
            return {
                "entries": [
                    {
                        "url": "https://music.youtube.com/watch?v=one",
                        "title": "One",
                        "artist": "Artist One",
                        "abr": 128.0,
                    },
                    {},
                    {
                        "id": "two",
                        "uploader": "Uploader Two",
                        "formats": [{"vcodec": "none", "acodec": "opus", "tbr": 160}],
                    },
                ]
            }

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    tracks = await YtDlpDownloader().playlist_tracks("playlist-url")

    assert captured["playlist_url"] == "playlist-url"
    assert captured["download"] is False
    assert tracks == [
        MediaTrack("https://music.youtube.com/watch?v=one", "One", "Artist One", 128),
        MediaTrack("two", "two", "Uploader Two", 160),
    ]


@pytest.mark.asyncio
async def test_playlist_tracks_does_not_resolve_ambiguous_flat_entry_bitrate(monkeypatch):
    detail_urls: list[str] = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def extract_info(self, url, download):
            assert download is False
            if url == "playlist-url":
                return {
                    "entries": [
                        {
                            "url": "https://music.youtube.com/watch?v=one",
                            "title": "One",
                            "tbr": 999,
                        },
                        {
                            "url": "https://music.youtube.com/watch?v=two",
                            "title": "Two",
                            "tbr": 888,
                        },
                        {
                            "url": "https://music.youtube.com/watch?v=three",
                            "title": "Three",
                            "abr": 96,
                            "tbr": 777,
                        },
                        {
                            "url": "https://music.youtube.com/watch?v=four",
                            "title": "Four",
                            "formats": [{"vcodec": "none", "acodec": "opus", "tbr": 160}],
                        },
                    ]
                }

            detail_urls.append(url)
            if url == "https://music.youtube.com/watch?v=one":
                return {"formats": [{"vcodec": "none", "acodec": "opus", "abr": 128}]}
            if url == "https://music.youtube.com/watch?v=two":
                raise RuntimeError("metadata unavailable")
            raise AssertionError(url)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    tracks = await YtDlpDownloader().playlist_tracks("playlist-url")

    assert tracks == [
        MediaTrack("https://music.youtube.com/watch?v=one", "One", None, None),
        MediaTrack("https://music.youtube.com/watch?v=two", "Two", None, None),
        MediaTrack("https://music.youtube.com/watch?v=three", "Three", None, 96),
        MediaTrack("https://music.youtube.com/watch?v=four", "Four", None, 160),
    ]
    assert detail_urls == []


@pytest.mark.asyncio
async def test_source_bitrate_resolves_audio_metadata(monkeypatch):
    captured_options: list[dict[str, object]] = []

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            captured_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def extract_info(self, url, download):
            assert download is False
            if url == "https://music.youtube.com/watch?v=one":
                return {
                    "tbr": 320,
                    "formats": [
                        {"format_id": "video", "vcodec": "vp9", "acodec": "none", "tbr": 1000},
                        {"format_id": "merged", "vcodec": "vp9", "acodec": "opus", "tbr": 512},
                        {"format_id": "audio", "vcodec": "none", "acodec": "opus", "abr": 128},
                    ],
                }
            if url == "https://music.youtube.com/watch?v=two":
                raise RuntimeError("metadata unavailable")
            raise AssertionError(url)

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    assert await YtDlpDownloader().source_bitrate("https://music.youtube.com/watch?v=one") == 128
    assert await YtDlpDownloader().source_bitrate("https://music.youtube.com/watch?v=two") is None
    assert all("extract_flat" not in options for options in captured_options)


@pytest.mark.asyncio
async def test_download_audio_returns_newly_created_file(tmp_path: Path, monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def download(self, urls):
            assert urls == ["https://music.youtube.com/watch?v=one"]
            target = Path(self.options["outtmpl"].replace("%(id)s", "one").replace("%(ext)s", "webm"))
            target.write_text("audio", encoding="utf-8")
            return 0

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    result = await YtDlpDownloader().download_audio(
        MediaTrack("https://music.youtube.com/watch?v=one", "One", None, None),
        tmp_path,
        lambda value: None,
    )

    assert result.name == "one.webm"
    assert result.parent != tmp_path
    assert result.read_text(encoding="utf-8") == "audio"


@pytest.mark.asyncio
async def test_concurrent_downloads_share_parent_but_return_own_files(tmp_path: Path, monkeypatch):
    (tmp_path / "preexisting.webm").write_text("old", encoding="utf-8")
    start_barrier = Barrier(2)
    finish_barrier = Barrier(2)

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def download(self, urls):
            track_id = urls[0].rsplit("=", maxsplit=1)[1]
            target = Path(self.options["outtmpl"].replace("%(id)s", track_id).replace("%(ext)s", "webm"))
            start_barrier.wait(timeout=5)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(track_id, encoding="utf-8")
            timestamp = 1000 if track_id == "one" else 2000
            target.touch()
            import os

            os.utime(target, (timestamp, timestamp))
            finish_barrier.wait(timeout=5)
            return 0

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYoutubeDL))

    one, two = await asyncio.gather(
        YtDlpDownloader().download_audio(
            MediaTrack("https://music.youtube.com/watch?v=one", "One", None, None),
            tmp_path,
            lambda value: None,
        ),
        YtDlpDownloader().download_audio(
            MediaTrack("https://music.youtube.com/watch?v=two", "Two", None, None),
            tmp_path,
            lambda value: None,
        ),
    )

    assert one.name == "one.webm"
    assert two.name == "two.webm"
    assert one.parent != tmp_path
    assert two.parent != tmp_path
    assert one.read_text(encoding="utf-8") == "one"
    assert two.read_text(encoding="utf-8") == "two"
    assert (tmp_path / "preexisting.webm").read_text(encoding="utf-8") == "old"


@pytest.mark.asyncio
async def test_encode_mp3_runs_ffmpeg_command_without_real_binary(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.webm"
    output = tmp_path / "nested" / "output.mp3"
    captured: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_create_subprocess_exec(*command, stdout, stderr):
        captured["command"] = list(command)
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        return FakeProcess()

    monkeypatch.setattr(
        "youtube_music_downloader.media.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    result = await FfmpegEncoder().encode_mp3(source, output, bitrate_kbps=192)

    assert result == output
    assert output.parent.is_dir()
    assert captured["command"] == FfmpegEncoder().build_command(source, output, 192)


@pytest.mark.asyncio
async def test_encode_mp3_reports_missing_ffmpeg_executable_clearly(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.webm"
    output = tmp_path / "output.mp3"

    async def fake_create_subprocess_exec(*command, stdout, stderr):
        raise FileNotFoundError(2, "The system cannot find the file specified", "ffmpeg")

    monkeypatch.setattr(
        "youtube_music_downloader.media.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    with pytest.raises(RuntimeError, match="ffmpeg .*PATH"):
        await FfmpegEncoder().encode_mp3(source, output, bitrate_kbps=192)
