# Native Runtime Notice Sources

These are unmodified upstream documents collected for the Windows review.
They supplement, not replace, the Python and Python-package license files
collected by the packager.

| Local document | Source |
| --- | --- |
| python-3.12.14-acknowledgements.rst | https://raw.githubusercontent.com/python/cpython/v3.12.14/Doc/license.rst |
| openssl-3.5.8-LICENSE.txt | https://raw.githubusercontent.com/openssl/openssl/openssl-3.5.8/LICENSE.txt |
| libffi-3.4.6-LICENSE | https://raw.githubusercontent.com/libffi/libffi/v3.4.6/LICENSE |
| mingw-w64-8.0.0-COPYING | https://raw.githubusercontent.com/mingw-w64/mingw-w64/v8.0.0/COPYING |
| gcc-10.3.0-COPYING.RUNTIME | https://raw.githubusercontent.com/gcc-mirror/gcc/releases/gcc-10.3.0/COPYING.RUNTIME |

Python reports 3.12.14 and OpenSSL 3.5.8 in the tested environment. The FFmpeg
binary reports GCC 10-win32 (20220113). Its upstream recipe uses Ubuntu 22.04
and the distribution's mingw-w64 package without an exact package lock.
The libffi DLL has no embedded version resource. Consequently, the libffi and
compiler-runtime document versions are reference material, not proof of the
exact revisions compiled into those binaries. That provenance gap remains in
the binary redistribution review. The GCC runtime exception text must be read
with the GPLv3 text at ../GPL-3.0.txt.

Microsoft runtime notices and redistribution restrictions are preserved in the
packaged Python LICENSE. They are not covered by this application's MIT license.
Windows system UCRT/API-set DLLs are supplied by Windows; the build must not
copy unrelated versions from other applications on PATH.
