import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/export_public_source.py'
PREFIX = 'YTMusicDownloader-source/'
PUBLIC_FILES = {
    '.gitignore': 'dist/\nbuild/\ndownloads/\n.env\ncookies.txt\nlocal-only.txt\n',
    '.github/workflows/check.yml': 'name: Source checks\n',
    'LICENSE': 'Example source license\n',
    'THIRD_PARTY_NOTICES.md': 'Example third-party notices\n',
    'SECURITY.md': 'Example security policy\n',
    'docs/DISTRIBUTION.md': 'Source distribution notes\n',
    'licenses/GPL-3.0.txt': 'Example GPL notice\n',
    'licenses/LGPL-3.0.txt': 'Example LGPL notice\n',
    'licenses/SOURCES.md': 'Corresponding source references\n',
    'README.md': 'Current public readme\n',
    'pyproject.toml': '[project]\nname = "example"\n',
    'src/app.py': 'VALUE = "staged version"\n',
    'tests/test_app.py': 'def test_example():\n    assert True\n',
    'scripts/check.py': 'print("source check")\n',
}


def git(root, *args, **kwargs):
    return subprocess.run(['git', *args], cwd=root, check=True,
                          capture_output=True, timeout=10, **kwargs)


@pytest.fixture
def source_root(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    git(root, 'init', '-q')
    git(root, 'config', 'core.autocrlf', 'false')
    for name, content in PUBLIC_FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    git(root, 'add', 'src/app.py')
    return root


def export_module(monkeypatch):
    assert SCRIPT.is_file(), 'The public source exporter has not been implemented'
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('export_public_source', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_uses_current_files_and_includes_all_public_source(source_root, monkeypatch):
    module = export_module(monkeypatch)
    (source_root / 'src/app.py').write_bytes(b'VALUE = "current version"\n')
    index_before = (source_root / '.git/index').read_bytes()

    output, count, digest = module.export_source(source_root)

    assert output == source_root / 'dist/YTMusicDownloader-source.zip'
    assert count == len(PUBLIC_FILES)
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == sorted(PREFIX + name for name in PUBLIC_FILES)
        assert archive.read(PREFIX + 'src/app.py') == b'VALUE = "current version"\n'
        assert archive.comment == b''
        for entry in archive.infolist():
            assert entry.comment == entry.extra == b''
            assert str(source_root) not in entry.filename
    assert (source_root / '.git/index').read_bytes() == index_before


def test_export_excludes_git_objects_ignored_files_and_itself(source_root, monkeypatch):
    module = export_module(monkeypatch)
    secret = 'ghp_' + 'x' * 36
    git(source_root, 'hash-object', '-w', '--stdin', input=secret.encode())
    private_files = {
        '.env': secret,
        'cookies.txt': 'private browser cookie',
        'downloads/song.mp3': 'private downloaded media',
        'build/app.exe': 'private executable',
        'dist/YTMusicDownloader-source.zip': 'previous archive',
        'local-only.txt': 'ignored local notes',
    }
    for name, content in private_files.items():
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    git_files_before = {path.relative_to(source_root / '.git'): path.read_bytes()
                        for path in (source_root / '.git').rglob('*') if path.is_file()}

    output, _, _ = module.export_source(source_root)

    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {PREFIX + name for name in PUBLIC_FILES}
        assert all(secret.encode() not in archive.read(name) for name in archive.namelist())
    assert {path.relative_to(source_root / '.git'): path.read_bytes()
            for path in (source_root / '.git').rglob('*') if path.is_file()} == git_files_before


def test_deleted_tracked_file_is_not_restored_from_index(source_root, monkeypatch):
    module = export_module(monkeypatch)
    (source_root / 'src/app.py').unlink()

    output, count, _ = module.export_source(source_root)

    assert count == len(PUBLIC_FILES) - 1
    with zipfile.ZipFile(output) as archive:
        assert PREFIX + 'src/app.py' not in archive.namelist()


def test_ignored_tracked_file_is_not_exported(source_root, monkeypatch):
    module = export_module(monkeypatch)
    (source_root / 'local-only.txt').write_text('Local notes\n', encoding='utf-8')
    git(source_root, 'add', '-f', 'local-only.txt')

    output, _, _ = module.export_source(source_root)

    with zipfile.ZipFile(output) as archive:
        assert PREFIX + 'local-only.txt' not in archive.namelist()


@pytest.mark.parametrize('name, content', [
    ('src/secret.py', 'TOKEN = "' + 'ghp_' + 'a' * 36 + '"\n'),
    ('auth.key', 'private key content'),
    ('unexpected.exe', 'binary artifact'),
])
def test_unsafe_source_fails_before_creating_output(source_root, monkeypatch, name, content):
    module = export_module(monkeypatch)
    (source_root / name).write_text(content, encoding='utf-8')

    with pytest.raises(ValueError):
        module.export_source(source_root)

    assert not (source_root / 'dist').exists()


def test_required_notice_is_checked_before_output(source_root, monkeypatch):
    module = export_module(monkeypatch)
    (source_root / 'LICENSE').unlink()

    with pytest.raises(ValueError, match='LICENSE'):
        module.export_source(source_root)

    assert not (source_root / 'dist').exists()


def test_unsafe_index_still_blocks_sanitized_worktree(source_root, monkeypatch):
    module = export_module(monkeypatch)
    path = source_root / 'src/app.py'
    path.write_text('TOKEN = "' + 'ghp_' + 'b' * 36 + '"\n', encoding='utf-8')
    git(source_root, 'add', 'src/app.py')
    path.write_text('TOKEN = None\n', encoding='utf-8')

    with pytest.raises(ValueError, match='index:src/app.py'):
        module.export_source(source_root)

    assert not (source_root / 'dist').exists()


@pytest.mark.parametrize('name', ['README.md', 'src/app.py', 'src/../README.md'])
def test_output_cannot_overwrite_source_candidate(source_root, monkeypatch, name):
    module = export_module(monkeypatch)
    before = {path: path.read_bytes() for path in source_root.rglob('*') if path.is_file()}

    with pytest.raises(ValueError, match='[Oo]utput'):
        module.export_source(source_root, Path(name))

    assert all(path.read_bytes() == content for path, content in before.items())


def test_output_cannot_recreate_deleted_source_candidate(source_root, monkeypatch):
    module = export_module(monkeypatch)
    path = source_root / 'src/app.py'
    path.unlink()

    with pytest.raises(ValueError, match='[Oo]utput'):
        module.export_source(source_root, path)

    assert not path.exists()


def test_output_cannot_overwrite_git_metadata(source_root, monkeypatch):
    module = export_module(monkeypatch)
    config = source_root / '.git/config'
    before = config.read_bytes()

    with pytest.raises(ValueError, match='[Oo]utput'):
        module.export_source(source_root, config)

    assert config.read_bytes() == before


def test_non_repository_and_nested_roots_are_rejected(source_root, monkeypatch, tmp_path):
    module = export_module(monkeypatch)
    for root in (tmp_path, source_root / 'src'):
        with pytest.raises(ValueError, match='[Rr]oot'):
            module.export_source(root)
        assert not (root / 'dist').exists()


def test_failed_write_preserves_existing_archive_and_removes_temporary_file(source_root, monkeypatch):
    module = export_module(monkeypatch)
    output = source_root / 'dist/YTMusicDownloader-source.zip'
    output.parent.mkdir()
    output.write_bytes(b'previous complete archive')

    def fail_write(*args, **kwargs):
        raise OSError('simulated disk failure')

    monkeypatch.setattr(zipfile.ZipFile, 'writestr', fail_write)
    with pytest.raises(OSError, match='simulated disk failure'):
        module.export_source(source_root)

    assert output.read_bytes() == b'previous complete archive'
    assert list(output.parent.iterdir()) == [output]


def test_symlink_source_is_rejected(source_root, monkeypatch):
    module = export_module(monkeypatch)
    link = source_root / 'linked.py'
    try:
        link.symlink_to(source_root / 'src/app.py')
    except OSError:
        pytest.skip('Creating symlinks is not permitted on this host')

    with pytest.raises(ValueError, match='symlink'):
        module.export_source(source_root)

    assert not (source_root / 'dist').exists()


def test_index_symlink_is_rejected_without_host_symlink_support(source_root, monkeypatch):
    module = export_module(monkeypatch)
    target = b'src/app.py'
    blob = git(source_root, 'hash-object', '-w', '--stdin', input=target).stdout.decode().strip()
    git(source_root, 'update-index', '--add', '--cacheinfo', f'120000,{blob},linked.py')
    (source_root / 'linked.py').write_bytes(target)

    with pytest.raises(ValueError, match='index:linked.py'):
        module.export_source(source_root)

    assert not (source_root / 'dist').exists()


def test_repeat_export_is_stable_and_does_not_include_previous_archive(source_root, monkeypatch):
    module = export_module(monkeypatch)
    output, count, first_digest = module.export_source(source_root)

    repeated_output, repeated_count, second_digest = module.export_source(source_root)

    assert repeated_output == output
    assert repeated_count == count == len(PUBLIC_FILES)
    assert first_digest == second_digest
    assert list(output.parent.iterdir()) == [output]


def test_ignored_required_notice_blocks_incomplete_archive(source_root, monkeypatch):
    module = export_module(monkeypatch)
    ignore = source_root / '.gitignore'
    ignore.write_text(ignore.read_text(encoding='utf-8') + 'LICENSE\n', encoding='utf-8')

    with pytest.raises(ValueError, match='LICENSE'):
        module.export_source(source_root)

    assert not (source_root / 'dist').exists()


def test_cli_reports_file_count_and_checksum_without_upload(source_root, monkeypatch):
    export_module(monkeypatch)
    result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(source_root)],
                            capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stdout + result.stderr
    output = source_root / 'dist/YTMusicDownloader-source.zip'
    assert str(len(PUBLIC_FILES)) + ' files' in result.stdout
    assert hashlib.sha256(output.read_bytes()).hexdigest() in result.stdout
    assert 'SHA256' in result.stdout


def test_cli_failure_does_not_echo_credential_or_write_archive(source_root, monkeypatch):
    export_module(monkeypatch)
    secret = 'ghp_' + 'z' * 36
    (source_root / 'README.md').write_text(secret, encoding='utf-8')
    result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(source_root)],
                            capture_output=True, text=True, timeout=30)

    assert result.returncode == 1
    assert 'BLOCKED' in result.stdout
    assert secret not in result.stdout + result.stderr
    assert not (source_root / 'dist').exists()
