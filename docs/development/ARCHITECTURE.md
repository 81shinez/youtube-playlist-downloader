# 코드 구조

[개발자 문서 목록](README.md)

기본 실행 경로는 네이티브 데스크톱 GUI입니다.
웹 서버는 `--web`을 지정했을 때만 실행되며, 데스크톱 GUI는 HTTP API에 의존하지 않습니다.

## 데스크톱 실행 흐름

```text
main.py
  -> desktop.py / DesktopController        GUI 프로세스
      -> desktop_worker.py                JSON Lines IPC, asyncio 루프
          -> DesktopService / JobManager  명령 처리, 작업 상태, 동시 실행
              -> desktop_media.py
                  -> media_process.py     미디어 하위 프로세스
                      -> yt-dlp / FFmpeg
```

GUI는 `QProcess`로 워커를 시작합니다. 표준 입력으로 명령을 보내고 표준 출력으로
`ready`, `ack`, `error`, `snapshot` 이벤트를 받습니다.
`request_id`는 명령과 응답을 연결하며, 각 JSON 메시지는 줄바꿈으로 구분합니다.
진단 출력은 표준 오류로 보내야 IPC 스트림을 손상시키지 않습니다.

워커는 별도 asyncio 루프에서 명령과 작업을 처리합니다.
상태가 바뀌면 스냅샷을 게시하고, GUI는 이를 받아 화면을 갱신합니다.
작업 상태는 메모리에만 존재하며 앱 재시작 시 복원하지 않습니다.

## 주요 모듈

아래 파일은 모두 [src/youtube_music_downloader](../../src/youtube_music_downloader)에 있습니다.

| 모듈 | 책임 |
| --- | --- |
| `main.py` | 데스크톱, 웹, 내부 워커 실행 경로 선택 |
| `desktop.py` | 위젯, 사용자 입력, 작업 목록 표시 |
| `desktop_controller.py` | 워커 수명 주기, IPC, 응답 대기와 시간 제한 |
| `desktop_worker.py` | IPC 입력 처리와 이벤트 출력 |
| `desktop_service.py` | 데스크톱 명령 검증, 작업 예약과 스냅샷 |
| `job_manager.py` | 재생목록과 곡 상태, 병렬 처리, 재시도·일시 정지·취소 |
| `desktop_media.py`, `media_process.py` | 데스크톱 미디어 작업의 프로세스 분리 |
| `media.py` | yt-dlp와 FFmpeg 연동 |
| `models.py` | 작업·곡 데이터와 상태 |
| `bitrate.py`, `filenames.py` | 출력 비트레이트와 파일 이름 규칙 |
| `desktop_runtime.py` | 소스 실행과 패키지 실행의 워커 경로 구분 |
| `legal_resources.py` | 오프라인 라이선스 리소스 조회 |
| `package_verification.py` | 독립 실행 패키지 자체 검증 |
| `api.py`, `static/` | 기존 로컬 웹 API와 UI |

## 변경 시 주의할 경계

- GUI 이벤트 처리에 네트워크 작업이나 긴 미디어 작업을 추가하지 않습니다.
- IPC 메시지 형식을 바꿀 때 송신부, 수신부, 관련 테스트를 함께 수정합니다.
- `DesktopService`, `JobManager`, 웹 API가 모두 작업 상태를 다룹니다. 상태 전이를 바꾸면
  재시도 중 재시도, 분석 중 취소, 일시 정지 후 재개 등 겹치는 명령도 확인합니다.
- 일시 정지는 대기 작업의 새 실행을 막는 기능입니다. 운영체제 수준의 프로세스 정지와 다릅니다.
- 다운로드와 인코딩은 작은 인터페이스로 주입합니다. 단위 테스트에서는 가짜 구현을 사용합니다.
- 소스 실행과 frozen 패키지는 실행 파일과 리소스 경로가 다릅니다.
  경로 변경은 [패키지 검증](TESTING.md)까지 확인합니다.

## 웹 실행 경로

`--web`은 FastAPI 앱과 별도의 백그라운드 asyncio 루프를 사용합니다.
정적 웹 UI는 HTTP API를 폴링하며, 데스크톱 IPC와는 다른 경로로 `JobManager`를 호출합니다.
공통 작업 동작을 수정할 때는 데스크톱 서비스와 웹 API 테스트를 모두 확인하세요.

웹 모드의 보안 경계와 엔드포인트는 [웹 모드와 API](WEB_API.md)에 있습니다.
