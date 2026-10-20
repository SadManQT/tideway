"""Text-to-speech for every enabled storyboard scene.

Writes <work>/audio/<scene>-<hash>.wav (48 kHz mono PCM) and <work>/narration.json
with measured durations and sentence timings. Audio is cached by voice, rate and
text, so a re-render only synthesises scenes whose narration changed.

Engine: edge-tts neural voice (needs network). If it fails, Windows SAPI via
PowerShell System.Speech is used instead and recorded in narration.json.

    python scripts/pitch_video/narrate.py --work dist/video/work [--voice en-US-AndrewNeural]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
RATE = 48000


def find_ffmpeg() -> str:
    from shutil import which
    import os
    if os.environ.get("FFMPEG"):
        return os.environ["FFMPEG"]
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - optional dependency
        pass
    for candidate in [which("ffmpeg"), *Path.home().glob("AppData/Local/lla-tools/ffmpeg/*/bin/ffmpeg.exe")]:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise SystemExit("ffmpeg not found: pip install imageio-ffmpeg in the tools venv or set FFMPEG")


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text.strip())
    return [p.strip() for p in parts if p.strip()]


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def to_wav(ffmpeg: str, source: Path, target: Path) -> None:
    # Trim leading/trailing silence so scene timing follows the spoken words.
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(source), "-af",
                    "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05,"
                    "areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08,areverse",
                    "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(target)], check=True)


async def edge_tts_speak(text: str, voice: str, rate: str, mp3: Path) -> list[dict]:
    import edge_tts
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="SentenceBoundary")
    except TypeError:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
    marks = []
    with mp3.open("wb") as handle:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                handle.write(chunk["data"])
            elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                marks.append({"type": chunk["type"], "start": chunk["offset"] / 1e7,
                              "end": (chunk["offset"] + chunk["duration"]) / 1e7, "text": chunk["text"]})
    if mp3.stat().st_size < 1000:
        raise RuntimeError("edge-tts returned no audio")
    return marks


def sapi_speak(text: str, wav_path: Path) -> None:
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1;"
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
        "$s.Rate = 0;"
        f"$s.SetOutputToWaveFile('{wav_path}');"
        "$s.Speak([Console]::In.ReadToEnd()); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], input=text, text=True, check=True)


def sentence_timings(text: str, marks: list[dict], duration: float, offset: float) -> list[dict]:
    """Sentence cue times relative to the trimmed audio start."""
    sentences = [m for m in marks if m["type"] == "SentenceBoundary"]
    if sentences:
        cues = [{"start": max(0.0, m["start"] - offset), "end": max(0.0, m["end"] - offset), "text": m["text"].strip()} for m in sentences]
        cues[-1]["end"] = max(cues[-1]["end"], duration)
        return cues
    parts = split_sentences(text)
    total = sum(len(p) for p in parts) or 1
    cues, cursor = [], 0.0
    for part in parts:
        length = duration * len(part) / total
        cues.append({"start": cursor, "end": cursor + length, "text": part})
        cursor += length
    return cues


def leading_silence(ffmpeg: str, source: Path) -> float:
    """Seconds of silence trimmed from the start (to shift boundary offsets)."""
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(source), "-af", "silencedetect=n=-50dB:d=0.05", "-f", "null", "-"],
                            capture_output=True, text=True)
    first = re.search(r"silence_start: (-?[\d.]+)\s.*?silence_end: ([\d.]+)", result.stderr, re.S)
    if first and float(first.group(1)) <= 0.01:
        return float(first.group(2))
    return 0.0


def narrate(storyboard: Path, work: Path, voice: str | None = None, rate: str | None = None, engine: str = "auto") -> dict:
    board = json.loads(storyboard.read_text(encoding="utf-8"))
    voice = voice or board.get("voice", "en-US-AndrewNeural")
    rate = rate or board.get("rate", "+0%")
    ffmpeg = find_ffmpeg()
    audio_dir = work / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    result = {"voice": voice, "rate": rate, "engine": None, "scenes": {}}
    engines_used = set()
    scenes = [s for s in board["scenes"] if s.get("enabled") is not False and (s.get("narration") or "").strip()]

    def synthesise(scene: dict) -> tuple[Path, dict]:
        text = scene["narration"].strip()
        chosen = engine
        key = hashlib.sha256(f"{voice}|{rate}|{text}".encode()).hexdigest()[:12]
        wav_path = audio_dir / f"{scene['id']}-{key}.wav"
        meta_path = audio_dir / f"{scene['id']}-{key}.json"
        if wav_path.exists() and meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = None
            if chosen in ("auto", "edge"):
                mp3 = audio_dir / f"{scene['id']}-{key}.mp3"
                for attempt in range(3):
                    try:
                        marks = asyncio.run(edge_tts_speak(text, voice, rate, mp3))
                        offset = leading_silence(ffmpeg, mp3)
                        to_wav(ffmpeg, mp3, wav_path)
                        duration = wav_duration(wav_path)
                        meta = {"engine": f"edge-tts:{voice}", "duration": duration,
                                "sentences": sentence_timings(text, marks, duration, offset)}
                        break
                    except Exception as error:  # noqa: BLE001 - network TTS can fail
                        print(f"edge-tts failed for {scene['id']} (attempt {attempt + 1}): {error}", file=sys.stderr)
                mp3.unlink(missing_ok=True)
                if meta is None and chosen == "edge":
                    raise SystemExit("edge-tts failed and --engine edge was requested")
            if meta is None:
                raw = audio_dir / f"{scene['id']}-{key}-sapi.wav"
                sapi_speak(text, raw)
                to_wav(ffmpeg, raw, wav_path)
                raw.unlink(missing_ok=True)
                duration = wav_duration(wav_path)
                meta = {"engine": "windows-sapi", "duration": duration, "sentences": sentence_timings(text, [], duration, 0.0)}
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return wav_path, meta

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        outputs = list(pool.map(synthesise, scenes))
    for scene, (wav_path, meta) in zip(scenes, outputs):
        engines_used.add(meta["engine"])
        result["scenes"][scene["id"]] = {"wav": str(wav_path.relative_to(work)).replace("\\", "/"), **meta}
        print(f"narration {scene['id']}: {meta['duration']:.2f} s ({meta['engine']})")
    # Remove cached audio for narration text that no longer exists.
    keep = {Path(v["wav"]).stem for v in result["scenes"].values()}
    for stale in audio_dir.glob("*.wav"):
        if stale.stem not in keep:
            stale.unlink(missing_ok=True)
            stale.with_suffix(".json").unlink(missing_ok=True)
    result["engine"] = ", ".join(sorted(engines_used))
    (work / "narration.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--storyboard", type=Path, default=HERE / "storyboard.json")
    parser.add_argument("--work", type=Path, default=HERE.parents[1] / "dist" / "video" / "work")
    parser.add_argument("--voice")
    parser.add_argument("--rate")
    parser.add_argument("--engine", choices=["auto", "edge", "sapi"], default="auto")
    args = parser.parse_args()
    out = narrate(args.storyboard, args.work, args.voice, args.rate, args.engine)
    print(f"total narration {sum(s['duration'] for s in out['scenes'].values()):.1f} s")
