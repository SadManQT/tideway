"""Read-only ASR/content and waveform QA for all generated Probaho takes."""
from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import wave
from difflib import SequenceMatcher

QA = Path(__file__).resolve().parent
PRODUCTION = QA.parent
ROOT = PRODUCTION.parents[1]
ANALYSIS = ROOT / 'tmp' / 'video-reference-analysis'
sys.path.insert(0, str(ANALYSIS / 'packages'))
import imageio_ffmpeg
import numpy as np
from faster_whisper import WhisperModel

NUMBERS = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
           'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
           'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
           'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30,
           'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
           'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6,
           'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10}


def normalize(text):
    text = text.lower().replace("'", '').replace('’', '')
    text = re.sub(r'(?<=\d),(?=\d)', '', text)
    text = re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', text)
    text = re.sub(r'\bs[\s.]*m[\s.]*e\b', 'sme', text)
    text = re.sub(r'\bc[\s.]*s[\s.]*v\b', 'csv', text)
    text = re.sub(r'\bs[\s.]*q[\s.]*l\b', 'sql', text)
    words = re.findall(r'[a-z]+|\d+', text)
    result = []
    group = 0
    total = 0
    active = False
    for word in words + ['__END__']:
        if word in NUMBERS:
            group += NUMBERS[word]
            active = True
            continue
        if word == 'hundred' and active:
            group = (group or 1) * 100
            continue
        if word in ('thousand', 'million') and active:
            total += (group or 1) * (1000 if word == 'thousand' else 1000000)
            group = 0
            continue
        if active:
            result.append(str(total + group))
            group = total = 0
            active = False
        if word != '__END__':
            # Proper-name phonetic variants are retained in raw transcript.
            result.append('probaho' if word in ('probeho', 'provaho', 'probo', 'probho') else word)
    return result


def edit_distance(a, b):
    old = list(range(len(b) + 1))
    for i, word in enumerate(a, 1):
        new = [i]
        for j, other in enumerate(b, 1):
            new.append(min(new[-1] + 1, old[j] + 1, old[j - 1] + (word != other)))
        old = new
    return old[-1]


def differences(expected, actual):
    rows = []
    for tag, a, b, c, d in SequenceMatcher(a=expected, b=actual, autojunk=False).get_opcodes():
        if tag != 'equal':
            rows.append({'operation': tag, 'expected': ' '.join(expected[a:b]), 'recognized': ' '.join(actual[c:d])})
    return rows


def waveform(path):
    with wave.open(str(path), 'rb') as wav:
        rate, frames = wav.getframerate(), wav.getnframes()
        channels, width = wav.getnchannels(), wav.getsampwidth()
        assert channels == 1 and width == 2, (channels, width)
        samples = np.frombuffer(wav.readframes(frames), dtype=np.int16).astype(np.float32) / 32768.0
    size = max(1, rate // 100)
    padded = np.pad(samples, (0, (-len(samples)) % size))
    rms = np.sqrt(np.mean(padded.reshape(-1, size) ** 2, axis=1))
    peak_rms = float(np.max(rms)) if len(rms) else 0
    threshold = max(10 ** (-55 / 20), peak_rms * 10 ** (-42 / 20))
    active = np.flatnonzero(rms > threshold)
    leading = float(active[0] * size / rate) if len(active) else frames / rate
    trailing = max(0.0, frames / rate - float((active[-1] + 1) * size / rate)) if len(active) else frames / rate
    return {
        'duration_seconds': round(frames / rate, 6), 'sample_rate': rate,
        'channels': channels, 'sample_width': width, 'frames': frames,
        'peak_dbfs': round(20 * math.log10(max(float(np.max(np.abs(samples))), 1e-12)), 2),
        'rms_dbfs': round(20 * math.log10(max(float(np.sqrt(np.mean(samples ** 2))), 1e-12)), 2),
        'clipped_sample_count': int(np.sum(np.abs(samples) >= 32766 / 32768)),
        'leading_silence_seconds': round(leading, 3),
        'trailing_silence_seconds': round(trailing, 3),
        'silence_method': '10ms RMS windows; threshold max(-55dBFS, maximum-window RMS -42dB)',
    }


CRITICAL = {
    3: {'opening120k': '120000', 'payroll80k': '80000', 'supplier70k': '70000',
        'receivable20k': '20000', 'october31': 'october 31', 'closing-minus10k': 'minus 10000', 'gap30k': '30000'},
    5: {'delay7days': '7 day', 'late-closing-minus30k': 'minus 30000', 'late-gap50k': '50000'},
    6: {'supplier-deferral40k': '40000', 'november7': 'november 7', 'mock-cannot-execute': 'cannot execute',
        'reminder-is-not-cash': 'never counts as collected cash'},
    8: {'recovered-closing30k': '30000', 'no-reserve-shortfall': 'no reserve shortfall',
        'obligation-remains': 'supplier obligation still exists', 'single-execution': 'instead of executing twice'},
    10: {'local-demo': 'local demo', 'live-model-not-tested': 'not yet been tested'},
    11: {'backend-tests30': '30', 'evaluation-cases18': '18', 'synthetic-results': 'synthetic', 'production-not-established': 'production readiness'},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=12)
    args = parser.parse_args()
    QA.mkdir(parents=True, exist_ok=True)
    scenes = json.loads((PRODUCTION / 'script' / 'scenes.json').read_text(encoding='utf-8'))['scenes']
    cache_path = QA / 'narration-scene-asr.json'
    previous = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {'scenes': []}
    cache = {r['scene_index']: r for r in previous.get('scenes', [])}
    model = None
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    result = []
    for i, scene in enumerate(scenes[:args.limit], 1):
        path = PRODUCTION / 'audio-ai' / 'wav' / f'scene-{i:02d}.wav'
        if not path.exists() or path.stat().st_size <= 44:
            print(f'WAITING: scene {i:02d} is not available; run again once generation completes.', flush=True)
            break
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if cache.get(i, {}).get('wav_sha256') == digest:
            row = cache[i]
            print(f'REUSED: scene {i:02d} unchanged WAV SHA256.', flush=True)
        else:
            if model is None:
                model = WhisperModel('base.en', device='cpu', compute_type='int8', cpu_threads=4,
                                     download_root=str(ANALYSIS / 'models'), local_files_only=True)
            raw = subprocess.run([ffmpeg, '-loglevel', 'error', '-i', str(path), '-f', 's16le', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', '-'], capture_output=True, check=True).stdout
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            segments, info = model.transcribe(samples, beam_size=5, language='en', condition_on_previous_text=False)
            segments = [{'start': round(s.start, 3), 'end': round(s.end, 3), 'text': s.text.strip()} for s in segments]
            actual = ' '.join(s['text'] for s in segments)
            expected = scene['narration']
            a, b = normalize(expected), normalize(actual)
            stats = waveform(path)
            joined = ' '.join(b)
            critical = {name: phrase in joined for name, phrase in CRITICAL.get(i, {}).items()}
            row = {
                'scene_index': i, 'scene_id': scene['id'], 'file': str(path.relative_to(PRODUCTION)),
                'wav_sha256': digest, 'expected': expected, 'recognized': actual, 'asr_segments': segments,
                'normalized_expected_words': a, 'normalized_recognized_words': b,
                'normalized_word_error_rate': round(edit_distance(a, b) / max(len(a), 1), 4),
                'differences_requiring_review': differences(a, b),
                'starts_with_expected_first_two_words': a[:2] == b[:2],
                'ends_with_expected_last_two_words': a[-2:] == b[-2:],
                'critical_spoken_checks': critical, 'waveform': stats,
                'timing_note': 'ASR segment times are approximate and can overhang actual duration; waveform duration is authoritative.',
            }
            print(f'ASR scene {i:02d}: {actual}', flush=True)
            print(f'  WER {row["normalized_word_error_rate"]:.2%}; leading {stats["leading_silence_seconds"]:.3f}s; trailing {stats["trailing_silence_seconds"]:.3f}s; numeric checks {critical}', flush=True)
        result.append(row)
        cache_path.write_text(json.dumps({'method': 'Local faster-whisper base.en; CPU int8; beam5; ASR assists human review', 'scenes': result}, indent=2), encoding='utf-8')
    complete = len(result) == len(scenes)
    payload = {
        'status': 'complete_pending_human_review' if complete else 'partial',
        'scene_count_checked': len(result), 'required_scene_count': len(scenes),
        'missing_scene_indices': list(range(len(result) + 1, len(scenes) + 1)),
        'all_critical_spoken_checks_passed': all(all(r['critical_spoken_checks'].values()) for r in result),
        'all_first_last_words_present': all(r['starts_with_expected_first_two_words'] and r['ends_with_expected_last_two_words'] for r in result),
        'all_waveforms_unclipped': all(r['waveform']['clipped_sample_count'] == 0 for r in result),
        'total_take_duration_seconds': round(sum(r['waveform']['duration_seconds'] for r in result), 6),
        'overall_normalized_wer': round(sum(edit_distance(r['normalized_expected_words'], r['normalized_recognized_words']) for r in result) / max(sum(len(r['normalized_expected_words']) for r in result), 1), 4),
        'scenes': result,
    }
    combined = PRODUCTION / 'audio-ai' / 'narration-full.wav'
    if complete and combined.exists():
        with wave.open(str(combined), 'rb') as wav:
            actual_pcm = wav.readframes(wav.getnframes())
        take_pcm = []
        for row in result:
            with wave.open(str(PRODUCTION / row['file']), 'rb') as wav:
                take_pcm.append(wav.readframes(wav.getnframes()))
        payload['combined_wav'] = {
            'file': str(combined.relative_to(PRODUCTION)),
            'sha256': hashlib.sha256(combined.read_bytes()).hexdigest(),
            'pcm_exactly_matches_ordered_takes': actual_pcm == b''.join(take_pcm),
            'waveform': waveform(combined),
        }
    (QA / 'narration-qa.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in payload.items() if k not in ('scenes',)}, indent=2), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
