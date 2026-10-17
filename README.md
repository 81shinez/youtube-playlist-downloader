# YouTube Music Downloader

YouTube / YouTube Music 재생목록을 MP3로 저장하는 로컬 데스크톱 앱입니다.
기본 실행 화면은 PySide6 네이티브 창이며, 브라우저나 로컬 웹 서버가 필요하지 않습니다.
다운로드하거나 보관할 권한이 있는 콘텐츠에만 사용하세요.

프로젝트 자체 소스는 [MIT 라이선스](LICENSE)입니다. YouTube/Google과 제휴한 공식 앱이 아닙니다.
소스 라이선스는 콘텐츠 다운로드 권한을 부여하지 않으며, 저작권과
[YouTube 이용약관](https://www.youtube.com/static?template=terms)을 별도로 준수해야 합니다.
현재 **소스 공개 준비와 로컬 테스트용 빌드만 지원**합니다. FFmpeg·Qt의 대응 소스 검증이
완료되지 않아 EXE 등 바이너리의 공개 배포는 차단했습니다. [배포 체크리스트](docs/DISTRIBUTION.md)를 확인하세요.

## 설치

소스 실행과 빌드에는 Python 3.12 이상이 필요합니다. 배포용으로 빌드한 Windows 단일 EXE,
macOS `.app`, Linux 폴더에는 Python과 필요한 라이브러리가 포함됩니다.
Windows 기본 빌드는 `YTMusicDownloader.exe` 하나만 복사하여 실행할 수 있습니다.
이는 실행 파일 구성에 대한 설명이며, 별도의 라이선스 재배포 의무를 면제하지 않습니다.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\ytm-downloader.exe
```

### macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/ytm-downloader
```

Linux에서는 그래픽 데스크톱 세션과 Qt 플랫폼 플러그인이 사용하는 시스템 라이브러리가
필요합니다. Ubuntu 22.04 기준으로 다음 패키지를 설치할 수 있습니다.

```bash
sudo apt-get install libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0
```

GUI에는 `PySide6-Essentials`의 QtCore, QtGui, QtWidgets를 사용합니다.
QtWebEngine이나 전체 `PySide6` 패키지는 필요하지 않습니다. 미디어 다운로드는
`yt-dlp`, MP3 변환은 FFmpeg가 담당합니다. 소스 실행은 `imageio-ffmpeg` 또는 `PATH`의
FFmpeg를 사용합니다. 패키징은 소스와 해시가 고정된 오디오 전용 FFmpeg 8.1.2를 별도로
포함하며, 개발용 `imageio-ffmpeg` 바이너리는 포함하지 않습니다.

## 실행과 사용

가상환경의 `ytm-downloader`를 실행하거나, 다음처럼 Python 모듈로 실행할 수 있습니다.

```powershell
.\.venv\Scripts\python -m youtube_music_downloader.main
```

macOS / Linux에서는 위 명령의 Python 경로를 `.venv/bin/python`으로 바꾸세요.

1. 재생목록 URL과 저장 폴더를 지정합니다.
2. 출력 모드, 동시 작업 수(1~4), 브라우저 쿠키 설정을 선택합니다.
3. 작업을 시작한 뒤 곡별 진행 상태를 확인합니다. 실패한 곡은 개별 또는 일괄 재시도할 수 있습니다.

### 일시 정지와 취소

- 일시 정지는 대기 중인 곡을 새로 시작하지 않도록 합니다. 이미 분석, 다운로드 또는 변환
  중인 곡은 계속 진행할 수 있으며, 실행 중인 프로세스를 운영체제 수준에서 정지시키는 기능은 아닙니다.
- 재개하면 대기 중인 곡 처리를 이어갑니다. 앱을 종료한 뒤 이어받는 영구 저장 기능과는 다릅니다.
- 작업 전체를 취소할 수 있습니다. 이미 저장된 완료 파일은 자동 삭제하지 않습니다.

### 브라우저 쿠키

YouTube가 로그인 또는 봇 확인을 요구하면, YouTube에 로그인한 브라우저를 선택하세요.
Chrome, Edge, Firefox, Brave 쿠키를 재생목록 분석, 원본 비트레이트 조회, 다운로드에 전달합니다.
브라우저 프로필 잠금, 운영체제 암호화 또는 접근 권한 때문에 쿠키를 읽지 못할 수 있으며,
쿠키 사용이 모든 인증 문제를 해결하지는 않습니다. 브라우저 쿠키 파일을 배포본이나 저장소에 넣지 마세요.

### 출력 모드

- `MP3 192kbps`: 모든 완료 파일을 192kbps MP3로 저장합니다.
- `MP3 maximum`: 추정 원본 오디오 비트레이트를 사용하되 최대 320kbps로 제한합니다.
  원본 비트레이트를 알 수 없으면 256kbps를 사용합니다.

MP3 변환은 호환성을 위한 재인코딩입니다. 원본보다 높은 비트레이트로 저장해도 원본에 없던
음질이 복원되지는 않습니다.

## 선택 사항: 기존 웹 모드

웹 UI와 HTTP API는 `--web`을 지정할 때만 실행합니다.

```powershell
.\.venv\Scripts\python -m youtube_music_downloader.main --web
```

[로컬 웹 UI](http://127.0.0.1:8000)를 여세요. 웹 모드 로그를 보려면 Windows의 GUI 런처 대신
위 Python 명령을 사용하세요. 기본 의존성의 FastAPI, Uvicorn은 웹 모드 호환을 위해 유지합니다.
웹 모드는 로컬 전용입니다. 포트 포워딩·공개 터널·프록시로 외부에 노출하지 마세요.
API는 실행마다 바뀌는 토큰과 Host/Origin을 검사합니다. 웹 UI는 토큰을 자동으로 받아 사용하며,
직접 호출하는 클라이언트도 토큰과 JSON Content-Type을 제공해야 합니다.
네트워크 공유(UNC) 및 장치 경로는 저장 폴더로 허용하지 않습니다. [보안 안내](SECURITY.md)

### HTTP API

- `POST /api/jobs`: `playlist_url`, `output_dir`, `output_mode` (`192` 또는 `max`),
  `concurrency` (1~4), 선택 사항인 `cookie_source` (`chrome`, `edge`, `firefox`, `brave`)로 작업 생성.
- `GET /api/jobs/{job_id}`: 작업 상태, 요약, 곡 목록 조회.
- `POST /api/jobs/{job_id}/tracks/{track_id}/retry`: 실패하거나 완료된 곡 하나 재시도.
- `POST /api/jobs/{job_id}/retry-failed`: 실패한 곡 일괄 재시도.
- `POST /api/jobs/{job_id}/pause`: 대기 중인 곡의 새 실행 중단.
- `POST /api/jobs/{job_id}/resume`: 일시 정지한 작업 재개.
- `POST /api/jobs/{job_id}/cancel`: 작업 전체 취소.
- `POST /api/jobs/{job_id}/tracks/{track_id}/cancel`: 곡 하나 취소.
- `POST /api/jobs/{job_id}/open-output-folder`: 로컬 클라이언트에서 작업의 저장 폴더 열기.

## 데스크톱 배포본 빌드

대상 운영체제에서 가상환경을 활성화한 뒤 실행합니다.

```bash
python -m pip install -e ".[build]"
python scripts/prepare_ffmpeg.py --download
python scripts/build_desktop.py
```

`--clean`을 추가하면 PyInstaller 캐시를 정리하고 다시 빌드합니다. 스크립트 자체는 의존성을
설치하지 않습니다. 현재 호스트 운영체제와 Python 아키텍처용으로만 빌드하며, Windows에서
macOS 앱을 만드는 등의 교차 컴파일은 지원하지 않습니다.
빌드는 5분을 초과하면 하위 프로세스를 종료합니다. 공개 배포 검사를 포함하는 `--release`는
현재 대응 소스 준비 미완료로 실패합니다. 일반 빌드는 로컬 검증용으로만 사용하세요.

Windows에서는 기본적으로 onefile 모드로 `dist/YTMusicDownloader.exe`를 만듭니다.
기존 Windows 폴더형 배포본이 필요하면 `python scripts/build_desktop.py --onedir`를 사용하세요.
macOS의 기본 `.app`과 Linux의 기본 폴더형 출력은 그대로 유지됩니다.

| 빌드 호스트 | 배포할 결과물 | GUI 실행 파일 | 콘솔 워커 |
| --- | --- | --- | --- |
| Windows (기본 onefile) | `dist/YTMusicDownloader.exe` 하나 | `YTMusicDownloader.exe` | EXE에 내장, 실행 시 임시 폴더에 추출 |
| Windows (`--onedir`) | `dist/YTMusicDownloader/` 전체 | `YTMusicDownloader.exe` | 같은 폴더의 `ytm-worker.exe` |
| macOS | `dist/YTMusicDownloader.app` 전체 | `Contents/MacOS/YTMusicDownloader` | `Contents/MacOS/ytm-worker` |
| Linux | `dist/YTMusicDownloader/` 전체 | `YTMusicDownloader` | 같은 폴더의 `ytm-worker` |

Windows 기본 빌드는 EXE만으로 실행됩니다. 런타임, 워커와 FFmpeg가 EXE에 내장되어 있으며,
실행 시 PyInstaller가 `sys._MEIPASS`가 가리키는 임시 폴더에 자동으로 추출합니다.
따로 압축을 풀거나 워커/FFmpeg를 옆에 둘 필요는 없지만, 추출 과정 때문에 첫 시작이 더 느릴 수 있습니다.
Windows에서 전체 폴더를 함께 복사해야 하는 것은 `--onedir` 배포본뿐입니다.

macOS에서는 `.app`을 열고, Linux에서는 배포 폴더의 `./YTMusicDownloader`를 실행하세요.
Windows `--onedir`와 Linux 폴더형 배포본은 `_internal`을 포함한 전체 폴더가 필요하며,
macOS는 `.app/Contents`의 라이브러리와 데이터를 포함한 전체 `.app`이 필요합니다.
macOS에서 함께 생성되는 일반 onedir
폴더 대신 `.app`을 배포하고, ZIP을 만들 때는 `ditto`처럼 심볼릭 링크를 보존하는 도구를 사용하세요.
Linux는 실행 권한과 심볼릭 링크를 보존하는 `tar` 아카이브를 권장합니다.

### 패키징 인터페이스

- `scripts/desktop_entry.py`는 `youtube_music_downloader.main:main`을 호출합니다.
- `scripts/worker_entry.py`는 `--desktop-worker`를 `desktop_worker.main()`으로,
  `--media-process`를 `media_process.main()`으로 전달합니다. 라우트 플래그만 제거하고
  나머지 인자는 유지합니다. 이 두 플래그는 내부 프로세스용입니다.
- Windows onefile 실행 시 내장 워커는 `sys._MEIPASS` 임시 폴더에 추출된 런타임에서 찾습니다.
  Windows `--onedir`에서는 `Path(sys.executable).parent / "ytm-worker.exe"`,
  macOS / Linux에서는 `Path(sys.executable).parent / "ytm-worker"`를 사용합니다.
- Windows GUI는 `console=False`, 워커는 `console=True`입니다. GUI 실행 파일을 IPC 워커로
  다시 실행하면 표준 입출력이 `None`이 될 수 있으므로 반드시 별도 워커를 실행해야 합니다.
  호출 측에서 표준 입출력 파이프를 연결하고 `CREATE_NO_WINDOW` 등으로 콘솔 창을 숨깁니다.
- Windows onefile은 워커와 필요한 런타임을 GUI EXE에 내장합니다. 기존 onedir 패키징은
  두 `Analysis`와 하나의 `COLLECT`를 사용하며, 워커 분석에서 Qt를 제외하고
  두 실행 파일이 같은 외부 라이브러리 디렉터리를 공유합니다.
- `yt_dlp` 데이터와 하위 모듈, 검증된 오디오 전용 FFmpeg/ffprobe를 `media/`에 포함합니다.
  `prepare_ffmpeg.py`는 다운로드별 시간 제한과 SHA-256 검사를 적용합니다.
  Qt 라이브러리와 플랫폼 플러그인은 PyInstaller의 PySide6 훅으로 수집합니다.
- 설치된 배포 패키지에서 찾을 수 있는 라이선스/고지 파일을 `licenses/` 아래에 포함합니다.
  Windows onefile에서는 EXE에 내장되어 런타임과 함께 임시 폴더에 추출됩니다.
  Windows `--onedir` / Linux에서는 `_internal/licenses`, macOS에서는 `Contents/Resources/licenses`에
  들어갑니다. 패키지 메타데이터의 라이선스 파일도 보존합니다. 이 자동 수집만으로 모든
  재배포 의무가 확인되었다고 간주하지 않으며, 배포 전 포함 바이너리의 조건을 별도로 확인해야 합니다.
- 앱의 `도움말 > 오픈소스 라이선스`에서 프로젝트·의존성 고지와 라이선스 전문을 오프라인으로
  열람할 수 있습니다. [서드파티 고지](THIRD_PARTY_NOTICES.md)와 [배포 안내](docs/DISTRIBUTION.md)도 함께 포함합니다.

폴더형 구조는 [PyInstaller onedir 멀티패키지 문서](https://pyinstaller.org/en/stable/spec-files.html#multipackaging-with-one-folder-apps)를 참고하세요.
Windows onefile과 onedir 모두 [Windows windowed 표준 입출력 제한](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#sys-stdin-sys-stdout-and-sys-stderr-in-noconsole-windowed-applications-windows-only)에 따라 별도 콘솔 워커를 사용합니다.

### CI 검증

`.github/workflows/desktop-build.yml`은 `windows-latest`, `macos-14`, `ubuntu-22.04`에서
각각 Python 3.12로 네이티브 빌드합니다. 테스트와 공개 소스 검사를 수행하지만,
미검증 바이너리가 공개되지 않도록 아티팩트 업로드는 하지 않습니다.
관련 파일의 push / pull request 또는 수동 실행으로 동작하며,
릴리스 게시, 설치 프로그램 생성, 배포 서명 또는 macOS 공증은 하지 않습니다.

소스 공개 전에는 `python scripts/release_check.py`를 실행하세요.
`python scripts/release_check.py --binary`는 남은 의무를 출력하고 실패합니다.
검사 성공이 모든 비밀정보 부재나 법적 준수를 보증하지는 않습니다.

Git 이력 없이 현재 소스만 내보내려면 다음 명령을 사용합니다. 기존 `.git`은 변경하지 않습니다.
쿠키, 로그, 음원, 가상환경, 빌드 결과와 Git 이력은 소스 ZIP에 포함하지 않습니다.

```bash
python scripts/export_public_source.py
python scripts/export_dependency_sources.py
```

첫 명령은 `dist/YTMusicDownloader-source.zip`, 두 번째는 미리 확보한 Qt/FFmpeg 소스를
검증한 `dist/YTMusicDownloader-dependency-sources.zip`을 생성합니다. 대응 소스 준비 방법과
남은 배포 검토 범위는 [배포 안내](docs/DISTRIBUTION.md)에 기록되어 있습니다.

Windows 빌드 직후에는 다음 오프라인 패키지 검증을 실행합니다.

```powershell
python scripts/verify_onefile.py dist/YTMusicDownloader.exe --output build/onefile-verification
```

검증 스크립트는 별도의 깨끗한 디렉터리에 EXE만 복사한 뒤, 복사한 실행 파일을
`--verify-package report.json`으로 실행합니다. GUI, 워커, 미디어 헬퍼, FFmpeg와 정상 종료를
확인하며 네트워크를 사용하지 않습니다. 검증 출력은 `build/onefile-verification`에 저장합니다.
macOS / Linux는 기존 콘솔 워커 시작 확인을 유지합니다. 이 검증은 실제 다운로드나
사용자 GUI 상호작용 전체를 검증하는 테스트는 아닙니다.

## 현재 제한

- macOS 실기기에서 로컬 실행과 패키징을 테스트하지 않았습니다. CI 빌드 성공과 실제 GUI,
  브라우저 쿠키 접근, 파일 선택, 다운로드 동작 검증은 별개입니다.
- Windows 단일 EXE를 빈 폴더에 단독 복사하여 GUI 시작, 작업 엔진 통신, 내장 FFmpeg의
  MP3 변환, 정상 종료와 임시 추출 폴더 정리를 로컬에서 확인했습니다.
  macOS와 Linux용 CI 설정은 포함되어 있으나 이 환경에서 실행하지 않았습니다.
- 배포본은 서명/공증을 제공하지 않으므로 Windows 또는 macOS 보안 경고가 나타날 수 있습니다.
- Linux의 glibc, 그래픽 시스템 라이브러리와 CPU 아키텍처 호환성이 필요합니다.
  모든 Linux 배포판이나 모든 macOS/Windows 버전에서의 실행을 보장하지 않습니다.
- 재생목록 및 작업 상태는 실행 중인 프로세스에 보관합니다. 앱을 재시작한 뒤 작업 이력을
  복원하거나 다운로드를 자동으로 이어받는 기능은 제공하지 않습니다.
- YouTube 변경, 지역/계정 제한, 쿠키 접근 실패로 다운로드가 실패할 수 있습니다.
  별도 JavaScript 런타임이나 추가 인증이 필요한 콘텐츠까지 자동으로 해결하지는 않습니다.

## 개발 및 테스트

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider
```

macOS / Linux에서는 Python 경로를 `.venv/bin/python`으로 바꾸세요. 자동 테스트는 가짜
다운로더를 사용하며 YouTube Music에서 실제 파일을 다운로드하지 않습니다.
