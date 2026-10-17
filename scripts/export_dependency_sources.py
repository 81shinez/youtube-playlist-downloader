"""Export verified Qt/FFmpeg source archives locally, without binaries or history."""

import json
import hashlib
import os
from pathlib import Path
import tempfile
import zipfile

from collect_qt_notices import SOURCES as QT_SOURCES
from prepare_ffmpeg import ROOT, SOURCES as FFMPEG_SOURCES, ensure_local_path, sha256


def identities() -> dict:
    sources = {name: {'url': url, 'sha256': digest} for name, (url, digest) in FFMPEG_SOURCES.items()}
    sources.update({item['archive']: {'url': item['source_url'], 'sha256': item['sha256']} for item in QT_SOURCES})
    return sources


def export_sources(root: Path = ROOT) -> Path:
    sources = identities()
    directory = root / 'release-materials' / 'sources'
    output = root / 'dist' / 'YTMusicDownloader-dependency-sources.zip'
    ensure_local_path(root, output)
    for name, item in sources.items():
        path = directory / name
        ensure_local_path(root, path)
        if path.is_symlink() or not path.is_file() or sha256(path) != item['sha256']:
            raise ValueError(f'Missing source or SHA-256 mismatch: {name}')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.sources-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                archive.writestr('SOURCES.json', json.dumps(sources, indent=2) + '\n')
                for name in sorted(sources):
                    path = directory / name
                    archive.write(path, 'sources/' + name)
                    if sha256(path) != sources[name]['sha256']:
                        raise ValueError(f'Source changed while exporting: {name}')
            stream.flush()
            os.fsync(stream.fileno())
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError('Source archive CRC verification failed')
            for name, item in sources.items():
                with archive.open('sources/' + name) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
                        raise ValueError(f'Exported source SHA-256 mismatch: {name}')
        temporary.replace(output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output


if __name__ == '__main__':
    result = export_sources()
    print(f'Dependency sources: {result}')
    print(f'SHA256: {sha256(result)}')
    print('Source archives only; this is not binary redistribution approval. Nothing uploaded.')
