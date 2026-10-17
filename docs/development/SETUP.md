# 개발 환경

[개발자 문서 목록](README.md)

앱 소스를 수정하고 테스트·패키징하는 개발자를 위한 환경 설정입니다.
일반 사용자는 이 과정을 거치지 않고 패키징된 앱을 실행합니다.
Python 3.12 이상이 필요하며, 아래 예시는 Python 3.12 기준입니다.

## 소스 받기

```bash
git clone https://github.com/81shinez/youtube-playlist-downloader.git
cd youtube-playlist-downloader
```

Git 없이 받으려면 저장소의 `Code > Download ZIP`을 선택하고 압축을 풉니다.
이후 명령은 `pyproject.toml`이 있는 프로젝트 폴더에서 실행합니다.

## Windows

PowerShell에서 실행합니다. 가상환경 활성화 없이도 아래 경로로 Python을 호출할 수 있습니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

앱을 확인할 때는 [빌드 절차](BUILDING.md)로 만든 `dist/YTMusicDownloader.exe`를 실행하고
[독립 실행 검증](TESTING.md)을 수행합니다.

## macOS / Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
```

앱 실행은 [빌드 절차](BUILDING.md)에서 만든 플랫폼별 패키지를 기준으로 확인합니다.
Linux의 GUI에는 그래픽 데스크톱 세션과 Qt 시스템 라이브러리가 필요합니다.
Ubuntu 22.04 기준 패키지는 다음과 같습니다.

```bash
sudo apt-get install libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0
```

## 의존성

의존성의 기준은 [pyproject.toml](../../pyproject.toml)입니다.
`pip install -e`는 소스 수정 사항을 설치된 패키지에 반영하는 개발용 설치입니다.

| 의존성 | 역할 |
| --- | --- |
| PySide6-Essentials | QtCore, QtGui, QtWidgets 기반 GUI |
| yt-dlp | 재생목록 분석, 오디오 메타데이터 조회와 다운로드 |
| imageio-ffmpeg | 소스 실행 환경의 FFmpeg 제공 |
| FastAPI, Uvicorn | 기존 웹 모드 |
| `.[dev]` | pytest, pytest-asyncio, httpx |
| `.[build]` | PyInstaller |

QtWebEngine이나 전체 `PySide6` 패키지는 필요하지 않습니다.
소스 실행은 `imageio-ffmpeg` 또는 `PATH`의 FFmpeg를 사용하지만,
독립 실행 파일은 별도로 준비한 오디오 전용 FFmpeg를 포함합니다.
소스 실행 성공만으로 패키징 성공을 판단하지 마세요.

다음 단계: [테스트](TESTING.md), [독립 실행 파일 빌드](BUILDING.md).
