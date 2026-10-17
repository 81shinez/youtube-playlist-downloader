"""Locate worker executables in source, directory, and self-extracting builds."""
import sys
from pathlib import Path


def worker_command(route: str) -> list[str]:
    if route not in {'desktop-worker', 'media-process'}:
        raise ValueError(f'Unknown worker route: {route}')
    if getattr(sys, 'frozen', False):
        name = 'ytm-worker.exe' if sys.platform == 'win32' else 'ytm-worker'
        extracted = getattr(sys, '_MEIPASS', None)
        helper = Path(extracted) / name if extracted else None
        if helper is None or not helper.is_file():
            helper = Path(sys.executable).parent / name
        return [str(helper), '--' + route]
    python = Path(sys.executable)
    if python.name.lower() == 'pythonw.exe':
        python = python.with_name('python.exe')
    return [str(python), '-m', 'youtube_music_downloader.' + route.replace('-', '_')]
