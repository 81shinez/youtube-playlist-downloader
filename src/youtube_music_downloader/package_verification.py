"""Offline, opt-in verification of the actual frozen application."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import wave


def verify_package(report_path: Path) -> int:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication, QEvent, QSettings, qVersion
    import PySide6
    from PySide6.QtWidgets import QApplication
    from youtube_music_downloader.desktop import MainWindow
    from youtube_music_downloader.desktop_controller import DesktopController
    from youtube_music_downloader.desktop_media import DesktopDownloader, DesktopEncoder
    from youtube_music_downloader.desktop_runtime import worker_command
    from youtube_music_downloader.legal_resources import LegalResources, PRIMARY_FILES

    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'ok': False, 'extracted_dir': getattr(sys, '_MEIPASS', None)}
    report['qt_version'] = qVersion()
    report['pyside_version'] = PySide6.__version__
    qt_candidates = [Path(PySide6.__file__).parent / 'Qt6Core.dll']
    if getattr(sys, 'frozen', False):
        qt_candidates.extend([Path(sys._MEIPASS) / 'Qt6Core.dll', Path(sys._MEIPASS) / 'PySide6' / 'Qt6Core.dll'])
    for qt_core in qt_candidates:
        if qt_core.is_file():
            report['qt_core_sha256'] = hashlib.sha256(qt_core.read_bytes()).hexdigest()
            break
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    controller = DesktopController()
    errors = []
    controller.error.connect(errors.append)

    def until(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        if not predicate():
            raise TimeoutError(f'Package verification timed out: {errors}')

    with tempfile.TemporaryDirectory(prefix='ymd-verification-') as temporary:
        folder = Path(temporary)
        window = MainWindow(controller, QSettings(str(folder / 'settings.ini'), QSettings.Format.IniFormat))
        try:
            window.show()
            until(lambda: controller.is_ready)
            report['gui'] = window.isVisible() and not window.grab().isNull()
            resources = LegalResources()
            report['legal_documents'] = {}
            for name in PRIMARY_FILES:
                content = resources.read(name)
                if not content.strip() or content.startswith('Legal resource unavailable:'):
                    raise RuntimeError(f'Missing packaged legal document: {name}')
                report['legal_documents'][name] = len(content)
            window.show_licenses()
            app.processEvents()
            dialog = window.licenses_dialog
            report['license_dialog'] = dialog.isVisible() and not dialog.grab().isNull()
            if not report['license_dialog'] or 'MIT License' not in dialog.text.toPlainText():
                raise RuntimeError('Packaged license viewer failed')
            dialog.close()
            report['worker'] = worker_command('desktop-worker')[0]
            controller.send('start', playlist_url='https://example.com/')
            until(lambda: bool(errors))
            if 'YouTube' not in errors[-1] or not window.start_button.isEnabled():
                raise RuntimeError(f'Invalid-input handling failed: {errors}')
            report['worker_ipc'] = True

            async def verify_media():
                downloader = DesktopDownloader()
                try:
                    await downloader._request({'operation': 'package_verification'}, 10)
                except RuntimeError as exc:
                    if 'Unknown media operation' not in str(exc):
                        raise
                else:
                    raise RuntimeError('Media helper did not reject the verification request')
                report['media_helper'] = True
                source = folder / 'silence.wav'
                with wave.open(str(source), 'wb') as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(44100)
                    audio.writeframes(b'\0\0' * 4410)
                encoder = DesktopEncoder(timeout=10)
                encoder.ensure_available()
                report['ffmpeg'] = encoder.ffmpeg_path
                report['ffmpeg_sha256'] = hashlib.sha256(Path(encoder.ffmpeg_path).read_bytes()).hexdigest()
                if getattr(sys, 'frozen', False):
                    Path(encoder.ffmpeg_path).resolve().relative_to(Path(sys._MEIPASS).resolve())
                result = await encoder.encode_mp3(source, folder / 'audio.mp3', 192)
                report['mp3_bytes'] = result.stat().st_size
                if report['mp3_bytes'] <= 0:
                    raise RuntimeError('MP3 output is empty')

            asyncio.run(verify_media())
            report['ok'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            window.close()
            try:
                until(lambda: controller.process.state().value == 0)
                report['worker_stopped'] = True
            except Exception:
                report['ok'] = False
                report['shutdown_error'] = traceback.format_exc()
                controller.process.kill()
                controller.process.waitForFinished(3000)
            app.processEvents()
            window.deleteLater()
            controller.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
