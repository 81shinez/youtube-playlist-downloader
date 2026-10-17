# YouTube Music Downloader

YouTube / YouTube Music 재생목록을 MP3로 저장하는 데스크톱 앱입니다.
재생목록 다운로드, 곡별 진행 상태, 실패 항목 재시도, 일시 정지와 취소를 지원합니다.

**Windows에서는 빌드된 `YTMusicDownloader.exe` 파일 하나로 실행합니다.**
앱 실행에는 Python, 가상환경, 별도 FFmpeg나 웹 서버가 필요하지 않습니다.
macOS는 `.app` 번들, Linux는 실행 파일과 라이브러리가 포함된 폴더를 사용합니다.

## 앱 실행

### Windows

1. `YTMusicDownloader.exe`를 원하는 폴더에 둡니다.
2. 파일을 더블클릭하여 앱을 엽니다.
3. 사용을 마치면 앱 창을 닫습니다.

**필요한 파일은 EXE 하나뿐입니다.** 설치 명령이나 터미널을 사용할 필요가 없습니다.
실행에 필요한 구성 요소가 EXE에 포함되어 있으며, 실행 시 임시 폴더에 자동으로 풀립니다.
처음 열 때는 잠시 시간이 걸릴 수 있습니다.

### macOS

`YTMusicDownloader.app`을 열어 실행하고 앱을 종료하여 닫습니다.
`.app`은 하나의 앱으로 취급되는 번들이므로 내부 파일을 꺼내지 말고 전체를 유지하세요.

### Linux

현재 Linux 패키지는 단일 파일이 아닌 폴더형입니다.
`YTMusicDownloader` 폴더 안의 실행 파일을 열며, 포함된 라이브러리와 폴더 구조를 유지해야 합니다.

## 실행 파일 제공 상태

**현재 GitHub에는 다운로드할 수 있는 공개 실행 파일이 없습니다.**
Windows 단일 EXE는 로컬 검증본이 있지만, 포함 라이브러리의 재배포 검토가 남아 있어
GitHub Releases에는 올리지 않았습니다. 자세한 상태는 [배포 문서](docs/DISTRIBUTION.md)에 있습니다.
GitHub의 `Code > Download ZIP`은 앱이 아닌 소스 코드이며, 위 실행 파일을 포함하지 않습니다.

## 직접 빌드하기

공개 실행 파일이 아직 없으므로, 필요하면 아래 절차로 로컬용 앱을 만들 수 있습니다.
**Python은 빌드할 때만 필요합니다. 완성된 앱은 위의 실행 방법대로 독립 실행합니다.**

Python 3.12와 인터넷 연결을 준비하고, `Code > Download ZIP`으로 소스를 받아 압축을 풉니다.
터미널에서 `pyproject.toml`이 있는 폴더로 이동한 뒤 해당 OS의 명령을 실행하세요.
Windows용은 Windows에서, macOS용은 macOS에서, Linux용은 Linux에서 빌드합니다.

<details>
<summary>Windows (PowerShell)</summary>

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\python scripts/prepare_ffmpeg.py --download
.\.venv\Scripts\python scripts/build_desktop.py
```

결과: `dist/YTMusicDownloader.exe`. 이 파일 하나를 더블클릭하면 됩니다.

</details>

<details>
<summary>macOS / Linux (터미널)</summary>

Linux는 그래픽 세션과 Qt 시스템 라이브러리가 필요합니다.
Ubuntu 22.04에서는 먼저 다음 패키지를 설치하세요. macOS에는 이 단계가 필요하지 않습니다.

```bash
sudo apt-get update
sudo apt-get install libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0
```

앱 빌드:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[build]"
.venv/bin/python scripts/prepare_ffmpeg.py --download
.venv/bin/python scripts/build_desktop.py
```

macOS 결과: `dist/YTMusicDownloader.app`을 엽니다.
Linux 결과: `dist/YTMusicDownloader/` 폴더 전체를 유지하고 내부 실행 파일을 엽니다.

</details>

추가 옵션과 패키징 내부 설명은 [개발자용 빌드 문서](docs/development/BUILDING.md)에 있습니다.
이 절차는 로컬용 빌드이며, 실행 파일의 공개 재배포 검토가 완료되었다는 뜻은 아닙니다.

## 앱 사용하기

1. YouTube 또는 YouTube Music 재생목록 URL을 붙여 넣습니다.
2. MP3를 저장할 폴더를 선택합니다.
3. 출력 모드, 동시 작업 수(1~4), 필요하면 브라우저 쿠키를 선택합니다.
4. 다운로드를 시작하고 목록에서 곡별 진행 상태를 확인합니다.
5. 실패한 항목은 해당 곡의 재시도 버튼이나 실패 항목 모두 재시도 버튼으로 다시 처리합니다.

## 출력 음질

| 모드 | 저장 방식 |
| --- | --- |
| MP3 192kbps | 192kbps MP3로 저장 |
| MP3 maximum | 추정 원본 오디오 비트레이트에 맞추되 최대 320kbps로 제한 |

최대 모드에서 원본 비트레이트를 알 수 없으면 256kbps를 사용합니다.
MP3 변환은 재인코딩이므로 원본을 무손실 보존하는 방식은 아닙니다.
비트레이트를 높인다고 원본에 없던 음질이 복원되지는 않습니다.

## 작업 제어

- 일시 정지는 대기 중인 곡의 새 실행을 멈춥니다. 이미 분석·다운로드·변환 중인 작업은 계속될 수 있습니다.
- 재개하면 대기 중인 곡 처리를 이어갑니다.
- 작업 취소는 이미 저장된 완료 파일을 삭제하지 않습니다.
- 작업 이력은 메모리에만 보관합니다. 앱을 종료하고 다시 열면 이전 작업을 복원하지 않습니다.

## 로그인 오류와 쿠키

YouTube가 로그인 또는 봇 확인을 요구하면, 본인이 YouTube에 로그인한 브라우저를 선택하세요.
Chrome, Edge, Firefox, Brave 쿠키를 사용할 수 있습니다.

브라우저 프로필 잠금, 운영체제 암호화 또는 접근 권한 때문에 쿠키를 읽지 못할 수 있습니다.
쿠키를 사용해도 모든 인증 문제가 해결되지는 않습니다. 쿠키 파일이나 계정 정보는 저장소,
배포 파일, 오류 제보에 포함하지 마세요. 자세한 내용은 [보안 안내](SECURITY.md)에 있습니다.

## 지원 범위

- Windows 단일 EXE의 독립 실행과 내장 FFmpeg 변환은 로컬에서 검증했습니다.
- macOS와 Linux용 빌드 설정은 제공하지만, 실제 기기에서의 GUI 사용과 다운로드 검증은 별도입니다.
- 실행 파일의 서명·공증은 제공하지 않습니다. 운영체제에 따라 보안 경고가 나타날 수 있습니다.
- YouTube 변경, 지역·계정 제한, 추가 인증이나 JavaScript 런타임 요구로 다운로드가 실패할 수 있습니다.

## 개발자 문서

소스 받기, 개발 환경 준비, 코드 구조, 패키징과 테스트는 [개발자 문서 세트](docs/development/README.md)에 있습니다.
이 절차는 앱을 만드는 개발자를 위한 것이며, 패키징된 앱을 사용하는 사람에게는 필요하지 않습니다.

## 라이선스

프로젝트 자체 소스는 [MIT 라이선스](LICENSE)입니다.
포함 라이브러리의 조건은 [서드파티 고지](THIRD_PARTY_NOTICES.md)를 참고하세요.

이 앱은 YouTube/Google의 공식 제품이 아닙니다.
다운로드하거나 보관할 권한이 있는 콘텐츠에만 사용하고
[YouTube 이용약관](https://www.youtube.com/static?template=terms)을 준수하세요.
소스 라이선스가 콘텐츠 다운로드 권한을 부여하지는 않습니다.
