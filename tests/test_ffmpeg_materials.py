import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def module():
    spec = importlib.util.spec_from_file_location('prepare_ffmpeg', ROOT / 'scripts/prepare_ffmpeg.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def archive(tmp_path, name='bundle/bin/ffmpeg.exe', kind=tarfile.REGTYPE):
    path = tmp_path / 'bundle.tar.gz'
    with tarfile.open(path, 'w:gz') as output:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.size = 3 if kind == tarfile.REGTYPE else 0
        entry.linkname = '../../outside'
        output.addfile(entry, io.BytesIO(b'abc') if entry.size else None)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_extract_only_expected_verified_regular_member(tmp_path):
    path, digest = archive(tmp_path)
    assert module().verified_member(path, digest, 'bundle/bin/ffmpeg.exe') == b'abc'


def test_corrupt_archive_rejected_before_extraction(tmp_path):
    path, _ = archive(tmp_path)
    with pytest.raises(ValueError, match='SHA-256'):
        module().verified_member(path, '0' * 64, 'bundle/bin/ffmpeg.exe')


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_binary_links_rejected(tmp_path, kind):
    path, digest = archive(tmp_path, kind=kind)
    with pytest.raises(ValueError, match='regular'):
        module().verified_member(path, digest, 'bundle/bin/ffmpeg.exe')


def test_unsupported_architecture_fails_without_guessing():
    with pytest.raises(ValueError, match='Unsupported'):
        module().target_key('win32', 'arm64')


def test_windows_architecture_alias():
    assert module().target_key('win32', 'AMD64') == 'win32-x86_64'


def test_packaging_excludes_opaque_imageio_binary():
    spec = (ROOT / 'scripts/desktop.spec').read_text(encoding='utf-8')
    assert 'prepare_ffmpeg' in spec
    assert 'get_package_paths("imageio_ffmpeg")' not in spec
    assert '"imageio_ffmpeg"' in spec


@pytest.mark.parametrize('linked', ['release-materials', 'sources', 'library.tar.gz'])
def test_preparation_rejects_linked_destination_ancestors(tmp_path, monkeypatch, linked):
    target = tmp_path / 'release-materials' / 'sources' / 'library.tar.gz'
    monkeypatch.setattr(Path, 'is_symlink', lambda self: self.name == linked)
    with pytest.raises(ValueError, match='link'):
        module().ensure_local_path(tmp_path, target)


def test_preparation_rejects_destination_outside_root(tmp_path):
    with pytest.raises(ValueError, match='outside'):
        module().ensure_local_path(tmp_path / 'root', tmp_path / 'outside')


@pytest.mark.parametrize('extra', [
    'imageio_ffmpeg/binaries/ffmpeg-win.exe', 'PySide6/opengl32sw.dll',
    'ucrtbase.dll', 'api-ms-win-crt-runtime-l1-1-0.dll',
])
def test_actual_archive_policy_rejects_unintended_native_files(extra):
    spec = importlib.util.spec_from_file_location('verify_onefile', ROOT / 'scripts/verify_onefile.py')
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    with pytest.raises(ValueError, match='Unexpected'):
        verifier.validate_entries(['media/ffmpeg.exe', 'media/ffprobe.exe', extra])
