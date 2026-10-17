import sys
from pathlib import Path

import pytest


def test_onefile_uses_extracted_helper_instead_of_exe_directory(monkeypatch, tmp_path):
    from youtube_music_downloader.desktop_runtime import worker_command
    extracted = tmp_path / 'extracted'
    extracted.mkdir()
    name = 'ytm-worker.exe' if sys.platform == 'win32' else 'ytm-worker'
    (extracted / name).touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(extracted), raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'portable' / 'app.exe'))
    for route in ('desktop-worker', 'media-process'):
        assert worker_command(route) == [str(extracted / name), '--' + route]


def test_onedir_and_mac_bundle_fall_back_to_sibling_helper(monkeypatch, tmp_path):
    from youtube_music_downloader.desktop_runtime import worker_command
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path / '_internal'), raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'app.exe'))
    name = 'ytm-worker.exe' if sys.platform == 'win32' else 'ytm-worker'
    assert worker_command('desktop-worker') == [str(tmp_path / name), '--desktop-worker']


def test_source_pythonw_launches_console_python(monkeypatch):
    from youtube_music_downloader.desktop_runtime import worker_command
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(sys, 'executable', str(Path('runtime') / 'pythonw.exe'))
    assert worker_command('desktop-worker') == [str(Path('runtime') / 'python.exe'), '-m',
                                               'youtube_music_downloader.desktop_worker']


def test_rejects_unknown_worker_route():
    from youtube_music_downloader.desktop_runtime import worker_command
    with pytest.raises(ValueError):
        worker_command('unknown')
