"""Console entry point for piped worker IPC; deliberately does not import Qt."""

import sys


def main() -> int | None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"--desktop-worker", "--media-process"}:
        print("Usage: ytm-worker (--desktop-worker | --media-process) [arguments]", file=sys.stderr)
        return 0 if sys.argv[1:] in (["--help"], ["-h"]) else 2

    route = sys.argv.pop(1)
    if route == "--desktop-worker":
        from youtube_music_downloader.desktop_worker import main as run_worker
    else:
        from youtube_music_downloader.media_process import main as run_worker

    return run_worker()


if __name__ == "__main__":
    raise SystemExit(main())
