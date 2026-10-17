"""Offline GUI/worker smoke test; optionally exercise the packaged helper."""
import argparse
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from youtube_music_downloader.desktop import MainWindow
from youtube_music_downloader.desktop_controller import DesktopController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.bundle:
        sys.frozen = True
        executable = 'YTMusicDownloader.exe' if os.name == 'nt' else 'YTMusicDownloader'
        sys.executable = str(args.bundle.resolve() / executable)
    app = QApplication([])
    if sys.platform == 'win32' and os.environ.get('QT_QPA_PLATFORM') == 'offscreen':
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'malgun.ttf'
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
            app.setFont(QFont('Malgun Gothic', 9))
    app.setQuitOnLastWindowClosed(False)
    controller = DesktopController()
    window = MainWindow(controller, QSettings(str(args.output / 'smoke.ini'), QSettings.Format.IniFormat))
    window.show()
    errors = []
    controller.error.connect(errors.append)

    def until(condition, seconds=15):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if not condition():
            raise RuntimeError(f'Smoke test timed out: {errors}')

    try:
        until(lambda: controller.is_ready)
        for width, height, name in [(1100, 760, 'desktop'), (880, 620, 'compact')]:
            window.resize(width, height)
            app.processEvents()
            if not window.grab().save(str(args.output / f'{name}.png')):
                raise RuntimeError('Could not save GUI screenshot')
        controller.send('start', playlist_url='https://example.com/')
        until(lambda: bool(errors))
        assert 'YouTube' in errors[-1], errors
        assert window.start_button.isEnabled()
        print('GUI rendered; worker ready; invalid input rejected; controls recovered.')
    finally:
        window.close()
        until(lambda: controller.process.state().value == 0)
        app.processEvents()
        window.deleteLater()
        controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    print('Worker exited cleanly.')


if __name__ == '__main__':
    main()
