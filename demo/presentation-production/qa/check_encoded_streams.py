"""Independent read-only stream, decode and duration QA for final MP4."""
from pathlib import Path
import json
import subprocess
import sys

QA = Path(__file__).resolve().parent
PRODUCTION = QA.parent
ROOT = PRODUCTION.parents[1]
sys.path.insert(0, str(ROOT / 'tmp' / 'video-reference-analysis' / 'packages'))
import av
import imageio_ffmpeg

source = ROOT / 'demo' / 'Probaho-presentation.mp4'
timed = json.loads((PRODUCTION / 'render' / 'timed-scenes.json').read_text(encoding='utf-8'))
container = av.open(str(source))
streams = []
for stream in container.streams:
    context = stream.codec_context
    row = {'type': stream.type, 'codec': context.name, 'stream_duration_seconds': float(stream.duration * stream.time_base) if stream.duration is not None else None}
    if stream.type == 'video':
        row.update(width=context.width, height=context.height, pixel_format=context.format.name,
                   fps=float(stream.average_rate) if stream.average_rate else None, frames=stream.frames)
    if stream.type == 'audio':
        row.update(sample_rate=context.sample_rate, channels=context.channels,
                   layout=context.layout.name, bitrate=context.bit_rate)
    streams.append(row)
duration = container.duration / 1000000
container.close()
assert sum(s['type'] == 'video' for s in streams) == 1, streams
assert sum(s['type'] == 'audio' for s in streams) == 1, streams
audio = next(s for s in streams if s['type'] == 'audio')
video = next(s for s in streams if s['type'] == 'video')
assert audio['codec'] == 'aac' and audio['sample_rate'] > 0 and audio['channels'] > 0, audio
assert abs(duration - timed['target_seconds']) < 0.12, (duration, timed['target_seconds'])
assert abs(audio['stream_duration_seconds'] - timed['target_seconds']) < 0.12, audio
assert abs(video['stream_duration_seconds'] - timed['target_seconds']) < 0.12, video

decode = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error', '-i', str(source), '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, text=True)
assert decode.returncode == 0 and not decode.stderr.strip(), decode.stderr
result = {'status': 'passed', 'file': str(source), 'file_bytes': source.stat().st_size,
          'duration_seconds': duration, 'expected_duration_seconds': timed['target_seconds'],
          'streams': streams, 'entire_audio_stream_decoded_without_errors': True,
          'scope': 'Independent media stream/duration/decode check; root separately verifies PCM placement and visual motion.'}
(QA / 'encoded-stream-qa.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
