# YouTube Music Downloader

YouTube / YouTube Music 재생목록의 노래를 MP3로 저장하는 데스크톱 앱입니다.
곡별 진행 상태, 실패 항목 재시도, 일시 정지와 취소를 지원합니다.

**현재는 소스 코드만 공개되어 있으며, GitHub Releases에 실행 파일은 없습니다.**
아래 순서로 소스에서 앱을 빌드한 뒤 사용할 수 있습니다.
포함 라이브러리의 재배포 검토가 끝나기 전까지 빌드 결과는 로컬 테스트용입니다.
공개 배포의 남은 검토 사항은 [배포 문서](docs/DISTRIBUTION.md)에 정리되어 있습니다.

## 1. 준비하기

1. 빌드할 컴퓨터에 Python 3.12를 설치하고 인터넷 연결을 준비합니다.
2. 이 저장소의 `Code > Download ZIP`으로 소스를 받아 압축을 풉니다.
3. 터미널을 열고 `pyproject.toml`이 있는 폴더로 이동합니다.

사용할 운영체제에서 빌드해야 합니다. Windows에서 macOS 앱을 만드는 교차 빌드는 지원하지 않습니다.
**Python과 가상환경은 빌드 도구입니다. 완성된 앱을 실행할 때는 별도 Python·FFmpeg 설치나 웹 서버가 필요하지 않습니다.**

## 2. 실행 파일 만들기

자신의 운영체제에 해당하는 명령만 실행하세요.

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\python scripts/prepare_ffmpeg.py --download
.\.venv\Scripts\python scripts/build_desktop.py
```

### macOS / Linux (터미널)

Linux에는 그래픽 세션과 Qt 시스템 라이브러리가 필요합니다.
Ubuntu 22.04에서는 먼저 아래 패키지를 설치하세요. macOS는 이 단계를 건너뜁니다.

```bash
sudo apt-get update
sudo apt-get install libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0
```

이어서 앱을 빌드합니다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e ".[build]"
.venv/bin/python scripts/prepare_ffmpeg.py --download
.venv/bin/python scripts/build_desktop.py
```

빌드가 완료되면 프로젝트의 `dist` 폴더에 다음 결과물이 생성됩니다.

| 운영체제 | 결과물 | 다른 폴더로 옮길 때 |
| --- | --- | --- |
| Windows | `dist/YTMusicDownloader.exe` | **EXE 파일 하나만** |
| macOS | `dist/YTMusicDownloader.app` | 내부 파일을 포함한 `.app` 전체 |
| Linux | `dist/YTMusicDownloader/` | 라이브러리를 포함한 폴더 전체 |

## 3. 사용하기

1. 빌드된 앱을 엽니다. Windows는 EXE를, macOS는 `.app`을 더블클릭합니다.
   Linux는 결과 폴더 안의 `YTMusicDownloader` 실행 파일을 엽니다.
2. YouTube 또는 YouTube Music 재생목록 URL을 붙여 넣습니다.
3. 저장 폴더, 출력 음질, 동시 작업 수(1~4)를 선택합니다.
4. 다운로드를 시작하고 목록에서 곡별 진행 상태를 확인합니다.
5. 사용을 마치면 앱을 종료합니다.

Windows EXE는 실행에 필요한 구성 요소를 임시 폴더에 자동으로 풀기 때문에 처음 열 때 잠시 시간이 걸릴 수 있습니다.

### 출력 음질

| 모드 | MP3 저장 방식 |
| --- | --- |
| MP3 192kbps | 192kbps 고정 |
| MP3 maximum | 추정 원본 오디오 비트레이트에 맞추되 최대 320kbps로 제한 |

최대 모드에서 원본 비트레이트를 알 수 없으면 256kbps를 사용합니다.
MP3 변환은 재인코딩이며 무손실 보존이 아닙니다. 비트레이트를 높여도 원본에 없던 음질이 복원되지는 않습니다.

### 재시도와 작업 제어

- 실패한 곡은 해당 항목의 재시도 버튼이나 실패 항목 모두 재시도 버튼으로 다시 처리합니다.
- 일시 정지는 대기 중인 곡의 새 실행을 멈춥니다. 이미 분석·다운로드·변환 중인 작업은 계속될 수 있으며, 재개하면 대기 곡 처리를 이어갑니다.
- 작업 취소는 이미 저장된 완료 MP3를 삭제하지 않습니다. 앱을 종료하면 작업 이력은 사라지며, 다시 열어 자동으로 이어받는 기능은 없습니다.

## 제한과 문제 해결

- 로그인 또는 봇 확인 오류가 나면 본인이 YouTube에 로그인한 브라우저를 쿠키 설정에서 선택하세요.
  Chrome, Edge, Firefox, Brave를 지원하지만, 프로필 잠금이나 암호화 때문에 읽지 못할 수 있습니다.
- YouTube 변경, 지역·계정 제한, 추가 인증이나 JavaScript 런타임 요구로 다운로드가 실패할 수 있습니다.
  쿠키 선택만으로 모든 오류가 해결되지는 않습니다.
- Windows 단일 EXE의 독립 실행과 내장 FFmpeg 변환은 로컬에서 검증했습니다.
  macOS와 Linux는 빌드 설정을 제공하지만 실제 기기에서의 GUI·다운로드 검증은 별도입니다.
- 실행 파일의 서명·공증은 제공하지 않습니다. 운영체제의 보안 경고가 나타날 수 있습니다.
- 쿠키·계정 정보·개인 경로가 담긴 로그를 공개 저장소나 오류 제보에 올리지 마세요. [보안 안내](SECURITY.md)

## 개발자 문서

코드를 수정하거나 패키징을 변경하려면 [개발자 문서 세트](docs/development/README.md)를 참고하세요.
개발 환경, 코드 구조, 상세 빌드 옵션, 테스트, 기존 웹 API는 README와 분리되어 있습니다.

## 라이선스

프로젝트 자체 소스는 [MIT 라이선스](LICENSE)이며, 의존성에는 각각의 [서드파티 라이선스](THIRD_PARTY_NOTICES.md)가 적용됩니다.

YouTube/Google의 공식 앱이 아닙니다. 다운로드하거나 보관할 권한이 있는 콘텐츠에만 사용하고
[YouTube 이용약관](https://www.youtube.com/static?template=terms)을 준수하세요.
소스 라이선스는 콘텐츠 다운로드 권한을 부여하지 않습니다.
