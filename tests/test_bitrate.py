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


def test_choose_target_bitrate_rejects_raw_api_value():
    with pytest.raises(ValueError, match="Unsupported output mode"):
        choose_target_bitrate("192", source_bitrate_kbps=256)
