"""Collect original notices from pinned, already downloaded Qt 6.12.0 sources.

This is an offline collector, not a binary SBOM or a compliance determination.
Run with Python 3.12+: python -B scripts/collect_qt_notices.py
Archives belong in release-materials/sources; no archive is extracted wholesale.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import tarfile


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 2_000_000
MAX_ARCHIVE_BYTES = 2_000_000_000
MAX_MEMBERS = 100_000
VERSION = '6.12.0'
QT_URL = 'https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/'
PYSIDE_URL = 'https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/'
SOURCE_IDENTITIES = (
    ('pyside-setup', 18211772, '099c1a597cf33c1b000e11cf68a0b82d216fb802bf81726efc720394f10c7751'),
    ('qtbase', 51220268, 'a951bd163c7b80fc6b8c88d7668fb56abf91c152373e13c10666763238131307'),
    ('qtsvg', 2341876, 'e4ab39534ec97987b1b9b60ef7f4d3253d5912a69f8c713a01753174a4029331'),
    ('qtimageformats', 1848620, '0943132b5db8de6b6a7f1d162682173e8763c7ed94e80fd39113292845f67762'),
)
SOURCES = tuple({
    'module': module,
    'archive': f'{module}-everywhere-src-{VERSION}.tar.xz',
    'archive_root': f'{module}-everywhere-src-{VERSION}',
    'size': size,
    'sha256': digest,
    'source_url': (PYSIDE_URL if module == 'pyside-setup' else QT_URL)
                  + f'{module}-everywhere-src-{VERSION}.tar.xz',
    'mirrorlist_url': (PYSIDE_URL if module == 'pyside-setup' else QT_URL)
                      + f'{module}-everywhere-src-{VERSION}.tar.xz.mirrorlist',
    'download_mirror_url': (
        'https://ftp.jaist.ac.jp/pub/qtproject/official_releases/QtForPython/pyside6/'
        'PySide6-6.12.0-src/' if module == 'pyside-setup' else
        'https://ftp.jaist.ac.jp/pub/qtproject/archive/qt/6.12/6.12.0/submodules/'
    ) + f'{module}-everywhere-src-{VERSION}.tar.xz',
} for module, size, digest in SOURCE_IDENTITIES)

# Conservative source notice coverage for the observed Windows runtime modules.
# Optional code in these modules is not asserted to be compiled into the wheel.
QTBASE_THIRDPARTY = (
    'D3D12MemoryAllocator', 'VulkanMemoryAllocator', 'blake2', 'double-conversion',
    'easing', 'emoji-segmenter', 'freetype', 'harfbuzz-ng', 'iaccessible2', 'icc',
    'libjpeg', 'libpng', 'libpsl', 'md4', 'md4c', 'md5', 'pcre2', 'pixman',
    'rfc6234', 'sha1', 'sha3', 'siphash', 'tinycbor', 'wintab', 'zlib',
)
SCOPES = {
    'qtbase': (
        'src/corelib', 'src/gui', 'src/widgets', 'src/network',
        'src/plugins/platforms/windows', 'src/plugins/platforms/direct2d',
        'src/plugins/platforms/minimal', 'src/plugins/platforms/offscreen',
        'src/plugins/styles/modernwindows', 'src/plugins/generic/tuiotouch',
        'src/plugins/networkinformation/networklistmanager',
        'src/plugins/tls/certonly', 'src/plugins/tls/openssl', 'src/plugins/tls/schannel',
        'src/plugins/imageformats/gif', 'src/plugins/imageformats/ico',
        'src/plugins/imageformats/jpeg', 'src/platformsupport', 'src/entrypoint',
        'util/gradientgen',
    ) + tuple('src/3rdparty/' + name for name in QTBASE_THIRDPARTY),
    'qtsvg': ('src/svg', 'src/plugins'),
    'qtimageformats': (
        'src/plugins/imageformats/icns', 'src/plugins/imageformats/tga',
        'src/plugins/imageformats/tiff', 'src/plugins/imageformats/wbmp',
        'src/plugins/imageformats/webp', 'src/3rdparty/libtiff', 'src/3rdparty/libwebp',
    ),
    'pyside-setup': (
        'sources/pyside6/libpyside', 'sources/pyside6/PySide6/QtCore',
        'sources/pyside6/PySide6/QtGui', 'sources/pyside6/PySide6/QtWidgets',
        'sources/pyside6/PySide6/QtNetwork', 'sources/shiboken6/libshiboken',
        'sources/shiboken6/shibokenmodule',
    ),
}
EXCLUDED_ATTRIBUTIONS = {'qeventdispatcher_cf': 'macOS-only dispatcher'}
NOTICE_NAME = re.compile(
    r'(^|[._-])(licen[cs]e\w*|copying\w*|copyright\w*|notice\w*|authors|patents|'
    r'unlicense|ftl|gpl\w*|lgpl\w*|bsd\w*|mit|isc|ofl\w*|apache\w*|mpl\w*)([._-]|$)',
    re.IGNORECASE,
)
SOURCE_SUFFIXES = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.py', '.js', '.java'}
BINARY_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.bmp', '.pdf', '.icc'}
RESERVED = {'con', 'prn', 'aux', 'nul'} | {
    f'{prefix}{number}' for prefix in ('com', 'lpt') for number in range(1, 10)
}


def safe_parts(name, *, pattern=False):
    parts = name.split('/')
    forbidden = '<>:"\\|' + ('' if pattern else '?*')
    if not name or any(
        not part or part in {'.', '..'} or part.endswith((' ', '.'))
        or part.split('.')[0].lower() in RESERVED
        or any(ord(char) < 32 or char in forbidden for char in part)
        for part in parts
    ):
        raise ValueError(f'Unsafe archive path: {name!r}')
    return parts


def reject_links(path):
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise ValueError(f'Link or junction is not allowed: {item}')


def archive_index(archive, root):
    safe_parts(root)
    members = {}
    seen = set()
    files = set()
    total = 0
    for number, member in enumerate(archive, 1):
        parts = safe_parts(member.name.rstrip('/') if member.isdir() else member.name)
        if parts[0] != root:
            raise ValueError(f'Unsafe archive root: {member.name}')
        if not (member.isdir() or member.isfile()) or member.sparse is not None:
            raise ValueError(f'Unsafe link or special archive member: {member.name}')
        canonical = '/'.join(parts).casefold()
        if canonical in seen:
            raise ValueError(f'Duplicate archive path or Windows case collision: {member.name}')
        seen.add(canonical)
        total += member.size
        if number > MAX_MEMBERS or member.size < 0 or total > MAX_ARCHIVE_BYTES:
            raise ValueError('Unsafe archive size or member count')
        if member.isfile():
            if len(parts) < 2:
                raise ValueError('Invalid archive root file')
            members['/'.join(parts[1:])] = member
            files.add(canonical)
    for name in seen:
        if any(str(parent) in files for parent in PurePosixPath(name).parents):
            raise ValueError(f'Archive file/directory conflict: {name}')
    return members


def in_scope(module, path):
    return any(path == prefix or path.startswith(prefix + '/') for prefix in SCOPES[module])


def notice_reason(module, path):
    pure = PurePosixPath(path)
    name = pure.name
    if pure.suffix.lower() in BINARY_SUFFIXES:
        return None
    if path.startswith('LICENSES/'):
        return 'module-license-text'
    if path in {'.reuse/dep5', 'REUSE.toml', 'REUSE'}:
        return 'reuse-metadata'
    scoped = in_scope(module, path)
    if scoped and 'LICENSES' in pure.parts[:-1]:
        return 'third-party-license-text'
    if name in {'REUSE.toml', 'REUSE'} and (
        scoped or any(prefix.startswith(str(pure.parent) + '/') for prefix in SCOPES[module])
    ):
        return 'reuse-metadata'
    if scoped and name == 'qt_attribution.json':
        return 'qt-attribution'
    if (scoped or len(pure.parts) == 1) and NOTICE_NAME.search(name):
        if pure.suffix.lower() not in SOURCE_SUFFIXES:
            return 'original-notice'
    return None


def reference_path(attribution_path, reference):
    if not reference or reference.startswith('/') or '\\' in reference:
        raise ValueError(f'Unsafe attribution reference: {reference!r}')
    parts = list(PurePosixPath(attribution_path).parent.parts)
    for part in reference.split('/'):
        if part == '..':
            if not parts:
                raise ValueError(f'Attribution reference escapes archive: {reference}')
            parts.pop()
        elif part != '.':
            parts.append(part)
    result = '/'.join(parts)
    safe_parts(result, pattern=True)
    return result


def reference_list(value, *, split=False):
    if isinstance(value, str):
        return shlex.split(value) if split else [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError('Invalid attribution reference list')


def large_member_identity(archive, member):
    with archive.extractfile(member) as stream:
        head = stream.read(65536)
        digest = hashlib.sha256(head)
        size = len(head)
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            size += len(chunk)
            digest.update(chunk)
    if size != member.size:
        raise ValueError(f'Archive member size mismatch: {member.name}')
    return head, digest.hexdigest()


def copyright_excerpt(module, path, head):
    # Only these two reviewed upstream header formats may replace large copies.
    if module != 'qtbase':
        return None
    if path == 'src/corelib/time/qtimezonelocale_data_p.h':
        if not head.startswith(b'// Copyright'):
            return None
        end = 0
        for line in head.splitlines(keepends=True):
            if not line.startswith(b'//') or not line.endswith(b'\n'):
                return None
            end += len(line)
            if line.rstrip(b'\r\n') == b'// SPDX-License-Identifier: Unicode-3.0':
                return 0, head[:end]
    elif path == 'src/gui/vulkan/vk.xml':
        opening = re.search(rb'(?m)^[ \t]*<comment>\r?\n', head)
        if not opening or b'<registry>' not in head[:opening.start()]:
            return None
        closing = re.search(rb'</comment>[ \t]*\r?\n', head[opening.end():])
        if not closing:
            return None
        excerpt = head[opening.start():opening.end() + closing.end()]
        if b'Copyright' in excerpt and b'SPDX-License-Identifier: Apache-2.0 OR MIT' in excerpt:
            return opening.start(), excerpt
    return None


def add_payload(payloads, destination, data):
    if destination.casefold() in {name.casefold() for name in payloads}:
        raise ValueError(f'Duplicate output path: {destination}')
    payloads[destination] = data


def collect_archive(archive, spec, report, payloads):
    module = spec['module']
    members = archive_index(archive, spec['archive_root'])
    selected = {}
    reference_notices = {}
    for path in members:
        reason = notice_reason(module, path)
        if reason:
            selected[path] = {reason}

    for path in sorted(selected):
        if not path.endswith('/qt_attribution.json'):
            continue
        member = members[path]
        if member.size > MAX_FILE_BYTES:
            continue
        # Upstream attribution JSON sometimes contains literal control characters.
        # Parse tolerantly, but preserve the original file bytes without rewriting.
        entries = json.loads(archive.extractfile(member).read(), strict=False)
        entries = entries if isinstance(entries, list) else [entries]
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f'Invalid attribution entry: {path}')
            identifier = entry.get('Id', '')
            if identifier in EXCLUDED_ATTRIBUTIONS:
                report['excluded_references'].append({
                    'module': module, 'attribution': path, 'id': identifier,
                    'reason': EXCLUDED_ATTRIBUTIONS[identifier],
                })
                continue
            report['components'].append({
                'module': module, 'attribution': path,
                **{key: entry[key] for key in ('Id', 'Name', 'Version', 'LicenseId', 'QtUsage', 'Copyright')
                   if key in entry},
            })
            entry_files = set()
            entry_licenses = set()
            for field in ('LicenseFile', 'LicenseFiles', 'Files'):
                if field not in entry:
                    continue
                for reference in reference_list(entry[field], split=field == 'Files'):
                    target = reference_path(path, reference)
                    matches = sorted(name for name in members
                                     if PurePosixPath('/' + name).match('/' + target))
                    if not matches:
                        report['unresolved_references'].append({
                            'module': module, 'attribution': path, 'field': field,
                            'reference': reference, 'resolved_path': target,
                        })
                    for name in matches:
                        if field == 'Files' and not in_scope(module, name):
                            report['excluded_references'].append({
                                'module': module, 'attribution': path, 'reference': reference,
                                'resolved_path': name, 'reason': 'outside selected runtime module scope',
                            })
                            continue
                        selected.setdefault(name, set()).add('attribution-' + field)
                        (entry_files if field == 'Files' else entry_licenses).add(name)
            for name in entry_files:
                reference_notices.setdefault(name, set()).update(entry_licenses)

    for path, reasons in sorted(selected.items()):
        member = members[path]
        destination = module + '/' + path
        if member.size > MAX_FILE_BYTES:
            head, digest = large_member_identity(archive, member)
            skipped = {
                'path': destination, 'archive': spec['archive'],
                'archive_member': member.name, 'size': member.size,
                'sha256': digest, 'reasons': sorted(reasons),
                'full_original_in_source_archive': True,
            }
            excerpt = copyright_excerpt(module, path, head)
            if excerpt:
                offset, data = excerpt
                excerpt_path = destination + '.copyright-notice.txt'
                add_payload(payloads, excerpt_path, data)
                report['files'].append({
                    'path': excerpt_path, 'archive': spec['archive'], 'archive_member': member.name,
                    'kind': 'byte-exact-copyright-excerpt',
                    'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                    'source_byte_offset': offset, 'source_byte_length': len(data),
                    'original_file_sha256': digest, 'original_file_size': member.size,
                    'full_original_in_source_archive': True, 'reasons': sorted(reasons),
                })
                skipped['notice_excerpt'] = excerpt_path
            report['skipped_large_files'].append(skipped)
            continue
        data = archive.extractfile(member).read(MAX_FILE_BYTES + 1)
        if len(data) != member.size:
            raise ValueError(f'Archive member size mismatch: {member.name}')
        if PurePosixPath(path).suffix.lower() in BINARY_SUFFIXES:
            report['archive_only_files'].append({
                'path': destination, 'archive': spec['archive'], 'archive_member': member.name,
                'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                'full_original_in_source_archive': True,
                'reason': 'Binary asset; copy the referenced original license text, not the asset.',
                'notice_files': sorted(module + '/' + name for name in reference_notices.get(path, ())),
                'reasons': sorted(reasons),
            })
            continue
        add_payload(payloads, destination, data)
        report['files'].append({
            'path': destination, 'archive': spec['archive'], 'archive_member': member.name,
            'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'reasons': sorted(reasons),
        })


def collect_notices(source_dir, output_dir, *, sources=SOURCES, refresh_manifest=False):
    source_dir = Path(source_dir).absolute()
    output_dir = Path(output_dir).absolute()
    reject_links(source_dir)
    reject_links(output_dir)
    if source_dir.is_relative_to(output_dir) or output_dir.is_relative_to(source_dir):
        raise ValueError('Source and output directories must be separate')
    report = {
        'schema_version': 2, 'qt_version': VERSION,
        'scope': 'Windows x64 PySide6/Shiboken6, QtCore, QtGui, QtWidgets, QtNetwork, '
                 'QtSvg, and the observed Qt plugins; opengl32sw excluded',
        'scope_note': 'Conservative source notice coverage, including optional code within '
                      'these modules. Not a binary SBOM or a legal compliance determination.',
        'notices_complete_definition': 'All selected notice references are accounted for by '
                      'original files, the two explicitly supported byte-exact header excerpts, '
                      'or binary archive references with separately copied license texts. '
                      'This does not assert completeness of corresponding source for the wheel.',
        'exact_wheel_build_recipe_and_patches_verified': False,
        'wheel_provenance_note': 'Official version-matched source archives are verified. '
                      'The exact build recipe, configuration, patches, and source revisions '
                      'used to produce the installed Windows wheels are not independently verified.',
        'selection_prefixes': {name: list(SCOPES[name]) for name in sorted({s['module'] for s in sources})},
        'max_copied_file_bytes': MAX_FILE_BYTES,
        'sources': [], 'files': [], 'components': [], 'skipped_large_files': [], 'archive_only_files': [],
        'unresolved_references': [], 'excluded_references': [],
    }
    payloads = {}
    seen_modules = set()
    for spec in sources:
        module = spec['module']
        if module in seen_modules or module not in SCOPES:
            raise ValueError('Invalid or duplicate module')
        seen_modules.add(module)
        if len(safe_parts(spec['archive'])) != 1:
            raise ValueError('Unsafe archive filename')
        path = source_dir / spec['archive']
        reject_links(path)
        with path.open('rb') as stream:
            size = os.fstat(stream.fileno()).st_size
            if size != spec['size']:
                raise ValueError(f'Source size mismatch: {spec["archive"]}')
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != spec['sha256']:
                raise ValueError(f'Source SHA256 mismatch: {spec["archive"]}')
            report['sources'].append({**spec, 'actual_size': size, 'actual_sha256': digest,
                                      'sha256_verified': True})
            stream.seek(0)
            with tarfile.open(fileobj=stream, mode='r:xz') as archive:
                collect_archive(archive, spec, report, payloads)

    report['files'].sort(key=lambda item: item['path'])
    for item in report['archive_only_files']:
        item['notice_files'] = [name for name in item['notice_files'] if name in payloads]
    report['full_selected_files_copied'] = not (report['skipped_large_files'] or report['archive_only_files'])
    report['notices_complete'] = not (
        report['unresolved_references']
        or any('notice_excerpt' not in item for item in report['skipped_large_files'])
        or any(not item['notice_files'] for item in report['archive_only_files'])
    )
    payloads['provenance.json'] = (json.dumps(report, indent=2, ensure_ascii=True, sort_keys=True)
                                   + '\n').encode('utf-8')
    # Validate the entire write set before touching the destination; never replace
    # edited originals, follow links, or publish the manifest before the files.
    for name, data in payloads.items():
        path = output_dir / name
        reject_links(path)
        if any(parent.exists() and not parent.is_dir() for parent in path.parents):
            raise ValueError(f'Existing output directory conflict: {path}')
        if path.exists() and (not path.is_file() or (
            path.read_bytes() != data and not (refresh_manifest and name == 'provenance.json')
        )):
            raise ValueError(f'Existing output differs; refusing overwrite: {path}')
    for name, data in payloads.items():
        path = output_dir / name
        if path.exists():
            if refresh_manifest and name == 'provenance.json' and path.read_bytes() != data:
                temporary = output_dir / '.provenance.json.tmp'
                reject_links(temporary)
                with temporary.open('xb') as stream:
                    stream.write(data)
                os.replace(temporary, path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        reject_links(path)
        with path.open('xb') as stream:
            stream.write(data)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=ROOT / 'release-materials/sources')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'licenses/qt-6.12.0')
    parser.add_argument('--refresh-manifest', action='store_true',
                        help='Update generated provenance only; never overwrite changed notice originals.')
    args = parser.parse_args()
    try:
        report = collect_notices(args.source_dir, args.output_dir, refresh_manifest=args.refresh_manifest)
    except (OSError, ValueError, tarfile.TarError) as error:
        print(f'BLOCKED: {error}')
        return 1
    print(f'Verified {len(report["sources"])} source archives; collected {len(report["files"])} notice files/excerpts.')
    for item in report['sources']:
        print(f'SHA256 {item["actual_sha256"]} {item["archive"]} ({item["actual_size"]} bytes)')
    for item in report['skipped_large_files']:
        print(f'OVER LIMIT: {item["path"]} ({item["size"]} bytes); excerpt: {item.get("notice_excerpt", "NONE")}')
    for item in report['archive_only_files']:
        print(f'ARCHIVE ONLY: {item["path"]}; notice files: {item["notice_files"]}')
    for item in report['unresolved_references']:
        print(f'UNRESOLVED: {item["module"]}/{item["attribution"]}: {item["reference"]}')
    print(f'Manifest: {args.output_dir / "provenance.json"}')
    return 0 if report['notices_complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
