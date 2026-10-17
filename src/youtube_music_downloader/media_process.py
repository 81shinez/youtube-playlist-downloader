"""One-request JSON-lines media helper, also used by the frozen console worker."""

import asyncio
import json
import sys
import traceback
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from youtube_music_downloader.media import ProgressCallback, YtDlpDownloader
from youtube_music_downloader.models import MediaTrack


class _ChildDownloader(YtDlpDownloader):
    @classmethod
    def download_options(
        cls, output_dir: Path, progress: ProgressCallback, cookie_source: str | None = None
    ) -> dict[str, Any]:
        return {
            **super().download_options(output_dir, progress, cookie_source),
            "fixup": "never",
            "external_downloader": {"default": "native"},
        }


async def _dispatch(request: dict[str, Any], emit: Callable[[dict[str, Any]], None]) -> Any:
    downloader = _ChildDownloader()
    operation = request.get("operation")
    cookie_source = request.get("cookie_source")
    if operation == "playlist_tracks":
        tracks = await downloader.playlist_tracks(request["playlist_url"], cookie_source)
        return [asdict(track) for track in tracks]
    if operation == "source_bitrate":
        return await downloader.source_bitrate(request["source_url"], cookie_source)
    if operation == "download_audio":
        output = await downloader.download_audio(
            MediaTrack(**request["track"]),
            Path(request["work_dir"]),
            lambda value: emit({"type": "progress", "value": int(value)}),
            cookie_source,
        )
        return str(output)
    raise ValueError(f"Unknown media operation: {operation}")


def main() -> int:
    """Process one stdin request; return an exit code for the caller's entrypoint."""
    protocol_stdout = sys.stdout

    def emit(event: dict[str, Any]) -> None:
        print(json.dumps(event, ensure_ascii=True), file=protocol_stdout, flush=True)

    try:
        with redirect_stdout(sys.stderr):
            request = json.load(sys.stdin)
            if not isinstance(request, dict):
                raise ValueError("Media request must be a JSON object")
            result = asyncio.run(_dispatch(request, emit))
        emit({"type": "result", "value": result})
        return 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        emit({"type": "error", "value": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
