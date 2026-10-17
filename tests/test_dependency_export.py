import hashlib
import importlib.util
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def exporter(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('export_dependency_sources', ROOT / 'scripts/export_dependency_sources.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_copies_only_declared_verified_sources(tmp_path, monkeypatch):
    module = exporter(monkeypatch)
    source = tmp_path / 'release-materials' / 'sources'
    source.mkdir(parents=True)
    (source / 'library.tar.xz').write_bytes(b'source archive')
    (source / 'cookies.txt').write_text('private')
    monkeypatch.setattr(module, 'identities', lambda: {
        'library.tar.xz': {'url': 'https://example.org/library.tar.xz', 'sha256': hashlib.sha256(b'source archive').hexdigest()},
    })
    path = module.export_sources(tmp_path)
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {'sources/library.tar.xz', 'SOURCES.json'}
        assert archive.read('sources/library.tar.xz') == b'source archive'
        assert archive.testzip() is None


def test_mismatch_keeps_existing_export(tmp_path, monkeypatch):
    module = exporter(monkeypatch)
    source = tmp_path / 'release-materials' / 'sources'
    source.mkdir(parents=True)
    (source / 'library.tar.xz').write_bytes(b'changed')
    output = tmp_path / 'dist' / 'YTMusicDownloader-dependency-sources.zip'
    output.parent.mkdir()
    output.write_bytes(b'previous export')
    monkeypatch.setattr(module, 'identities', lambda: {'library.tar.xz': {'url': 'https://example.org', 'sha256': '0' * 64}})
    with pytest.raises(ValueError, match='SHA-256'):
        module.export_sources(tmp_path)
    assert output.read_bytes() == b'previous export'
