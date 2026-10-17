import sys
from pathlib import Path

import pytest


@pytest.fixture
def legal_module():
    from youtube_music_downloader import legal_resources
    return legal_resources


def test_source_resources_use_project_root_not_working_directory(legal_module, tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'LICENSE').write_text('Original code MIT license\n', encoding='utf-8')
    monkeypatch.setattr(legal_module, '__file__', str(root / 'src' / 'youtube_music_downloader' / 'legal_resources.py'))
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    monkeypatch.chdir(tmp_path)

    assert legal_module.LegalResources().read('LICENSE') == 'Original code MIT license\n'


def test_frozen_resources_use_meipass_not_executable_directory(legal_module, tmp_path, monkeypatch):
    bundle = tmp_path / 'extracted'
    bundle.mkdir()
    (bundle / 'LICENSE').write_text('Bundled MIT license\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(bundle), raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'app.exe'))

    assert legal_module.LegalResources().read('LICENSE') == 'Bundled MIT license\n'


def test_mac_bundle_reads_contents_resources(legal_module, tmp_path, monkeypatch):
    contents = tmp_path / 'Downloader.app' / 'Contents'
    frameworks = contents / 'Frameworks'
    resources = contents / 'Resources'
    frameworks.mkdir(parents=True)
    resources.mkdir()
    (resources / 'LICENSE').write_text('Mac bundled license\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(frameworks), raising=False)
    monkeypatch.setattr(sys, 'platform', 'darwin')

    assert legal_module.LegalResources().read('LICENSE') == 'Mac bundled license\n'


def test_lists_nested_third_party_files_and_reads_full_plain_text(legal_module, tmp_path):
    nested = tmp_path / 'licenses' / 'third-party' / 'Qt' / 'deep'
    nested.mkdir(parents=True)
    text = 'Copyright holder\n' + ('A complete license clause.\n' * 4000) + '<END OF TERMS>\n'
    (nested / 'COPYING').write_text(text, encoding='utf-8-sig')
    (tmp_path / 'unrelated.txt').write_text('not legal material', encoding='utf-8')
    resources = legal_module.LegalResources(tmp_path)

    assert 'licenses/third-party/Qt/deep/COPYING' in resources.names()
    assert 'unrelated.txt' not in resources.names()
    assert resources.read('licenses/third-party/Qt/deep/COPYING') == text


def test_missing_legal_files_remain_selectable_with_readable_errors(legal_module, tmp_path):
    resources = legal_module.LegalResources(tmp_path)
    expected = {'LICENSE', 'THIRD_PARTY_NOTICES.md', 'licenses/GPL-3.0.txt',
                'licenses/LGPL-3.0.txt', 'licenses/SOURCES.md', 'docs/DISTRIBUTION.md'}

    assert expected <= set(resources.names())
    for name in expected:
        message = resources.read(name)
        assert name in message
        assert 'unavailable' in message.lower()


def test_removed_file_is_reported_without_raising(legal_module, tmp_path):
    directory = tmp_path / 'licenses'
    directory.mkdir()
    path = directory / 'COPYING'
    path.write_text('Terms', encoding='utf-8')
    resources = legal_module.LegalResources(tmp_path)
    assert 'licenses/COPYING' in resources.names()
    path.unlink()

    assert 'unavailable' in resources.read('licenses/COPYING').lower()


@pytest.mark.parametrize('name', ['../private.txt', 'licenses/../../private.txt',
                                 'licenses/../private.txt', 'private.txt', 'docs/private.txt'])
def test_reader_refuses_nonlegal_paths(legal_module, tmp_path, name):
    (tmp_path / 'licenses').mkdir()
    (tmp_path / 'docs').mkdir()
    for parent in (tmp_path, tmp_path.parent, tmp_path / 'docs'):
        (parent / 'private.txt').write_text('PRIVATE CONTENT', encoding='utf-8')

    text = legal_module.LegalResources(tmp_path).read(name)

    assert 'PRIVATE CONTENT' not in text
    assert 'unavailable' in text.lower()


def test_reader_refuses_absolute_paths(legal_module, tmp_path):
    path = tmp_path / 'LICENSE'
    path.write_text('Do not accept absolute paths', encoding='utf-8')

    assert 'unavailable' in legal_module.LegalResources(tmp_path).read(str(path)).lower()


@pytest.mark.parametrize('link_name', ['LICENSE', 'licenses/linked.txt', 'licenses/linked-directory'])
def test_symlinks_cannot_escape_legal_roots(legal_module, tmp_path, link_name):
    root = tmp_path / 'bundle'
    (root / 'licenses').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.txt').write_text('PRIVATE CONTENT', encoding='utf-8')
    directory_link = link_name.endswith('directory')
    target = outside if directory_link else outside / 'secret.txt'
    try:
        (root / link_name).symlink_to(target, target_is_directory=directory_link)
    except OSError as error:
        pytest.skip(f'Symbolic links unavailable: {error}')
    resources = legal_module.LegalResources(root)
    name = link_name + '/secret.txt' if directory_link else link_name

    assert 'unavailable' in resources.read(name).lower()
    assert 'licenses/linked-directory/secret.txt' not in resources.names()


def test_unreadable_and_binary_resources_have_readable_errors(legal_module, tmp_path, monkeypatch):
    path = tmp_path / 'LICENSE'
    path.write_bytes(b'not\x00plain text')
    resources = legal_module.LegalResources(tmp_path)
    assert 'unavailable' in resources.read('LICENSE').lower()

    def denied(*args, **kwargs):
        raise PermissionError('access denied')

    monkeypatch.setattr(Path, 'read_text', denied)
    assert 'unavailable' in resources.read('LICENSE').lower()


@pytest.mark.parametrize('name', ['LICENSE', 'docs/DISTRIBUTION.md', 'licenses', 'licenses/linked.txt'])
def test_resolved_targets_cannot_escape_legal_roots(legal_module, tmp_path, monkeypatch, name):
    root = tmp_path / 'bundle'
    (root / 'licenses').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    secret = outside / 'secret.txt'
    secret.write_text('PRIVATE CONTENT', encoding='utf-8')
    resolve = Path.resolve

    def redirected(path, *args, **kwargs):
        if path == root / name:
            return outside if name == 'licenses' else secret
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', redirected)
    resources = legal_module.LegalResources(root)
    assert 'unavailable' in resources.read(name).lower()
    assert 'licenses/secret.txt' not in resources.names()


def test_one_unreadable_entry_does_not_hide_other_licenses(legal_module, tmp_path, monkeypatch):
    directory = tmp_path / 'licenses'
    directory.mkdir()
    broken = directory / 'broken.txt'
    good = directory / 'good.txt'
    broken.write_text('unreadable', encoding='utf-8')
    good.write_text('Readable terms', encoding='utf-8')
    resolve = Path.resolve
    iterdir = Path.iterdir

    def denied(path, *args, **kwargs):
        if path == broken:
            raise PermissionError('access denied')
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', denied)
    monkeypatch.setattr(Path, 'iterdir', lambda path: iter([broken, good]) if path == directory else iterdir(path))
    resources = legal_module.LegalResources(tmp_path)

    assert 'licenses/good.txt' in resources.names()
    assert resources.read('licenses/good.txt') == 'Readable terms'
