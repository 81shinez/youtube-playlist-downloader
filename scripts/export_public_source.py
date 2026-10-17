"""Export checked working-tree source without Git history or uploading anything."""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import tempfile
import zipfile

import release_check


ROOT = release_check.ROOT
DEFAULT_OUTPUT = Path('dist/YTMusicDownloader-source.zip')
SOURCE_PREFIX = 'YTMusicDownloader-source'


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(['git', *args], cwd=root, check=True,
                          capture_output=True, timeout=15).stdout


def _validate_root(root: Path) -> Path:
    root = root.resolve()
    try:
        top = _git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError('Source root must be a Git working-tree root.') from error
    if Path(top).resolve() != root:
        raise ValueError('Source root must be the Git working-tree root, not a subdirectory.')
    return root


def _has_link(path: Path) -> bool:
    return any(part.is_symlink() or part.is_junction() for part in (path, *path.parents))


def _candidate_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (relative.is_absolute() or PureWindowsPath(name).drive or '\\' in name
            or '..' in relative.parts or release_check.unsafe_path(name)):
        raise ValueError(f'{name}: unsafe public source path')
    path = root / relative
    if _has_link(path):
        raise ValueError(f'{name}: review symlink/junction before public release')
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'{name}: source path escapes the source root')
    return path


def export_source(root: Path = ROOT, output: Path | None = None) -> tuple[Path, int, str]:
    """Return the archive path, file count and SHA256 after an atomic local export."""
    root = _validate_root(Path(root))
    names = sorted(set(_git(root, 'ls-files', '-z', '--cached', '--others',
                            '--exclude-standard').decode('utf-8').split('\0')) - {''})
    output = Path(output) if output is not None else DEFAULT_OUTPUT
    if not output.is_absolute():
        output = root / output
    if _has_link(output) or any(part.lower() == '.git' for part in output.parts):
        raise ValueError('Output must not use Git metadata, symlinks or junctions.')
    output = output.resolve()
    if output == root or output.is_dir():
        raise ValueError('Output must be an archive file, not a source directory.')
    if output in {(root / name).resolve() for name in names}:
        raise ValueError('Output must not overwrite a source candidate, including a deleted tracked file.')

    problems, _ = release_check.source_problems(root)
    if problems:
        raise ValueError('\n'.join(problems))

    # --exclude-standard alone only excludes ignored untracked files.
    ignored = set(_git(root, 'ls-files', '-z', '--cached', '--ignored',
                       '--exclude-standard').decode('utf-8').split('\0'))
    selected = [(name, _candidate_path(root, name)) for name in names if name not in ignored]
    contents = []
    for name, path in selected:
        if not path.exists():
            continue  # A working-tree deletion must never resurrect an index blob.
        if not path.is_file():
            raise ValueError(f'{name}: source candidate is not a regular file')
        data = path.read_bytes()
        if len(data) > 2_000_000:
            raise ValueError(f'{name}: large file needs manual review')
        try:
            problems = release_check.scan_text(name, data.decode('utf-8-sig'))
        except UnicodeDecodeError as error:
            raise ValueError(f'{name}: non-text source candidate needs manual review') from error
        if problems:
            raise ValueError('\n'.join(problems))
        mode = 0o100755 if path.stat().st_mode & 0o111 else 0o100644
        contents.append((name, data, mode))

    missing = set(release_check.REQUIRED) - {name for name, _, _ in contents}
    if missing:
        raise ValueError('Required notices excluded from export: ' + ', '.join(sorted(missing)))

    # Snapshot all checked bytes before creating any archive or temporary sibling.
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.' + output.name + '.',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data, mode in contents:
                    entry = zipfile.ZipInfo(f'{SOURCE_PREFIX}/{name}', date_time=(1980, 1, 1, 0, 0, 0))
                    entry.create_system = 3
                    entry.external_attr = mode << 16
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(entry, data)
            stream.flush()
            os.fsync(stream.fileno())
        with temporary.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        temporary.replace(output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output, len(contents), digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='Git working-tree root to check and export.')
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT,
                        help='ZIP destination, relative to the source root unless absolute.')
    args = parser.parse_args(argv)
    try:
        output, count, digest = export_source(args.root, args.output)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('BLOCKED: ' + str(error))
        return 1
    print(f'Exported {count} files: {output}')
    print(f'SHA256: {digest}')
    print('No Git history included. No files uploaded or Git metadata changed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
