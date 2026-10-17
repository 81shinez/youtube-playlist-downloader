import os
import time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QSettings, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QListWidget, QPlainTextEdit


class Controller(QObject):
    snapshot = Signal(dict)
    error = Signal(str)
    ready = Signal(bool)
    busy = Signal(bool)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.sent = []

    def send(self, action, **options):
        self.sent.append((action, options))

    def shutdown(self):
        self.stopped.emit()


@pytest.fixture(scope='session')
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance
    instance.processEvents()
    for widget in instance.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def window(tmp_path):
    from youtube_music_downloader.desktop import MainWindow
    controller = Controller()
    settings = QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat)
    view = MainWindow(controller, settings)
    controller.ready.emit(True)
    return view, controller


def job(status='running'):
    return dict(id='one', status=status, output_dir='.', error_message=None,
                summary={'total': 2, 'completed': 0, 'failed': 1, 'canceled': 0},
                tracks=[dict(id='a', title='곡 이름', artist='아티스트', status='downloading',
                             progress=42, target_bitrate_kbps=192, source_bitrate_kbps=192,
                             output_path=None, error_message=None),
                        dict(id='b', title='실패한 곡', artist='아티스트', status='failed',
                             progress=0, target_bitrate_kbps=None, source_bitrate_kbps=256,
                             output_path=None, error_message='인증이 필요합니다.')])


def test_running_controls_send_pause_cancel_and_retry(app, tmp_path):
    view, controller = window(tmp_path)
    controller.snapshot.emit(job())
    assert view.pause_button.isEnabled()
    assert view.cancel_button.isEnabled()
    assert view.retry_button.isEnabled()
    view.pause_button.click()
    view.cancel_button.click()
    view.retry_button.click()
    assert [x[0] for x in controller.sent] == ['pause', 'cancel', 'retry_failed']
    assert view.table.rowCount() == 2
    view.close()


def test_start_error_releases_start_button_and_shows_message(app, tmp_path):
    view, controller = window(tmp_path)
    controller.busy.emit(True)
    assert not view.start_button.isEnabled()
    controller.error.emit('저장 폴더에 쓸 수 없습니다.')
    controller.busy.emit(False)
    assert view.start_button.isEnabled()
    assert '저장 폴더' in view.message.text()
    view.close()


def test_paused_and_terminal_controls(app, tmp_path):
    view, controller = window(tmp_path)
    controller.snapshot.emit(job('paused'))
    assert view.pause_button.isEnabled()
    assert view.pause_button.text() == '계속'
    view.pause_button.click()
    assert controller.sent[-1][0] == 'resume'
    controller.snapshot.emit(job('completed_with_errors'))
    assert not view.pause_button.isEnabled()
    assert not view.cancel_button.isEnabled()
    assert view.start_button.isEnabled()
    assert view.retry_button.isEnabled()
    view.close()


def test_real_worker_start_error_and_shutdown(app):
    from youtube_music_downloader.desktop_controller import DesktopController
    controller = DesktopController()
    errors = []
    controller.error.connect(errors.append)

    def until(predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert predicate(), errors

    try:
        until(lambda: controller.is_ready)
        controller.send('start', playlist_url='https://example.com/')
        until(lambda: bool(errors))
        assert 'YouTube' in errors[-1]
        assert not controller.pending
    finally:
        controller.shutdown()
        until(lambda: controller.process.state().value == 0)
        controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def license_action(view):
    menus = [action.menu() for action in view.menuBar().actions()
             if action.text() == '도움말(&H)']
    assert len(menus) == 1, 'A native Help menu must be available'
    actions = [action for action in menus[0].actions()
               if action.text() == '오픈소스 라이선스(&L)']
    assert len(actions) == 1
    return actions[0]


def test_license_menu_opens_nonmodal_dialog_and_preserves_download_state(app, tmp_path):
    view, controller = window(tmp_path)
    controller.snapshot.emit(job('paused'))
    controller.busy.emit(True)
    view.url.setText('https://music.youtube.com/playlist?list=unsaved')
    view.table.selectRow(1)
    before = (view.job, view.url.text(), view.output.text(), view.table.currentRow(),
              view.details.toPlainText(), view.progress.value(), view.message.text(),
              view.start_button.isEnabled(), view.pause_button.isEnabled(), view.settings.allKeys())
    view.show()
    try:
        action = license_action(view)
        assert action.isEnabled()
        action.trigger()
        app.processEvents()
        dialogs = view.findChildren(QDialog)
        assert len(dialogs) == 1
        dialog = dialogs[0]
        assert dialog.isVisible()
        assert not dialog.isModal()
        assert dialog.windowModality() == Qt.WindowModality.NonModal
        assert dialog.windowTitle() == '오픈소스 라이선스'
        assert view.isEnabled()
        notice = dialog.findChild(QLabel, 'qt_license_notice')
        assert notice is not None
        assert 'Qt' in notice.text() and 'PySide6' in notice.text()
        assert 'GNU Lesser General Public License' in notice.text()
        assert 'LGPL' in notice.text() and '3' in notice.text()
        action.trigger()
        assert view.findChildren(QDialog) == dialogs
        assert before == (view.job, view.url.text(), view.output.text(), view.table.currentRow(),
                          view.details.toPlainText(), view.progress.value(), view.message.text(),
                          view.start_button.isEnabled(), view.pause_button.isEnabled(), view.settings.allKeys())
        assert controller.sent == []
        buttons = dialog.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Close).click()
        assert not dialog.isVisible()
        action.trigger()
        assert dialog.isVisible()
        assert view.findChildren(QDialog) == dialogs
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
    finally:
        view.allow_close = True
        view.close()


def test_license_dialog_has_korean_labels(app):
    from youtube_music_downloader.desktop import OpenSourceLicensesDialog
    dialog = OpenSourceLicensesDialog()
    try:
        assert dialog.windowTitle() == '오픈소스 라이선스'
        assert dialog.files.accessibleName() == '라이선스 파일'
        assert dialog.text.accessibleName() == '라이선스 전문'
        button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Close)
        assert button.text() == '닫기'
    finally:
        dialog.deleteLater()


def test_license_dialog_exposes_full_text_and_nested_files_by_keyboard(app, tmp_path, monkeypatch):
    from youtube_music_downloader import legal_resources
    root = tmp_path / 'bundle'
    nested = root / 'licenses' / 'third-party' / 'Qt'
    nested.mkdir(parents=True)
    full_text = 'License terms\n' + ('A complete clause.\n' * 4000) + '<END OF TERMS>\n'
    (root / 'LICENSE').write_text(full_text, encoding='utf-8')
    (nested / 'COPYING').write_text('Nested third-party terms\n', encoding='utf-8')
    monkeypatch.setattr(legal_resources, 'resource_root', lambda: root)
    view, controller = window(tmp_path)
    try:
        license_action(view).trigger()
        app.processEvents()
        dialog = view.findChild(QDialog)
        files = dialog.findChild(QListWidget, 'legal_files')
        text = dialog.findChild(QPlainTextEdit, 'legal_text')
        assert files.accessibleName()
        assert text.accessibleName()
        assert text.isReadOnly()
        assert text.focusPolicy() != Qt.FocusPolicy.NoFocus
        names = [files.item(row).text() for row in range(files.count())]
        assert 'LICENSE' in names
        assert 'licenses/third-party/Qt/COPYING' in names
        files.setCurrentRow(names.index('LICENSE'))
        assert text.toPlainText() == full_text
        text.selectAll()
        assert text.textCursor().selectedText().replace('\u2029', '\n') == full_text
        index = names.index('licenses/third-party/Qt/COPYING')
        files.setCurrentRow(index - 1)
        files.setFocus()
        QTest.keyClick(files, Qt.Key.Key_Down)
        assert text.toPlainText() == 'Nested third-party terms\n'
        files.setCurrentRow(names.index('licenses/LGPL-3.0.txt'))
        assert 'unavailable' in text.toPlainText().lower()
        assert 'licenses/LGPL-3.0.txt' in text.toPlainText()
        assert controller.sent == []
    finally:
        view.allow_close = True
        view.close()


def test_license_dialog_displays_shipped_legal_documents_without_truncation(app, tmp_path):
    root = Path(__file__).resolve().parents[1]
    documents = ['LICENSE', 'THIRD_PARTY_NOTICES.md', 'licenses/LGPL-3.0.txt',
                 'licenses/GPL-3.0.txt', 'licenses/SOURCES.md', 'docs/DISTRIBUTION.md']
    view, controller = window(tmp_path)
    try:
        license_action(view).trigger()
        dialog = view.findChild(QDialog)
        files = dialog.findChild(QListWidget, 'legal_files')
        text = dialog.findChild(QPlainTextEdit, 'legal_text')
        for name in documents:
            expected = (root / name).read_text(encoding='utf-8-sig')
            assert expected.strip(), name
            matches = files.findItems(name, Qt.MatchFlag.MatchExactly)
            assert len(matches) == 1, name
            files.setCurrentItem(matches[0])
            assert text.toPlainText() == expected, name
        assert len((root / 'licenses/GPL-3.0.txt').read_text(encoding='utf-8')) > 30000
        assert len((root / 'licenses/LGPL-3.0.txt').read_text(encoding='utf-8')) > 7000
    finally:
        view.allow_close = True
        view.close()
