"""Build the standalone desktop app for this host OS and Python architecture."""

import argparse
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def build_environment(onefile: bool) -> dict[str, str]:
    env = os.environ.copy()
    env['YMD_ONEFILE'] = '1' if onefile else '0'
    if sys.platform == 'win32':
        # Do not collect DLLs from unrelated applications on the developer's PATH.
        env['PATH'] = os.pathsep.join([
            str(Path(sys.executable).parent), sys.base_prefix,
            str(Path(env.get('SystemRoot', 'C:/Windows')) / 'System32'),
        ])
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="Clear PyInstaller's build cache first.")
    parser.add_argument("--onedir", action="store_true", help="Build the legacy folder layout on Windows.")
    parser.add_argument("--release", action="store_true", help="Require public binary redistribution approval.")
    args = parser.parse_args()

    if args.release:
        from release_check import binary_blockers
        for problem in binary_blockers(ROOT):
            print('BLOCKED: ' + problem)
        return 1

    if sys.version_info < (3, 12):
        parser.error("Python 3.12 or newer is required.")
    if sys.platform not in {"win32", "darwin", "linux"}:
        parser.error("Supported build hosts are Windows, macOS, and Linux; cross-compilation is not supported.")
    if importlib.util.find_spec("PyInstaller") is None:
        parser.error('Build dependencies are missing. Run: python -m pip install -e ".[build]"')

    onefile = sys.platform == 'win32' and not args.onedir
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / ('onefile' if onefile else 'desktop')),
    ]
    if args.clean:
        command.append("--clean")
    command.append(str(ROOT / "scripts" / "desktop.spec"))
    env = build_environment(onefile)
    print('LOCAL TEST BUILD ONLY: public binary distribution is not approved.', flush=True)
    process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=os.name != 'nt')
    try:
        code = process.wait(timeout=300)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, timeout=10, check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.wait(timeout=5)
        raise RuntimeError('Build interrupted or exceeded 300 seconds; child processes stopped.') from None
    if code:
        raise subprocess.CalledProcessError(code, command)

    if onefile:
        artifact = ROOT / 'dist' / 'YTMusicDownloader.exe'
        if not artifact.is_file():
            raise RuntimeError(f'The build did not produce {artifact}')
        print(f'Single-file desktop artifact: {artifact}')
        print('This EXE runs alone, but is for local testing only. See docs/DISTRIBUTION.md before redistribution.')
        return 0

    if sys.platform == "darwin":
        artifact = ROOT / "dist" / "YTMusicDownloader.app"
        executable_dir = artifact / "Contents" / "MacOS"
    else:
        artifact = ROOT / "dist" / "YTMusicDownloader"
        executable_dir = artifact
    suffix = ".exe" if sys.platform == "win32" else ""
    for name in ("YTMusicDownloader", "ytm-worker"):
        executable = executable_dir / f"{name}{suffix}"
        if not executable.is_file():
            raise RuntimeError(f"The build did not produce the required executable: {executable}")

    print(f"Desktop artifact: {artifact}")
    print(f"Worker executable: {executable_dir / ('ytm-worker' + suffix)}")
    print("Local test build only. The complete directory/.app is required. See docs/DISTRIBUTION.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
