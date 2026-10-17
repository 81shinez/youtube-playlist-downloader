import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def release_module():
    spec = importlib.util.spec_from_file_location('release_check', ROOT / 'scripts/release_check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', [
    '.env', '.env.production', 'cookies.txt', 'backup-cookies.json', 'session.sqlite',
    'dist/app.exe', 'downloads/song.mp3', 'logs/server.out', '.venv/pyvenv.cfg',
])
def test_private_or_binary_paths_are_blocked(name):
    assert release_module().unsafe_path(name)


@pytest.mark.parametrize('name', ['LICENSE', 'src/app.py', 'tests/test_api.py', '.env.example', 'licenses/GPL-3.0.txt'])
def test_public_source_paths_are_allowed(name):
    assert not release_module().unsafe_path(name)


def test_scanner_reports_secret_location_without_echoing_secret():
    secret = 'ghp_' + 'a' * 36
    errors = release_module().scan_text('src/config.py', 'TOKEN = "' + secret + '"')
    assert errors and 'src/config.py:1' in errors[0]
    assert secret not in errors[0]


def test_email_is_not_a_secret():
    assert release_module().scan_text('README.md', 'author <person@example.com>') == []


def test_binary_release_is_blocked_until_corresponding_source_is_verified():
    problems = release_module().binary_blockers(ROOT)
    assert any('FFmpeg' in problem for problem in problems)
    assert any('Qt' in problem for problem in problems)


def test_ci_does_not_publish_unreviewed_binary_artifacts():
    workflow = (ROOT / '.github/workflows/desktop-build.yml').read_text(encoding='utf-8')
    assert 'actions/upload-artifact' not in workflow
    assert 'release_check.py' in workflow


def test_release_build_stops_before_packaging(monkeypatch):
    spec = importlib.util.spec_from_file_location('build_desktop', ROOT / 'scripts/build_desktop.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    monkeypatch.setattr('sys.argv', ['build_desktop.py', '--release'])

    def forbidden(*args, **kwargs):
        pytest.fail('Public release must not launch PyInstaller yet')

    monkeypatch.setattr(module.subprocess, 'Popen', forbidden)
    assert module.main() == 1


def test_windows_build_uses_only_runtime_and_system_paths(monkeypatch):
    spec = importlib.util.spec_from_file_location('build_desktop', ROOT / 'scripts/build_desktop.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('PATH', 'C:/unrelated/Java/bin')
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    env = module.build_environment(True)
    assert 'Java' not in env['PATH']
    assert 'System32' in env['PATH']
    assert env['YMD_ONEFILE'] == '1'


@pytest.mark.parametrize('deleted', [False, True])
def test_index_secret_is_detected_even_when_worktree_is_sanitized(tmp_path, deleted):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, timeout=10)
    staged = tmp_path / 'config.py'
    staged.write_text('TOKEN = "' + 'ghp_' + 'b' * 36 + '"', encoding='utf-8')
    subprocess.run(['git', 'add', 'config.py'], cwd=tmp_path, check=True, timeout=10)
    if deleted:
        staged.unlink()
    else:
        staged.write_text('TOKEN = None', encoding='utf-8')
    problems, _ = release_module().source_problems(tmp_path)
    assert any('index:config.py:1' in problem for problem in problems)


def test_packaging_collects_installed_web_extra_notices():
    import ast
    from importlib import metadata
    from packaging.requirements import Requirement
    from PyInstaller.utils.hooks import copy_metadata

    tree = ast.parse((ROOT / 'scripts/desktop.spec').read_text(encoding='utf-8'))
    statements = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            break
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            statements.append(node)
    env = {'Path': Path, 'SPECPATH': str(ROOT / 'scripts'), 'metadata': metadata,
           'os': __import__('os'), 'sys': __import__('sys'), 'tomllib': __import__('tomllib'),
           'copy_metadata': copy_metadata, 'Requirement': Requirement}
    exec(compile(ast.Module(statements, type_ignores=[]), '<spec metadata>', 'exec'), env)
    names = {metadata.Distribution.at(path).metadata['Name'].lower() for path, _ in env['runtime_metadata']}
    for name in ('httptools', 'websockets', 'watchfiles', 'python-dotenv', 'pyyaml'):
        try:
            metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        assert name in names
