# -*- mode: python ; coding: utf-8 -*-

from importlib import metadata
from pathlib import Path
import os
import sys
import tomllib
from packaging.requirements import Requirement

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_ffmpeg import prepare, target_key
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
ONEFILE = sys.platform == 'win32' and os.environ.get('YMD_ONEFILE', '1') == '1'
runtime_metadata = copy_metadata("youtube-music-downloader", recursive=True)
# PyInstaller's recursive metadata collector does not propagate uvicorn[standard].
for requirement_text in metadata.requires("uvicorn") or ():
    requirement = Requirement(requirement_text)
    if requirement.marker and not requirement.marker.evaluate({"extra": "standard"}):
        continue
    try:
        runtime_metadata.extend(copy_metadata(requirement.name, recursive=True))
    except metadata.PackageNotFoundError:
        continue
runtime_metadata = list(dict.fromkeys(runtime_metadata))


def license_files():
    files = []
    names = {
        "PySide6-Essentials", "shiboken6", "imageio-ffmpeg", "yt-dlp",
        "fastapi", "starlette", "pydantic", "pydantic-core", "uvicorn", "pyinstaller",
    }
    for metadata_path, _ in runtime_metadata:
        name = metadata.Distribution.at(metadata_path).metadata.get("Name")
        if name:
            names.add(name)
    for name in sorted(names):
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for relative in distribution.files or ():
            if ".." in relative.parts:
                continue
            is_license = relative.name.lower().startswith(("license", "licence", "copying", "notice"))
            in_license_dir = any(part.lower() in {"licenses", "licences"} for part in relative.parts[:-1])
            if is_license or in_license_dir:
                source = Path(distribution.locate_file(relative))
                if source.is_file():
                    files.append((str(source), str(Path("licenses/packages") / name / relative.parent)))
    for pattern in ("LICENSE*", "COPYING*", "NOTICE*"):
        files.extend((str(path), "licenses/project") for path in ROOT.glob(pattern) if path.is_file())
    for path in (ROOT / "licenses").rglob("*"):
        if path.is_file():
            files.append((str(path), str(Path("licenses") / path.relative_to(ROOT / "licenses").parent)))
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        files.append((str(ROOT / name), "."))
    files.append((str(ROOT / "docs" / "DISTRIBUTION.md"), "docs"))
    for name in ("LICENSE.txt", "LICENSE"):
        python_license = Path(sys.base_prefix) / name
        if python_license.is_file():
            files.append((str(python_license), "licenses/Python"))
            break
    return files


yt_dlp_data = collect_data_files("yt_dlp")
media_imports = collect_submodules("yt_dlp")
ffmpeg_binaries = [(str(path), 'media') for path in prepare(ROOT)]

media_data = (
    yt_dlp_data
    + runtime_metadata
    + license_files()
    + [(str(ROOT / 'release-materials' / 'ffmpeg' / target_key() / 'provenance.json'), 'licenses/FFmpeg')]
)

gui = Analysis(
    [str(ROOT / "scripts" / "desktop_entry.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("youtube_music_downloader") + [(str(ROOT / "README.md"), ".")],
    hiddenimports=media_imports + [
        "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets",
        "youtube_music_downloader.api", "uvicorn.logging", "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    ],
    excludes=["PyQt5", "PyQt6", "PySide2", "tkinter", "imageio_ffmpeg"],
)
worker = Analysis(
    [str(ROOT / "scripts" / "worker_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=ffmpeg_binaries,
    datas=media_data,
    hiddenimports=media_imports,
    excludes=["PySide6", "shiboken6", "PyQt5", "PyQt6", "PySide2", "tkinter", "imageio_ffmpeg"],
)

# This QWidget application uses raster rendering, not the legacy Mesa/LLVM
# software-OpenGL fallback bundled with Qt wheels.
gui.binaries = [entry for entry in gui.binaries if Path(entry[0]).name.lower() != 'opengl32sw.dll']

worker_exe = EXE(
    PYZ(worker.pure), worker.scripts, [],
    exclude_binaries=True,
    name="ytm-worker",
    console=True,
    strip=False,
    upx=False,
    contents_directory='.' if ONEFILE else '_internal',
)

if ONEFILE:
    # The console helper shares the outer EXE's extracted libraries at runtime.
    gui_exe = EXE(
        PYZ(gui.pure), gui.scripts,
        gui.binaries, gui.datas, worker.binaries, worker.datas,
        [('ytm-worker.exe', worker_exe.name, 'EXECUTABLE')],
        name='YTMusicDownloader', console=False, strip=False, upx=False,
    )
else:
    gui_exe = EXE(
        PYZ(gui.pure), gui.scripts, [],
        exclude_binaries=True, name='YTMusicDownloader',
        console=False, strip=False, upx=False,
    )
    collection = COLLECT(
        gui_exe, worker_exe,
        gui.binaries, gui.datas, worker.binaries, worker.datas,
        strip=False, upx=False, name='YTMusicDownloader',
    )

if sys.platform == "darwin":
    # BUNDLE places both EXECUTABLE entries in Contents/MacOS.
    app = BUNDLE(
        collection,
        name="YTMusicDownloader.app",
        bundle_identifier="org.youtube-music-downloader.desktop",
        version=PROJECT["version"],
        info_plist={
            "CFBundleDisplayName": "YouTube Music Downloader",
            "CFBundleExecutable": "YTMusicDownloader",
            "NSHighResolutionCapable": True,
            # COLLECT inherits console=True from the last EXE (the helper).
            "LSBackgroundOnly": False,
        },
    )
