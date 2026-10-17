# Third-Party Notices

The original YouTube Music Downloader source is MIT licensed. This does not
relicense Python, Qt, FFmpeg, yt-dlp, or any other dependency. No affiliation
with or endorsement by YouTube, Google, Qt, or FFmpeg is implied.

## Qt / PySide6 / Shiboken

This application uses Qt through PySide6-Essentials (QtCore, QtGui, QtWidgets)
and Shiboken under the GNU Lesser General Public License version 3 (LGPLv3).
Qt and PySide are copyright their respective upstream contributors and The Qt
Company Ltd. Full LGPLv3 and GPLv3 texts are in licenses/. LGPLv3 incorporates
GPLv3. Upstream notices collected from the installed wheels are preserved too;
a commercial-license reference in a wheel does not give this project a
commercial Qt license.

Users retain their LGPL rights to modify the libraries, use the application
with modified libraries, and reverse engineer it for debugging such changes.
The application's MIT license does not restrict those rights. Instructions and
the status of corresponding-source preparation are in docs/DISTRIBUTION.md.

- https://code.qt.io/cgit/pyside/pyside-setup.git/
- https://code.qt.io/cgit/qt/qtbase.git/
- https://www.qt.io/faq/qt-open-source-licensing

## FFmpeg and imageio-ffmpeg

FFmpeg is invoked as a separate executable. Packaged builds now use the
audio-encode variant from acoustid/ffmpeg-build v8.1.2-1: FFmpeg 8.1.2 with
LAME 3.100, without --enable-gpl or --enable-nonfree. This uses LGPLv2.1-or-later
components. Original license texts are in licenses/audio-ffmpeg/. The pinned
sources, recipe and binary archive hashes are in scripts/prepare_ffmpeg.py;
the exact packaged helper hashes are embedded in licenses/FFmpeg/provenance.json.
The recipe commit is bd5eb2e6ab4a56e9823a5216e838b53749de61cf.

The Windows binary's local audio conversion is verified. Other platform assets
are pinned but not locally executed on Windows. The compiler-runtime provenance
limitation is recorded in licenses/native-runtime/SOURCES.md.

imageio-ffmpeg remains a development fallback, not a packaged executable source.
Its Python wrapper is BSD-2-Clause, but its Windows 0.6.0 FFmpeg 7.1 Gyan binary
is GPLv3. The packager explicitly excludes that fallback and does not relicense
it. These components are copyright their respective upstream authors.

- https://ffmpeg.org/legal.html
- https://github.com/acoustid/ffmpeg-build/tree/v8.1.2-1
- https://github.com/imageio/imageio-ffmpeg

## Other Dependencies

| Component | Upstream license / role |
| --- | --- |
| yt-dlp | Unlicense; extractor and downloader. Optional dependencies retain their licenses. |
| Python | PSF license and bundled third-party notices; interpreter runtime. |
| PyInstaller | GPL with the bootloader/bundling exception; packaging tool. |
| FastAPI, Starlette, Uvicorn, Pydantic | MIT; optional local web mode and validation. |
| Transitive Python and native libraries | Their original licenses and notices, not the application MIT license. |

Package notices are collected recursively from installed runtime metadata into
licenses/packages/ when building. Python's LICENSE is included when available.
This collection is not a complete native-library license audit: Qt plugins,
OpenSSL, graphics/runtime DLLs, and FFmpeg's linked libraries must be checked
against each actual platform artifact before redistribution.

## Distribution Status

Source-only publication checks and local builds are supported. PUBLIC BINARY
DISTRIBUTION IS BLOCKED pending the items in docs/DISTRIBUTION.md. The repository
now includes reproducible exporters for local app-source and dependency-source
archives. Official version-matched Qt/PySide sources and FFmpeg/LAME sources are
available locally, but exact Qt wheel build/patch and some native-runtime
provenance remain unverified. No unsupported source-delivery promise is made.

The desktop Help menu exposes these notices and the packaged license texts
without a network connection. Build logs and installed package metadata identify
versions; do not assume an unconstrained future build uses the versions above.
