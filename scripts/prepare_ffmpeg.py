"""Fetch pinned audio-only FFmpeg and its corresponding sources for packaging."""

import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = 'https://github.com/acoustid/ffmpeg-build/releases/download/v8.1.2-1/'
TARGETS = {
    'win32-x86_64': ('x86_64-w64-mingw32', '937593a314dd529ce4db4b1e32fa259fd1ccaf288e0e6759d8faf4578cd03e9b'),
    'darwin-arm64': ('arm64-apple-macos11', '0a64b7cddf20f11ad388a623e5c2391e1eda79aa448d81749d188e8a842cae29'),
    'darwin-x86_64': ('x86_64-apple-macos10.9', '471b497550148b5953e2b55a44758413ca2fb8b0b822c0bae558909299b796b3'),
    'linux-arm64': ('arm64-linux-gnu', 'a13e22cb46136ae452b0fd232e382df4cc0a8fd9b9f3bb3d32f4f948ac73122a'),
    'linux-x86_64': ('x86_64-linux-gnu', '0cf7662af710e6e4c947de15cc9ab837b7bf5ed7266be059bd2e7b8365ceae5b'),
}
SOURCES = {
    'ffmpeg-8.1.2.tar.gz': (
        'https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.gz',
        '32faba5ef67340d54724941eae1425580791195312a4fd13bf6f820a2818bf22'),
    'lame-3.100.tar.gz': (
        'https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz',
        'ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e'),
    'ffmpeg-build-v8.1.2-1.tar.gz': (
        'https://api.github.com/repos/acoustid/ffmpeg-build/tarball/v8.1.2-1',
        'ee0dccd7ff144a85cea11982783c71e01d9846868468ce943f130f52f352b6dc'),
}


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ensure_local_path(root: Path, path: Path) -> None:
    root, path = root.absolute(), path.absolute()
    if not path.is_relative_to(root):
        raise ValueError(f'Destination outside project: {path.name}')
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError(f'Refusing linked material path: {candidate.name}')
        if candidate == root:
            break
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'Destination outside project: {path.name}')


def target_key(os_name=None, machine=None) -> str:
    architecture = (machine or platform.machine()).lower()
    architecture = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(architecture, architecture)
    key = f'{os_name or sys.platform}-{architecture}'
    if key not in TARGETS:
        raise ValueError(f'Unsupported FFmpeg build target: {key}')
    return key


def verified_member(archive: Path, digest: str, member: str) -> bytes:
    if sha256(archive) != digest:
        raise ValueError(f'SHA-256 mismatch: {archive.name}')
    with tarfile.open(archive, 'r:gz') as package:
        entries = [entry for entry in package if entry.name == member]
        if len(entries) != 1 or not entries[0].isfile() or entries[0].size > 200_000_000:
            raise ValueError(f'Expected one bounded regular archive member: {member}')
        with package.extractfile(entries[0]) as stream:
            return stream.read()


def obtain(path: Path, url: str, digest: str, *, download: bool, root=ROOT) -> None:
    ensure_local_path(root, path)
    if path.is_file():
        if sha256(path) != digest:
            raise ValueError(f'SHA-256 mismatch: {path.name}; cached file was not overwritten')
        return
    if not download:
        raise FileNotFoundError(f'Missing {path.name}. Run: python scripts/prepare_ffmpeg.py --download')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.part')
    ensure_local_path(root, temporary)
    try:
        subprocess.run([
            'curl', '--fail', '--location', '--proto', '=https', '--proto-redir', '=https',
            '--connect-timeout', '10', '--max-time', '120', '--speed-limit', '1024',
            '--speed-time', '20', '--output', str(temporary), url,
        ], check=True, timeout=125)
        if sha256(temporary) != digest:
            raise ValueError(f'SHA-256 mismatch: {path.name}')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(root=ROOT, *, download=False, target=None) -> list[Path]:
    key = target or target_key()
    architecture, digest = TARGETS[key]
    basename = f'ffmpeg-8.1.2-audio-encode-{architecture}'
    materials = root / 'release-materials'
    archive = materials / 'downloads' / (basename + '.tar.gz')
    obtain(archive, RELEASE_URL + archive.name, digest, download=download, root=root)
    for name, (url, source_digest) in SOURCES.items():
        obtain(materials / 'sources' / name, url, source_digest, download=download, root=root)
    notices = {
        'ffmpeg-8.1.2.tar.gz': ('ffmpeg-8.1.2', ('COPYING.LGPLv2.1', 'LICENSE.md')),
        'lame-3.100.tar.gz': ('lame-3.100', ('COPYING', 'LICENSE', 'README')),
        'ffmpeg-build-v8.1.2-1.tar.gz': ('acoustid-ffmpeg-build-26ba7c7', ('LICENSE',)),
    }
    for name, (prefix, members) in notices.items():
        for member in members:
            content = verified_member(materials / 'sources' / name, SOURCES[name][1], f'{prefix}/{member}')
            notice = root / 'licenses' / 'audio-ffmpeg' / prefix / member
            ensure_local_path(root, notice)
            notice.parent.mkdir(parents=True, exist_ok=True)
            notice.write_bytes(content)
    destination = materials / 'ffmpeg' / key
    ensure_local_path(root, destination)
    destination.mkdir(parents=True, exist_ok=True)
    suffix = '.exe' if key.startswith('win32-') else ''
    binaries = []
    for tool in ('ffmpeg', 'ffprobe'):
        name = tool + suffix
        content = verified_member(archive, digest, f'{basename}/bin/{name}')
        path = destination / name
        ensure_local_path(root, path)
        path.write_bytes(content)
        path.chmod(0o755)
        binaries.append(path)
    record = {
        'target': key, 'provider': 'acoustid/ffmpeg-build', 'release': 'v8.1.2-1',
        'recipe_commit': 'bd5eb2e6ab4a56e9823a5216e838b53749de61cf',
        'archive': {'url': RELEASE_URL + archive.name, 'sha256': digest},
        'sources': {name: {'url': url, 'sha256': value} for name, (url, value) in SOURCES.items()},
        'binaries': {path.name: sha256(path) for path in binaries},
    }
    provenance = destination / 'provenance.json'
    ensure_local_path(root, provenance)
    provenance.write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return binaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Allow bounded downloads of pinned archives.')
    parser.add_argument('--target', choices=sorted(TARGETS))
    args = parser.parse_args()
    for path in prepare(download=args.download, target=args.target):
        print(f'Verified: {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
