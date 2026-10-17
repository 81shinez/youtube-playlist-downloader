"""Exercise the pinned FFmpeg offline with bounded AAC/Opus/MP3 conversions."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import wave


def run(command):
    return subprocess.run(command, capture_output=True, check=True, timeout=15).stdout


def verify(ffmpeg: Path) -> dict:
    ffmpeg = ffmpeg.resolve()
    ffprobe = ffmpeg.with_name('ffprobe' + ffmpeg.suffix)
    report = {'version': run([str(ffmpeg), '-version']).decode().splitlines()[0], 'conversions': []}
    with tempfile.TemporaryDirectory(prefix='ymd-codecs-') as temporary:
        root = Path(temporary)
        wav = root / 'source.wav'
        with wave.open(str(wav), 'wb') as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(48000)
            stream.writeframes(b'\0\0\0\0' * 48000)
        sources = [wav]
        for codec, extension in [('aac', 'm4a'), ('opus', 'webm')]:
            path = root / ('source.' + extension)
            # The minimal build has a Matroska muxer; WebM is a restricted subset.
            muxer = ['-f', 'matroska'] if extension == 'webm' else []
            run([str(ffmpeg), '-y', '-i', str(wav), '-c:a', codec, '-strict', '-2', *muxer, str(path)])
            sources.append(path)
        for source in sources:
            for rate in (192, 256, 320):
                output = root / f'{source.suffix[1:]}-{rate}.mp3'
                run([str(ffmpeg), '-y', '-i', str(source), '-vn', '-codec:a', 'libmp3lame', '-b:a', f'{rate}k', str(output)])
                details = json.loads(run([str(ffprobe), '-v', 'error', '-show_streams', '-of', 'json', str(output)]))
                audio = details['streams'][0]
                if audio['codec_name'] != 'mp3' or int(audio['bit_rate']) != rate * 1000:
                    raise RuntimeError(f'Unexpected MP3 encoding result: {audio}')
                report['conversions'].append({'source': source.suffix[1:], 'bitrate_kbps': rate, 'bytes': output.stat().st_size})
    report['ok'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ffmpeg', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify(args.ffmpeg)
    content = json.dumps(report, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding='utf-8')
    print(content)


if __name__ == '__main__':
    main()
