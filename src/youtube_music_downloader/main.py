import sys


def main() -> int | None:
    if '--verify-package' in sys.argv:
        from pathlib import Path
        from youtube_music_downloader.package_verification import verify_package
        return verify_package(Path(sys.argv[sys.argv.index('--verify-package') + 1]))
    elif '--desktop-worker' in sys.argv:
        from youtube_music_downloader.desktop_worker import main as run
    elif '--media-process' in sys.argv:
        from youtube_music_downloader.media_process import main as run
    elif '--web' in sys.argv:
        import uvicorn
        uvicorn.run("youtube_music_downloader.api:create_app", factory=True, host="127.0.0.1", port=8000, reload=False)
        return
    else:
        from youtube_music_downloader.desktop import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
