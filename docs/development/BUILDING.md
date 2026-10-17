# 빌드와 패키징

[개발자 문서 목록](README.md)

빌드는 대상 운영체제와 Python 아키텍처에서 수행합니다.
Windows에서 macOS 앱을 만드는 등의 교차 컴파일은 지원하지 않습니다.
기본 빌드는 로컬 테스트용이며, 공개 배포의 미완료 검토 사항은 [배포 문서](../DISTRIBUTION.md)에 있습니다.

## 빌드 명령

[개발 환경](SETUP.md)의 가상환경을 준비한 뒤 저장소 루트에서 실행합니다.

Windows:

```powershell
.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\python scripts/prepare_ffmpeg.py --download
.\.venv\Scripts\python scripts/build_desktop.py
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -e ".[build]"
.venv/bin/python scripts/prepare_ffmpeg.py --download
.venv/bin/python scripts/build_desktop.py
```

Linux의 그래픽 라이브러리 요구 사항은 [개발 환경](SETUP.md)에 있습니다.
FFmpeg 준비 스크립트는 다운로드별 시간 제한과 SHA-256 검사를 적용합니다.
빌드 스크립트는 의존성을 자동 설치하지 않으며, 빌드가 300초를 초과하면 하위 프로세스를 종료합니다.

| 옵션 | 동작 |
| --- | --- |
| 기본값 | Windows onefile, macOS 앱 번들, Linux 폴더형 출력 |
| `--clean` | PyInstaller 캐시를 정리하고 다시 빌드 |
| `--onedir` | Windows에서 기존 폴더형 출력 사용 |
| `--release` | 현재 바이너리 공개 검토가 완료되지 않아 의도적으로 실패 |

검증했던 Windows 환경의 버전 목록은 [requirements-build-windows.lock](../../requirements-build-windows.lock)에 있습니다.
일반 설치 명령은 `pyproject.toml`의 허용 범위를 사용하므로 그 기록과 같은 버전을 보장하지 않습니다.
해당 환경을 기준으로 설치하는 절차와 한계는 [배포 문서](../DISTRIBUTION.md)에 있습니다.

## 산출물

| 플랫폼 | 결과물 | 워커 |
| --- | --- | --- |
| Windows 기본값 | `dist/YTMusicDownloader.exe` 하나 | EXE 내부에 포함 |
| Windows `--onedir` | `dist/YTMusicDownloader/` 전체 | 폴더의 `ytm-worker.exe` |
| macOS | `dist/YTMusicDownloader.app` 전체 | `Contents/MacOS/ytm-worker` |
| Linux | `dist/YTMusicDownloader/` 전체 | 폴더의 `ytm-worker` |

Windows onefile은 Python 런타임, 워커, FFmpeg를 EXE에 내장합니다.
실행 시 PyInstaller가 `sys._MEIPASS` 임시 폴더에 구성 요소를 추출하므로,
사용자가 별도 파일을 옆에 배치할 필요는 없습니다.

폴더형 출력은 `_internal`을 포함한 전체 폴더가 필요합니다.
macOS는 함께 생성되는 일반 폴더형 출력 대신 전체 `.app`을 사용하세요.
macOS 아카이브는 `ditto`처럼 심볼릭 링크를 보존하는 도구를,
Linux 아카이브는 실행 권한과 심볼릭 링크를 보존하는 `tar`를 사용합니다.

## 패키징 구조

구성의 기준은 [desktop.spec](../../scripts/desktop.spec)입니다.

- [desktop_entry.py](../../scripts/desktop_entry.py)는 앱의 `main()`을 호출합니다.
- [worker_entry.py](../../scripts/worker_entry.py)는 내부 `--desktop-worker`와
  `--media-process` 모드를 해당 모듈로 전달합니다. 라우트 플래그 외의 인자는 유지합니다.
- Windows GUI는 `console=False`, 워커는 `console=True`입니다.
  GUI 실행 파일은 표준 입출력이 없을 수 있으므로 IPC에 별도 콘솔 워커를 사용합니다.
  호출부는 파이프를 연결하고 콘솔 창을 숨깁니다.
- Windows onefile은 워커와 필요한 런타임을 EXE에 포함합니다.
  폴더형 패키징은 두 `Analysis`와 하나의 `COLLECT`를 사용하고 외부 라이브러리 폴더를 공유합니다.
  워커 분석에서는 Qt를 제외합니다.
- `yt_dlp` 데이터와 하위 모듈, 고정된 오디오 전용 FFmpeg/ffprobe를 수집합니다.
  개발 환경의 `imageio-ffmpeg` 바이너리는 패키지에 포함하지 않습니다.
- Qt 라이브러리와 플랫폼 플러그인은 PyInstaller의 PySide6 훅으로 수집합니다.
  Windows 빌드 PATH는 Python과 시스템 폴더로 제한합니다.

## 라이선스 리소스

설치된 의존성에서 찾은 라이선스·고지와 패키지 메타데이터를 함께 수집합니다.
Windows onefile에서는 내장 후 추출하며, 폴더형은 `_internal/licenses`,
macOS는 `Contents/Resources/licenses`에 배치합니다.

앱의 `도움말 > 오픈소스 라이선스`에서 프로젝트·의존성 고지를 오프라인으로 확인할 수 있습니다.
[서드파티 고지](../../THIRD_PARTY_NOTICES.md)와 배포 문서도 함께 포함합니다.
자동 수집 자체가 재배포 검토 완료를 뜻하지는 않습니다.

## 빌드 이후

[테스트와 검증](TESTING.md)에 따라 독립 실행 파일을 확인합니다.
실행에 EXE 하나면 충분하다는 것과 공개 배포에 EXE 하나만 제공하면 된다는 것은 다릅니다.
바이너리 업로드 전에는 [공개와 재배포](../DISTRIBUTION.md)의 검토가 완료되어야 합니다.
