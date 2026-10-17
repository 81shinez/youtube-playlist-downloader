"""Check public source candidates; refuse unaudited binary redistribution."""

import argparse
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    'LICENSE', 'THIRD_PARTY_NOTICES.md', 'SECURITY.md', 'docs/DISTRIBUTION.md',
    'licenses/GPL-3.0.txt', 'licenses/LGPL-3.0.txt', 'licenses/SOURCES.md',
)
PRIVATE_DIRS = {'.git', '.venv', '.worktrees', '.superpowers', '__pycache__',
                'build', 'dist', 'downloads', 'logs', 'release-materials'}
PRIVATE_SUFFIXES = {'.exe', '.dll', '.so', '.dylib', '.pyc', '.db', '.sqlite', '.sqlite3',
                    '.mp3', '.wav', '.m4a', '.mp4', '.webm', '.ogg', '.opus', '.flac',
                    '.part', '.log', '.pem', '.key', '.pfx', '.p12'}
SECRET = re.compile(
    r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'
    r'|\bgh[pousr]_[A-Za-z0-9]{36,}\b'
    r'|\bgithub_pat_[A-Za-z0-9_]{40,}\b'
    r'|\bAKIA[A-Z0-9]{16}\b'
    r'|\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b'
)


def unsafe_path(name: str) -> bool:
    path = PurePosixPath(name.replace('\\', '/').lower())
    return (any(part in PRIVATE_DIRS or part.startswith('pytest-tmp-') for part in path.parts)
            or path.suffix in PRIVATE_SUFFIXES
            or (path.name.startswith('.env') and path.name != '.env.example')
            or ('cookies' in path.name and path.suffix in {'.txt', '.json', '.cookies'}))


def scan_text(name: str, content: str) -> list[str]:
    return [f'{name}:{number}: possible credential/private key (value hidden)'
            for number, line in enumerate(content.splitlines(), 1) if SECRET.search(line)]


def index_problems(root: Path) -> list[str]:
    entries = subprocess.run(['git', 'ls-files', '--stage', '-z'], cwd=root,
                             check=True, capture_output=True, timeout=15).stdout
    problems = []
    for entry in entries.split(b'\0'):
        if not entry:
            continue
        info, raw_name = entry.split(b'\t', 1)
        mode, object_id, stage = info.decode('ascii').split()
        name = raw_name.decode('utf-8')
        label = 'index:' + name
        if stage != '0' or mode not in {'100644', '100755'}:
            problems.append(f'{label}: unresolved or non-regular index entry needs review')
            continue
        if unsafe_path(name):
            problems.append(f'{label}: private/generated/binary file is staged or tracked')
            continue
        size = int(subprocess.run(['git', 'cat-file', '-s', object_id], cwd=root,
                                  check=True, capture_output=True, timeout=10).stdout)
        if size > 2_000_000:
            problems.append(f'{label}: large index blob needs manual review')
            continue
        content = subprocess.run(['git', 'cat-file', 'blob', object_id], cwd=root,
                                 check=True, capture_output=True, timeout=10).stdout
        try:
            problems.extend(scan_text(label, content.decode('utf-8-sig')))
        except UnicodeDecodeError:
            problems.append(f'{label}: non-text index blob needs manual review')
    return problems


def source_problems(root: Path) -> tuple[list[str], int]:
    result = subprocess.run(
        ['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        cwd=root, check=True, capture_output=True, timeout=15,
    )
    names = sorted(set(result.stdout.decode('utf-8').split('\0')) - {''})
    problems = [f'Missing required notice: {name}' for name in REQUIRED if not (root / name).is_file()]
    count = 0
    for name in names:
        path = root / name
        if path.is_symlink():
            problems.append(f'{name}: review symlink before public release')
            continue
        if not path.is_file():
            continue
        count += 1
        if unsafe_path(name):
            problems.append(f'{name}: private/generated/binary file in public source candidates')
        elif path.stat().st_size > 2_000_000:
            problems.append(f'{name}: large file needs manual review')
        else:
            try:
                problems.extend(scan_text(name, path.read_text(encoding='utf-8-sig')))
            except UnicodeDecodeError:
                problems.append(f'{name}: non-text source candidate needs manual review')
    problems.extend(index_problems(root))
    return problems, count


def binary_blockers(root: Path) -> list[str]:
    # Deliberately fail closed. Remove these only after an artifact-specific review,
    # not by adding a bypass flag or a self-declared "compliant" manifest field.
    return [
        'FFmpeg: audio-only sources/recipe are prepared; exact compiler-runtime provenance remains unverified.',
        'Qt/PySide6: official version-matched sources are prepared; exact wheel build/patch provenance remains unverified.',
        'Native runtime dependencies: libffi revision and full per-platform redistribution review remain unverified.',
        f'Public binary uploads are disabled. See {root / "docs/DISTRIBUTION.md"}.',
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', action='store_true', help='Also require binary redistribution readiness.')
    args = parser.parse_args()
    problems, count = source_problems(ROOT)
    if args.binary:
        problems.extend(binary_blockers(ROOT))
    if problems:
        for problem in problems:
            print('BLOCKED: ' + problem)
        return 1
    print(f'Source checks passed for {count} working-tree files and the Git index. No files uploaded or history changed.')
    print('Pattern scan only; review new files and Git history separately. Binary release is NOT approved.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
