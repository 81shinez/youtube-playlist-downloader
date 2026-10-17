import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/collect_qt_notices.py'
ARCHIVE_ROOT = 'qtbase-everywhere-src-6.12.0'


def load_collector():
    assert SCRIPT.is_file(), 'The Qt notice collector has not been implemented'
    spec = importlib.util.spec_from_file_location('collect_qt_notices', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_archive(tmp_path, entries, module='qtbase'):
    source_dir = tmp_path / 'sources'
    source_dir.mkdir(exist_ok=True)
    root = f'{module}-everywhere-src-6.12.0'
    path = source_dir / f'{root}.tar.xz'
    with tarfile.open(path, 'w:xz') as archive:
        for name, data in entries:
            if isinstance(name, tarfile.TarInfo):
                archive.addfile(name, io.BytesIO(data) if data else None)
            else:
                member = tarfile.TarInfo(root + '/' + name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
    spec = {
        'module': module, 'archive': path.name, 'archive_root': root,
        'size': path.stat().st_size,
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'source_url': 'https://download.qt.io/example.tar.xz',
        'mirrorlist_url': 'https://download.qt.io/example.tar.xz.mirrorlist',
        'download_mirror_url': 'https://ftp.jaist.ac.jp/example.tar.xz',
    }
    return source_dir, spec


def attribution(**fields):
    return json.dumps({'Id': 'fixture', 'QDocModule': 'qtgui', **fields}).encode()


def test_collect_preserves_bytes_paths_and_only_selected_notice_material(tmp_path):
    collector = load_collector()
    original = b'Copyright \xc2\xa9 original author\r\nNo rewriting.\r\n'
    entries = [
        ('LICENSES/LGPL-3.0-only.txt', original),
        ('REUSE.toml', b'version = 1\n'),
        ('src/3rdparty/libpng/REUSE.toml', b'version = 1\r\n'),
        ('src/3rdparty/libpng/qt_attribution.json', attribution(LicenseFile='LICENSE')),
        ('src/3rdparty/libpng/LICENSE', original),
        ('src/3rdparty/libpng/png.c', b'/* Copyright: not a reason to copy all code */'),
        ('src/3rdparty/sqlite/LICENSE', b'Not part of the distributed Qt modules'),
        ('examples/demo/LICENSE', b'Not distributed'),
    ]
    sources, spec = make_archive(tmp_path, entries)
    output = tmp_path / 'notices'

    report = collector.collect_notices(sources, output, sources=(spec,))

    assert {item['path'] for item in report['files']} == {
        'qtbase/LICENSES/LGPL-3.0-only.txt', 'qtbase/REUSE.toml',
        'qtbase/src/3rdparty/libpng/REUSE.toml',
        'qtbase/src/3rdparty/libpng/qt_attribution.json',
        'qtbase/src/3rdparty/libpng/LICENSE',
    }
    assert (output / 'qtbase/src/3rdparty/libpng/LICENSE').read_bytes() == original
    assert report['sources'][0]['actual_sha256'] == spec['sha256']
    assert report['sources'][0]['actual_size'] == spec['size']
    assert report['unresolved_references'] == []
    for item in report['files']:
        assert item['sha256'] == hashlib.sha256((output / item['path']).read_bytes()).hexdigest()
    assert json.loads((output / 'provenance.json').read_bytes()) == report


def test_attribution_references_include_explicit_source_but_not_entire_library(tmp_path):
    collector = load_collector()
    data = attribution(Path='upstream', LicenseFiles=['LICENSE', '../shared/COPYRIGHT'],
                       Files=['src/one.c', 'src/two.h'])
    sources, spec = make_archive(tmp_path, [
        ('src/3rdparty/libpng/qt_attribution.json', data),
        ('src/3rdparty/libpng/LICENSE', b'license'),
        ('src/3rdparty/shared/COPYRIGHT', b'copyright'),
        ('src/3rdparty/libpng/src/one.c', b'/* original notice in source */'),
        ('src/3rdparty/libpng/src/two.h', b'/* second original */'),
        ('src/3rdparty/libpng/src/other.c', b'unreferenced'),
    ])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    paths = {item['path'] for item in report['files']}
    assert 'qtbase/src/3rdparty/shared/COPYRIGHT' in paths
    assert 'qtbase/src/3rdparty/libpng/src/one.c' in paths
    assert 'qtbase/src/3rdparty/libpng/src/two.h' in paths
    assert 'qtbase/src/3rdparty/libpng/src/other.c' not in paths
    assert report['unresolved_references'] == []


def test_string_file_list_and_glob_are_resolved_within_archive(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/3rdparty/libpng/qt_attribution.json', attribution(Files='src/*.h README')),
        ('src/3rdparty/libpng/src/a.h', b'first'),
        ('src/3rdparty/libpng/src/b.h', b'second'),
        ('src/3rdparty/libpng/README', b'original notice in readme'),
    ])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert len(report['files']) == 4
    assert report['unresolved_references'] == []


def test_missing_reference_is_reported_not_silently_declared_complete(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/3rdparty/libpng/qt_attribution.json', attribution(LicenseFile='ABSENT')),
    ])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert report['notices_complete'] is False
    assert report['unresolved_references'][0]['reference'] == 'ABSENT'


def test_files_over_two_million_bytes_are_listed_not_copied(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('LICENSES/large.txt', b'x' * 2_000_001),
        ('LICENSES/boundary.txt', b'x' * 2_000_000),
    ])
    output = tmp_path / 'out'
    report = collector.collect_notices(sources, output, sources=(spec,))
    assert not (output / 'qtbase/LICENSES/large.txt').exists()
    assert (output / 'qtbase/LICENSES/boundary.txt').stat().st_size == 2_000_000
    assert report['skipped_large_files'][0]['path'] == 'qtbase/LICENSES/large.txt'
    assert report['skipped_large_files'][0]['size'] == 2_000_001
    assert report['notices_complete'] is False


@pytest.mark.parametrize('name', [
    '../escape', '/absolute', 'C:/outside', ARCHIVE_ROOT + '/../escape',
    ARCHIVE_ROOT + '/bad\\path', ARCHIVE_ROOT + '/LICENSE:stream',
    ARCHIVE_ROOT + '/CON.txt', ARCHIVE_ROOT + '/trailing. ',
])
def test_unsafe_member_is_rejected_before_any_output(tmp_path, name):
    collector = load_collector()
    member = tarfile.TarInfo(name)
    member.size = 1
    sources, spec = make_archive(tmp_path, [('LICENSE', b'valid'), (member, b'x')])
    output = tmp_path / 'out'
    with pytest.raises(ValueError, match='[Uu]nsafe|[Ii]nvalid'):
        collector.collect_notices(sources, output, sources=(spec,))
    assert not output.exists()


@pytest.mark.parametrize('kind', [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_links_and_special_members_are_never_extracted(tmp_path, kind):
    collector = load_collector()
    member = tarfile.TarInfo(ARCHIVE_ROOT + '/LICENSES/link')
    member.type = kind
    member.linkname = '../../outside'
    sources, spec = make_archive(tmp_path, [(member, b'')])
    with pytest.raises(ValueError, match='[Uu]nsafe|[Ss]pecial|[Ll]ink'):
        collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert not (tmp_path / 'out').exists()


def test_windows_case_collision_is_rejected(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'one'), ('license', b'two')])
    with pytest.raises(ValueError, match='[Dd]uplicate|[Cc]ollision'):
        collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))


@pytest.mark.parametrize('field,value', [('sha256', '0' * 64), ('size', 1)])
def test_archive_identity_mismatch_fails_before_output(tmp_path, field, value):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'original')])
    spec[field] = value
    with pytest.raises(ValueError, match='[Ss]ize|SHA256'):
        collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert not (tmp_path / 'out').exists()


def test_all_archives_validated_before_writing_any_notice(tmp_path):
    collector = load_collector()
    sources, first = make_archive(tmp_path, [('LICENSE', b'first')])
    _, second = make_archive(tmp_path, [('LICENSE', b'second')], module='qtsvg')
    second['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='SHA256'):
        collector.collect_notices(sources, tmp_path / 'out', sources=(first, second))
    assert not (tmp_path / 'out').exists()


def test_reference_cannot_escape_archive_root(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/3rdparty/libpng/qt_attribution.json', attribution(LicenseFile='../../../../outside')),
    ])
    with pytest.raises(ValueError, match='[Uu]nsafe|[Ee]scape'):
        collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))


def test_repeat_run_is_deterministic_and_does_not_rewrite_originals(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'original\r\n')])
    output = tmp_path / 'out'
    first = collector.collect_notices(sources, output, sources=(spec,))
    before = {p.relative_to(output): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in output.rglob('*') if p.is_file()}
    second = collector.collect_notices(sources, output, sources=(spec,))
    assert first == second
    assert before == {p.relative_to(output): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in output.rglob('*') if p.is_file()}


def test_existing_modified_notice_is_not_overwritten(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'original')])
    output = tmp_path / 'out'
    path = output / 'qtbase/LICENSE'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'user content')
    with pytest.raises(ValueError, match='[Ee]xisting|[Dd]iffers'):
        collector.collect_notices(sources, output, sources=(spec,))
    assert path.read_bytes() == b'user content'
    assert not (output / 'provenance.json').exists()


def test_output_symlink_is_rejected(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'original')])
    outside = tmp_path / 'outside'
    outside.mkdir()
    output = tmp_path / 'out'
    try:
        output.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Host does not permit symlink creation')
    with pytest.raises(ValueError, match='[Ll]ink|[Jj]unction'):
        collector.collect_notices(sources, output, sources=(spec,))
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize('path,preamble,header', [
    ('src/corelib/time/qtimezonelocale_data_p.h', b'',
     b'// Copyright (C) original\r\n// SPDX-License-Identifier: Unicode-3.0\r\n'),
    ('src/gui/vulkan/vk.xml', b'<?xml version="1.0"?>\n<registry>\n',
     b'    <comment>\nCopyright original\nSPDX-License-Identifier: Apache-2.0 OR MIT\n    </comment>\n'),
])
def test_known_large_files_have_byte_exact_notice_excerpt_and_original_identity(
        tmp_path, path, preamble, header):
    collector = load_collector()
    data = preamble + header + b'\n' + b'x' * 2_000_001
    parent, filename = path.rsplit('/', 1)
    sources, spec = make_archive(tmp_path, [
        (parent + '/qt_attribution.json', attribution(Files=filename)),
        (path, data),
    ])
    output = tmp_path / 'out'
    report = collector.collect_notices(sources, output, sources=(spec,))
    excerpt_path = 'qtbase/' + path + '.copyright-notice.txt'
    assert not (output / 'qtbase' / path).exists()
    assert (output / excerpt_path).read_bytes() == header
    record = next(item for item in report['files'] if item['path'] == excerpt_path)
    assert record['kind'] == 'byte-exact-copyright-excerpt'
    assert record['source_byte_offset'] == len(preamble)
    assert record['source_byte_length'] == len(header)
    assert record['original_file_sha256'] == hashlib.sha256(data).hexdigest()
    assert record['original_file_size'] == len(data)
    assert record['full_original_in_source_archive'] is True
    assert report['notices_complete'] is True
    assert report['full_selected_files_copied'] is False
    assert report['skipped_large_files'][0]['notice_excerpt'] == excerpt_path


def test_unrecognized_large_header_is_not_guessed(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/gui/vulkan/qt_attribution.json', attribution(Files='vk.xml')),
        ('src/gui/vulkan/vk.xml', b'Not the known copyright header\n' + b'x' * 2_000_001),
    ])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert report['notices_complete'] is False
    assert all(not item['path'].endswith('.copyright-notice.txt') for item in report['files'])


def test_nested_license_directory_is_preserved_without_named_license_keyword(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('src/3rdparty/libpng/LICENSES/CC0-1.0.txt', b'terms')])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert report['files'][0]['path'] == 'qtbase/src/3rdparty/libpng/LICENSES/CC0-1.0.txt'


def test_glob_does_not_expand_across_directory_boundaries(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/3rdparty/libpng/qt_attribution.json', attribution(Files='src/*.h')),
        ('src/3rdparty/libpng/src/a.h', b'first'),
        ('src/3rdparty/libpng/src/nested/extra.h', b'not requested'),
    ])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert len(report['files']) == 2


def test_file_directory_conflict_is_rejected_before_output(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSES', b'file'), ('LICENSES/MIT.txt', b'terms')])
    with pytest.raises(ValueError, match='[Cc]onflict|[Dd]irectory'):
        collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert not (tmp_path / 'out').exists()


def test_documentation_image_with_license_in_name_is_not_a_notice(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/widgets/doc/images/licensewizard-flow.png', b'\x89PNG\r\n\x1a\n\x00image'),
        ('src/widgets/LICENSE.txt', b'original license'),
    ])
    output = tmp_path / 'out'
    report = collector.collect_notices(sources, output, sources=(spec,))
    assert [item['path'] for item in report['files']] == ['qtbase/src/widgets/LICENSE.txt']
    assert not (output / 'qtbase/src/widgets/doc/images/licensewizard-flow.png').exists()


def test_icc_profile_is_archive_reference_with_original_license_not_binary_copy(tmp_path):
    collector = load_collector()
    profile = b'ICC binary\x00profile'
    license_text = b'Copyright International Color Consortium, 2015\r\nOriginal terms.\r\n'
    parent = 'src/3rdparty/icc/'
    sources, spec = make_archive(tmp_path, [
        (parent + 'qt_attribution.json', attribution(Files='sRGB2014.icc', LicenseFile='LICENSE.txt')),
        (parent + 'sRGB2014.icc', profile),
        (parent + 'LICENSE.txt', license_text),
    ])
    output = tmp_path / 'out'
    report = collector.collect_notices(sources, output, sources=(spec,))
    assert not (output / 'qtbase' / parent / 'sRGB2014.icc').exists()
    assert (output / 'qtbase' / parent / 'LICENSE.txt').read_bytes() == license_text
    reference = report['archive_only_files'][0]
    assert reference['path'] == 'qtbase/' + parent + 'sRGB2014.icc'
    assert reference['sha256'] == hashlib.sha256(profile).hexdigest()
    assert reference['size'] == len(profile)
    assert reference['archive_member'] == ARCHIVE_ROOT + '/' + parent + 'sRGB2014.icc'
    assert reference['archive'] == spec['archive']
    assert reference['full_original_in_source_archive'] is True
    assert reference['notice_files'] == ['qtbase/' + parent + 'LICENSE.txt']
    assert report['notices_complete'] is True
    assert report['full_selected_files_copied'] is False


def test_icc_profile_without_license_text_is_not_declared_complete(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [
        ('src/3rdparty/icc/qt_attribution.json', attribution(Files='sRGB2014.icc')),
        ('src/3rdparty/icc/sRGB2014.icc', b'ICC\x00binary'),
    ])
    report = collector.collect_notices(sources, tmp_path / 'out', sources=(spec,))
    assert report['notices_complete'] is False
    assert report['archive_only_files'][0]['notice_files'] == []


def test_manifest_refresh_is_explicit_and_preserves_original_file_mtime(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'original\r\n')])
    output = tmp_path / 'out'
    collector.collect_notices(sources, output, sources=(spec,))
    original = output / 'qtbase/LICENSE'
    before = original.stat().st_mtime_ns
    manifest = output / 'provenance.json'
    manifest.write_bytes(b'{"old_generated_manifest": true}\n')
    with pytest.raises(ValueError, match='[Ee]xisting'):
        collector.collect_notices(sources, output, sources=(spec,))
    report = collector.collect_notices(sources, output, sources=(spec,), refresh_manifest=True)
    assert json.loads(manifest.read_bytes()) == report
    assert original.read_bytes() == b'original\r\n'
    assert original.stat().st_mtime_ns == before


def test_manifest_refresh_still_refuses_to_overwrite_modified_original(tmp_path):
    collector = load_collector()
    sources, spec = make_archive(tmp_path, [('LICENSE', b'original')])
    output = tmp_path / 'out'
    collector.collect_notices(sources, output, sources=(spec,))
    (output / 'qtbase/LICENSE').write_bytes(b'modified')
    before = (output / 'provenance.json').read_bytes()
    with pytest.raises(ValueError, match='[Ee]xisting'):
        collector.collect_notices(sources, output, sources=(spec,), refresh_manifest=True)
    assert (output / 'provenance.json').read_bytes() == before
