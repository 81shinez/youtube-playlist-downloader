# 테스트와 검증

[개발자 문서 목록](README.md)

명령은 저장소 루트에서 실행합니다. 먼저 [개발 환경](SETUP.md)을 준비하세요.

## 자동 테스트

Windows:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q -p no:cacheprovider
```

macOS / Linux:

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q -p no:cacheprovider
```

자동 테스트는 가짜 다운로더 등을 사용하며 실제 YouTube 음원을 다운로드하지 않습니다.
화면이 없는 CI에서는 `QT_QPA_PLATFORM=offscreen`으로 Qt 위젯 테스트를 실행합니다.
웹 UI의 일부 JavaScript 검증은 Node.js를 사용하며, 없는 환경에서는 건너뜁니다.

| 변경 영역 | 우선 확인할 테스트 |
| --- | --- |
| 작업 처리 | `test_job_manager.py`, `test_desktop_service.py` |
| GUI와 프로세스 | `test_desktop_ui.py`, `test_desktop_runtime.py`, `test_desktop_media.py` |
| 미디어와 출력 규칙 | `test_media.py`, `test_bitrate.py`, `test_filenames.py` |
| 웹 모드 | `test_api.py`, `test_web_security.py`, `test_static_assets.py` |
| 공개와 패키징 | `test_release_checks.py`, `test_source_export.py`, `test_legal_resources.py`, 의존성 자료 테스트 |

테스트 파일은 [tests/](../../tests)에 있습니다.
공통 상태 전이, IPC, 패키징을 수정했다면 일부 테스트만으로 끝내지 말고 전체를 실행합니다.

## Windows EXE 검증

[빌드](BUILDING.md) 후 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python scripts/verify_onefile.py dist/YTMusicDownloader.exe --output build/onefile-verification
```

별도의 깨끗한 폴더에 EXE만 복사하고 독립 실행을 확인합니다.
GUI 시작, 워커 IPC, 미디어 헬퍼, 내장 FFmpeg의 MP3 변환과 정상 종료를 검사합니다.
네트워크를 사용하지 않으며 결과는 지정한 출력 폴더에 저장합니다.
75초를 넘기면 하위 프로세스를 종료합니다.

이 검증은 모든 GUI 상호작용이나 실제 YouTube 다운로드를 검증하지는 않습니다.
수동 검증에서는 권한이 있는 콘텐츠로 시작, 재시도, 일시 정지·재개, 취소,
앱 종료를 확인하고 사용한 OS와 빌드 버전을 기록하세요.

## CI

[desktop-build.yml](../../.github/workflows/desktop-build.yml)은 Python 3.12와
`windows-latest`, `macos-14`, `ubuntu-22.04` 조합으로 테스트와 네이티브 빌드를 수행합니다.

- 모든 플랫폼: 오프라인 테스트, 공개 소스 검사, 로컬용 패키지 빌드.
- Windows: 위 단일 EXE 검증.
- macOS / Linux: 패키지의 `ytm-worker --help` 실행 확인.
- 공개 아티팩트 업로드, GitHub Release 게시, 서명·공증은 수행하지 않음.

macOS / Linux의 `--help` 확인은 워커 IPC, FFmpeg 변환이나 실제 GUI 사용을 검증하지 않습니다.
CI 성공을 해당 플랫폼의 전체 사용 검증으로 해석하지 마세요.

## 소스 공개 전 검사

```powershell
.\.venv\Scripts\python scripts/release_check.py
.\.venv\Scripts\python scripts/export_public_source.py
```

macOS / Linux에서는 Python 경로를 `.venv/bin/python`으로 바꿉니다.
검사와 소스 ZIP 생성은 Git 이력을 변경하거나 GitHub에 업로드하지 않습니다.
패턴 검사에는 한계가 있으므로 공개할 파일과 변경 내용을 직접 검토하세요.
대응 소스 ZIP과 바이너리 공개 제한은 [배포 문서](../DISTRIBUTION.md)를 참고하세요.
