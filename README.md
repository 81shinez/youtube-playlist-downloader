# YouTube Music Downloader

YouTube / YouTube Music 재생목록을 MP3로 저장하는 데스크톱 앱입니다.
재생목록 다운로드, 곡별 진행 상태, 실패 항목 재시도, 일시 정지와 취소를 지원합니다.

**Windows에서는 빌드된 `YTMusicDownloader.exe` 파일 하나로 실행합니다.**
앱 실행에는 Python, 가상환경, 별도 FFmpeg나 웹 서버가 필요하지 않습니다.
macOS는 `.app` 번들, Linux는 실행 파일과 라이브러리가 포함된 폴더를 사용합니다.

## 시작하기

현재 이 저장소는 **소스 코드만 제공**하며, GitHub Releases에 실행 파일은 없습니다.
아래 절차로 소스를 받아 로컬에서 실행 파일을 만들 수 있습니다.
Python은 이 빌드 과정에만 필요하며, 만들어진 앱을 실행할 때는 필요하지 않습니다.

포함 라이브러리의 재배포 검토가 끝나지 않아 공개 바이너리 배포는 아직 지원하지 않습니다.
자세한 검토 상태는 [배포 문서](docs/DISTRIBUTION.md)를 참고하세요.
GitHub의 `Code > Download ZIP`도 실행 파일이 아니라 소스 코드입니다.

### 1. 소스 받기

Git을 사용하는 경우 다음 명령을 실행합니다.

```bash
git clone https://github.com/81shinez/youtube-playlist-downloader.git
cd youtube-playlist-downloader
```

Git 없이 받으려면 저장소의 `Code > Download ZIP`을 선택하고 압축을 푸세요.
이후 명령은 `pyproject.toml`이 있는 프로젝트 폴더에서 실행합니다.

### 2. 실행 파일 만들기

Python 3.12 이상과 인터넷 연결이 필요합니다. 아래 예시는 Python 3.12 기준입니다.
Windows 앱은 Windows에서, macOS 앱은 macOS에서 빌드해야 합니다.

**Windows (PowerShell)**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\python scripts/prepare_ffmpeg.py --download
.\.venv\Scripts\python scripts/build_desktop.py
```

빌드가 끝나면 `dist\YTMusicDownloader.exe`를 더블클릭하세요.
다른 폴더로 옮길 때도 **이 EXE 하나만** 있으면 됩니다.

**macOS / Linux**

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[build]"
.venv/bin/python scripts/prepare_ffmpeg.py --download
.venv/bin/python scripts/build_desktop.py
```

macOS에서는 `dist/YTMusicDownloader.app`을 엽니다.
Linux에서는 `dist/YTMusicDownloader/` 폴더에서 `./YTMusicDownloader`를 실행합니다.
`.app`이나 Linux 출력 폴더는 내부 파일을 빼지 말고 전체를 유지하세요.
Linux의 그래픽 라이브러리 요구 사항과 추가 옵션은 [빌드 문서](docs/development/BUILDING.md)에 있습니다.

### 3. 앱 사용하기

1. YouTube 또는 YouTube Music 재생목록 URL을 붙여 넣습니다.
2. MP3를 저장할 폴더를 선택합니다.
3. 출력 모드, 동시 작업 수(1~4), 필요하면 브라우저 쿠키를 선택합니다.
4. 다운로드를 시작하고 목록에서 곡별 진행 상태를 확인합니다.
5. 실패한 항목은 해당 곡의 재시도 버튼이나 실패 항목 모두 재시도 버튼으로 다시 처리합니다.

사용을 마치면 앱 창을 닫습니다. Windows EXE는 실행 시 내장 구성 요소를 임시 폴더에
풀기 때문에 시작에 잠시 시간이 걸릴 수 있습니다.

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

소스를 수정하거나 테스트하려면 [개발자 문서 세트](docs/development/README.md)를 참고하세요.
개발 환경, 코드 구조, 패키징, 테스트, 기존 웹 모드와 HTTP API를 별도로 정리했습니다.

## 라이선스

프로젝트 자체 소스는 [MIT 라이선스](LICENSE)입니다.
포함 라이브러리의 조건은 [서드파티 고지](THIRD_PARTY_NOTICES.md)를 참고하세요.

이 앱은 YouTube/Google의 공식 제품이 아닙니다.
다운로드하거나 보관할 권한이 있는 콘텐츠에만 사용하고
[YouTube 이용약관](https://www.youtube.com/static?template=terms)을 준수하세요.
소스 라이선스가 콘텐츠 다운로드 권한을 부여하지는 않습니다.
