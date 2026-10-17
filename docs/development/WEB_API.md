# 웹 모드와 API

[개발자 문서 목록](README.md)

기존 로컬 웹 UI를 유지하는 호환 모드입니다.
기본 데스크톱 앱이나 단일 EXE 실행에 웹 서버는 필요하지 않습니다.

## 실행

[개발 환경](SETUP.md)을 준비한 뒤 저장소 루트에서 실행합니다.

Windows:

```powershell
.\.venv\Scripts\python -m youtube_music_downloader.main --web
```

macOS / Linux:

```bash
.venv/bin/python -m youtube_music_downloader.main --web
```

[로컬 웹 UI](http://127.0.0.1:8000)를 열고, 종료할 때는 서버를 실행한 터미널에서
`Ctrl+C`를 누릅니다. Windows에서는 로그 확인을 위해 GUI 런처 대신 위 명령을 사용하세요.

## 보안 경계

웹 모드는 루프백 전용입니다. 포트 포워딩, 공개 터널, 프록시로 외부에 노출하지 마세요.
서버는 Host/Origin과 실행마다 생성되는 토큰을 검사합니다.
웹 UI는 필요한 헤더를 자동으로 설정하지만, 직접 호출하는 클라이언트는 다음 규약을 따라야 합니다.

1. `GET /session-token`에 `X-YMD-Bootstrap: 1`과 서버 주소와 일치하는
   `Origin`을 전달합니다. 예: `Origin: http://127.0.0.1:8000`.
2. 응답의 `token`을 모든 `/api` 요청의 `X-YMD-Token` 헤더에 넣습니다.
3. API 요청에도 같은 Origin을 보내고, POST 요청은 `Content-Type: application/json`을 사용합니다.
   추가 값이 없는 명령은 `{}`를 보낼 수 있습니다.

토큰을 URL, 로그나 저장소에 기록하지 마세요. 서버를 재시작하면 토큰이 바뀝니다.
네트워크 공유(UNC)와 장치 경로는 출력 폴더로 허용하지 않습니다.
자세한 제한은 [SECURITY.md](../../SECURITY.md)와 [api.py](../../src/youtube_music_downloader/api.py)를 참고하세요.

## 작업 생성

`POST /api/jobs`의 JSON 본문:

| 필드 | 값 |
| --- | --- |
| `playlist_url` | YouTube / YouTube Music의 재생목록 URL |
| `output_dir` | 로컬 저장 폴더 |
| `output_mode` | `192` 또는 `max` |
| `concurrency` | 정수 1~4 |
| `cookie_source` | 선택 사항. `auto`, `chrome`, `edge`, `firefox`, `brave` 또는 `null` |

생성 응답의 `job_id`로 상태를 조회합니다. 생성 성공은 다운로드 완료를 뜻하지 않습니다.

## 엔드포인트

| 메서드와 경로 | 동작 |
| --- | --- |
| `GET /api/jobs/latest` | 마지막 작업 조회. 작업이 없으면 404 |
| `GET /api/jobs/{job_id}` | 작업 상태, 요약, 곡 목록 조회 |
| `POST /api/jobs/{job_id}/tracks/{track_id}/retry` | 곡 하나 재시도 |
| `POST /api/jobs/{job_id}/retry-failed` | 실패한 곡 일괄 재시도 |
| `POST /api/jobs/{job_id}/pause` | 대기 중인 곡의 새 실행 중단 |
| `POST /api/jobs/{job_id}/resume` | 일시 정지한 작업 재개 |
| `POST /api/jobs/{job_id}/cancel` | 작업 전체 취소 |
| `POST /api/jobs/{job_id}/tracks/{track_id}/cancel` | 곡 하나 취소 |
| `POST /api/jobs/{job_id}/cookie-source` | 쿠키 설정 갱신 및 조건에 따라 실패 작업 재시도 |
| `POST /api/jobs/{job_id}/open-output-folder` | Windows에서 저장 폴더 열기. 다른 OS는 501 |

재시도 요청에는 선택적으로 `cookie_source`를 전달할 수 있습니다.
쿠키 갱신 요청에는 해당 필드가 필수입니다.
이 API와 데스크톱 IPC는 별개이며, API 변경 시 웹 UI와 보안 테스트를 함께 확인하세요.
