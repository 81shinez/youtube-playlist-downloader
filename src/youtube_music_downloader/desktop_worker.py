import asyncio
import json
import os
import sys
import threading

from youtube_music_downloader.desktop_service import DesktopService
from youtube_music_downloader.job_manager import JobManager


async def serve(emit):
    from youtube_music_downloader.desktop_media import DesktopDownloader, DesktopEncoder

    service = DesktopService(JobManager(DesktopDownloader(), DesktopEncoder()))
    commands = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def read_commands():
        buffer = b''
        try:
            while data := os.read(0, 65536):
                buffer += data
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    loop.call_soon_threadsafe(commands.put_nowait, line)
        except (OSError, RuntimeError):
            pass
        finally:
            try:
                loop.call_soon_threadsafe(commands.put_nowait, b'{"action":"shutdown"}')
            except RuntimeError:
                pass

    threading.Thread(target=read_commands, daemon=True, name='desktop-input').start()

    async def publish():
        previous = None
        while True:
            snapshot = service.snapshot()
            if snapshot != previous:
                emit({'type': 'snapshot', 'job': snapshot})
                previous = snapshot
            await asyncio.sleep(0.25)

    publisher = asyncio.create_task(publish())
    emit({'type': 'ready'})
    try:
        while True:
            line = await commands.get()
            command = {}
            try:
                command = json.loads(line)
                if command.get('action') == 'shutdown':
                    break
                job = await service.dispatch(command)
                emit({'type': 'ack', 'request_id': command.get('request_id'), 'job': job})
            except Exception as exc:
                emit({'type': 'error', 'request_id': command.get('request_id'), 'message': str(exc)})
    finally:
        publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)
        await service.shutdown()


def main():
    output = sys.stdout
    sys.stdout = sys.stderr

    def emit(event):
        output.write(json.dumps(event, ensure_ascii=True) + '\n')
        output.flush()

    asyncio.run(serve(emit))


if __name__ == '__main__':
    main()
