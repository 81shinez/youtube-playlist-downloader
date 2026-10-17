from pathlib import Path

from youtube_music_downloader.filenames import resolve_mp3_path, sanitize_filename


def test_sanitize_filename_removes_windows_reserved_characters():
    assert sanitize_filename('A:B*C?D"E<F>G|H') == "A_B_C_D_E_F_G_H"


def test_sanitize_filename_collapses_whitespace_and_strips_edges():
    assert sanitize_filename("  hello   world  ") == "hello world"


def test_sanitize_filename_returns_fallback_for_empty_value():
    assert sanitize_filename("   ...   ") == "track"


def test_sanitize_filename_avoids_windows_device_names():
    assert sanitize_filename("CON") == "CON_"
    assert sanitize_filename("com1") == "com1_"


def test_sanitize_filename_avoids_device_names_with_extensions():
    assert sanitize_filename("NUL.txt") == "NUL_.txt"
    assert sanitize_filename("NUL.tar.gz") == "NUL_.tar.gz"


def test_sanitize_filename_avoids_superscript_device_names():
    assert sanitize_filename("COM\u00b9") == "COM\u00b9_"
    assert sanitize_filename("lpt\u00b2") == "lpt\u00b2_"


def test_filename_sources_are_ascii_safe():
    filenames_source = (
        Path(__file__).parents[1] / "src" / "youtube_music_downloader" / "filenames.py"
    )

    filenames_source.read_text(encoding="ascii")
    Path(__file__).read_text(encoding="ascii")


def test_sanitize_filename_replaces_control_characters():
    assert sanitize_filename("hello\x00world\x1fname") == "hello_world_name"


def test_resolve_mp3_path_uses_artist_and_title(tmp_path: Path):
    path = resolve_mp3_path(tmp_path, title="Song", artist="Artist")
    assert path == tmp_path / "Artist - Song.mp3"


def test_resolve_mp3_path_uses_title_only_when_artist_missing(tmp_path: Path):
    path = resolve_mp3_path(tmp_path, title="Song", artist=None)
    assert path == tmp_path / "Song.mp3"


def test_resolve_mp3_path_adds_suffix_when_file_exists(tmp_path: Path):
    first = tmp_path / "Artist - Song.mp3"
    second = tmp_path / "Artist - Song (2).mp3"
    first.write_text("already here", encoding="utf-8")

    path = resolve_mp3_path(tmp_path, title="Song", artist="Artist")

    assert path == second


def test_resolve_mp3_path_skips_multiple_existing_suffixes(tmp_path: Path):
    (tmp_path / "Artist - Song.mp3").write_text("one", encoding="utf-8")
    (tmp_path / "Artist - Song (2).mp3").write_text("two", encoding="utf-8")

    path = resolve_mp3_path(tmp_path, title="Song", artist="Artist")

    assert path == tmp_path / "Artist - Song (3).mp3"
