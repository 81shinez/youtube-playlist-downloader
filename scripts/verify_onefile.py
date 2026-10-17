"""Copy just the Windows EXE into a clean directory and verify it offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def validate_entries(names):
    entries = {name.replace('\\', '/').lower() for name in names}
    for name in entries:
        basename = name.rsplit('/', 1)[-1]
        if (name.startswith('imageio_ffmpeg/binaries/') or basename == 'opengl32sw.dll'
                or basename == 'ucrtbase.dll' or basename.startswith('api-ms-win-')):
            raise ValueError(f'Unexpected native file in packaged application: {name}')
    if not {'media/ffmpeg.exe', 'media/ffprobe.exe'} <= entries:
        raise ValueError('Missing pinned media helpers in packaged application')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    source = args.executable.resolve(strict=True)
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(source))
    validate_entries(archive.toc)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='onefile-', dir=output) as temporary:
        folder = Path(temporary)
        executable = folder / source.name
        shutil.copy2(source, executable)
        if list(folder.iterdir()) != [executable]:
            raise RuntimeError('Verification directory must contain only the EXE')
        report_path = folder / 'report.json'
        env = os.environ.copy()
        for name in ('PYTHONPATH', 'PYTHONHOME', 'IMAGEIO_FFMPEG_EXE'):
            env.pop(name, None)
        if os.name == 'nt':
            env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
        env['QT_QPA_PLATFORM'] = 'offscreen'
        process = subprocess.Popen(
            [str(executable), '--verify-package', str(report_path)], cwd=folder, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            exit_code = process.wait(timeout=75)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=10, check=False)
            process.kill()
            process.wait(timeout=5)
            raise RuntimeError('Single-file verification exceeded 75 seconds') from None
        if not report_path.is_file():
            raise RuntimeError(f'Application exited without a verification report (exit {exit_code})')
        report = json.loads(report_path.read_text(encoding='utf-8'))
        report['native_archive_policy'] = True
        with source.open('rb') as stream:
            report['executable_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if exit_code or not report.get('ok') or not report.get('worker_stopped'):
            raise RuntimeError(f'Packaged application verification failed: {report}')
        extracted = report.get('extracted_dir')
        if not extracted or Path(extracted).exists():
            raise RuntimeError('The single-file extraction directory was not cleaned up')
        report['extraction_cleaned'] = True
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('EXE-only verification passed: GUI, worker IPC, media helper, bundled FFmpeg, MP3 and clean shutdown.')
        print(f'Report: {output / "report.json"}')


if __name__ == '__main__':
    main()
