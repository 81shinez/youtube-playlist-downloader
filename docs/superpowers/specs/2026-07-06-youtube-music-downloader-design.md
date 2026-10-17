# YouTube Music Downloader Local Web UI Design

> 과거 설계 기록: 웹 앱으로 시작하던 시점의 문서이며 현재 데스크톱 앱의 개발 지침이 아닙니다.
> 현재 구조와 개발 절차는 [개발자 문서](../../development/README.md)를 참고하세요.

## Goal

Build a local web utility that accepts a YouTube Music playlist URL and saves each authorized track as an MP3 file. The app should prioritize the best available source audio, then encode to MP3 using either a fixed 192kbps setting or a source-aware maximum setting capped at 320kbps.

The app is for playlists and tracks the user has permission to download or archive. It must not implement DRM bypassing, paywall bypassing, account takeover flows, or any behavior that hides copyright or access restrictions.

## Product Shape

The first release is a local web app:

- A FastAPI backend runs on localhost.
- A static browser UI is served by the backend.
- The user enters a playlist URL, an output folder, and an MP3 output mode.
- The backend creates a job, analyzes the playlist, downloads each track with `yt-dlp`, and converts the result with `ffmpeg`.
- The UI polls job status and shows per-track progress, failure details, retry actions, and cancel/remove actions.

The app starts as a single-machine tool. It does not require user accounts, remote storage, cloud sync, or persistent job history in the first release.

## UI

The primary screen is a dense utility dashboard, not a marketing page.

Inputs:

- Playlist URL.
- Output folder path.
- Output mode:
  - MP3 192kbps.
  - MP3 maximum.
- Concurrent download count, defaulting to 2.

Actions:

- Start job.
- Open output folder.
- Retry a single failed or completed track.
- Retry all failed tracks in the current job.
- Cancel an active track.
- Remove a queued track.

The job table shows:

- Track title and artist when available.
- Status.
- Progress bar.
- Output mode.
- Row-level action button.
- Error message for failed items.

The UI must describe MP3 encoding honestly: converting to MP3 improves compatibility, but it does not improve the quality beyond the downloaded source audio.

## Output Rules

All completed files are MP3 files.

`MP3 192kbps`:

- Always encode with MP3 bitrate `192k`.

`MP3 maximum`:

- Read the best available source audio bitrate from `yt-dlp` metadata when available.
- Select the MP3 bitrate as `min(source_bitrate_kbps, 320)`.
- If the source bitrate is lower than 192kbps, preserve that lower bitrate rather than upscaling to 192kbps.
- If source bitrate metadata is missing, use `256kbps`.
- Encode with a constant MP3 bitrate matching the selected value, such as `192k`, `256k`, or `320k`.

Examples:

- Source 192kbps -> MP3 192kbps.
- Source 256kbps -> MP3 256kbps.
- Source 384kbps -> MP3 320kbps.
- Unknown source bitrate -> MP3 256kbps.

## Backend Architecture

FastAPI owns the HTTP API and serves static frontend assets.

Core backend units:

- API routes: request validation and response serialization.
- Job manager: in-memory registry of jobs and tracks.
- Worker queue: background execution for playlist analysis and track processing.
- Downloader: `yt-dlp` integration for metadata and audio retrieval.
- Encoder: `ffmpeg` integration for MP3 output.
- Filename policy: safe output filenames and collision handling.
- Bitrate policy: maps source metadata and selected output mode to MP3 bitrate.

The first version stores jobs in memory. Restarting the server clears job state, but previously written MP3 files remain in the output folder.

## API

`POST /api/jobs`

Creates a new job.

Request body:

```json
{
  "playlist_url": "https://music.youtube.com/playlist?list=...",
  "output_dir": "C:/Music/YouTube",
  "output_mode": "max",
  "concurrency": 2
}
```

`output_mode` is either `192` or `max`.

Response body:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

`GET /api/jobs/{job_id}`

Returns the current job, summary counts, and all tracks.

`POST /api/jobs/{job_id}/tracks/{track_id}/retry`

Retries one failed or completed track with the same job settings.

`POST /api/jobs/{job_id}/retry-failed`

Retries every failed track in the job.

`POST /api/jobs/{job_id}/tracks/{track_id}/cancel`

Cancels a queued, downloading, or converting track when possible. For queued tracks, this is the "remove from queue" action shown in the UI.

`POST /api/jobs/{job_id}/open-output-folder`

Opens the job output folder in the host operating system file explorer. This endpoint is local-only and only opens the output directory already stored on the job.

## State Model

Job status:

- `queued`
- `analyzing`
- `running`
- `completed`
- `completed_with_errors`
- `failed`
- `canceled`

Track status:

- `queued`
- `analyzing`
- `downloading`
- `converting`
- `completed`
- `failed`
- `canceled`

Track fields:

- `id`
- `title`
- `artist`
- `source_url`
- `source_bitrate_kbps`
- `target_bitrate_kbps`
- `status`
- `progress`
- `output_path`
- `error_message`
- `attempts`

Progress should be best-effort. Download progress comes from `yt-dlp` progress hooks. Conversion progress may be coarse in the first release and can show an indeterminate or phase-level state if reliable percentage data is unavailable.

## Error Handling

Playlist-level failures fail the job before tracks are queued.

Track-level failures mark only that track as `failed`; the rest of the job continues. The UI shows the failure message and leaves retry buttons available.

Retrying a completed track creates a new MP3 output using the filename collision policy rather than silently overwriting the existing file.

Common errors must produce readable messages:

- Missing or invalid playlist URL.
- Output folder does not exist or is not writable.
- `yt-dlp` is missing.
- `ffmpeg` is missing.
- Download failed.
- MP3 conversion failed.
- File write conflict or permission error.

Filename collisions are handled by appending a numeric suffix, for example `Song.mp3`, `Song (2).mp3`, `Song (3).mp3`.

## Testing Strategy

The implementation should be test-driven.

Unit tests:

- Bitrate selection for 192, max, unknown bitrate, low bitrate, and above-320 bitrate cases.
- Filename sanitization and collision suffixing.
- Job and track state transitions.
- Retry-one behavior.
- Retry-all-failed behavior.
- Request validation.

Integration-style tests with fakes:

- API creates a job and returns status.
- Job manager runs a fake playlist with one successful track and one failed track.
- Failed track retry returns it to the queue.

Real network downloads are not required in automated tests. `yt-dlp` and `ffmpeg` should be wrapped behind interfaces so tests can use fakes.

## Out Of Scope For First Release

- Persistent database-backed job history.
- Multi-user access.
- Cloud storage.
- Browser cookie import UI.
- DRM or paywall bypassing.
- Album art embedding unless it falls out naturally from `yt-dlp` metadata and does not complicate the first implementation.
- Electron packaging.
