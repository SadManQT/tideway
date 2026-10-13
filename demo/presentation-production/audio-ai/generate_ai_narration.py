"""Generate consistent ordinary English AI narration; no reference voice cloning."""
from pathlib import Path
import asyncio, hashlib, json, os, shutil, subprocess, sys, time, wave
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
PRODUCTION = OUT.parent
ROOT = PRODUCTION.parents[1]
sys.path.insert(0, str(ROOT / "tmp" / "video-capabilities" / "edge-packages"))
import edge_tts
VOICE = "en-US-GuyNeural"
RATE = "-8%"
SCENES = json.loads((PRODUCTION / "script" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
def find_ffmpeg():
    benchmark = ROOT / "tmp" / "video-capabilities" / "benchmark.json"
    if benchmark.exists():
        candidate = Path(json.loads(benchmark.read_text(encoding="utf-8"))["ffmpeg"])
        if candidate.exists():
            return candidate
    if shutil.which("ffmpeg"):
        return Path(shutil.which("ffmpeg"))
    import imageio_ffmpeg
    return Path(imageio_ffmpeg.get_ffmpeg_exe())


FFMPEG = find_ffmpeg()
MANIFEST = OUT / "audio-manifest.json"
WAV_DIR = OUT / "wav"
WAV_DIR.mkdir(parents=True, exist_ok=True)
manifest = {
    "project": "Probaho", "language": "English",
    "generation_source": "Microsoft Edge online text-to-speech using the edge-tts client",
    "client_version": edge_tts.__version__,
    "voice": VOICE, "rate": RATE, "pitch": "+0Hz", "volume": "+0%",
    "voice_note": "Ordinary synthetic English narrator, explicitly approved by user. It is not the reference speaker. No F5 cloned takes are mixed into this narration.",
    "reference_use": "Visual motion and general presentation cadence only.",
    "paid_calls": False, "concurrency": 2,
    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "status": "generating", "scenes": [],
}
for index, scene in enumerate(SCENES, 1):
    manifest["scenes"].append({
        "scene_index": index, "scene_id": scene["id"], "title": scene["title"],
        "text": scene["narration"], "word_count": scene["word_count"],
        "file": f"audio-ai/scene-{index:02d}.mp3",
        "wav_file": f"audio-ai/wav/scene-{index:02d}.wav",
        "status": "pending",
    })


def write_manifest():
    manifest["completed_scene_count"] = sum(x["status"] == "generated" for x in manifest["scenes"])
    manifest["total_audio_seconds"] = round(sum(x.get("duration_seconds", 0) for x in manifest["scenes"] if x["status"] == "generated"), 6)
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pending = MANIFEST.with_suffix(".json.pending")
    pending.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    for attempt in range(8):
        try:
            os.replace(pending, MANIFEST)
            break
        except PermissionError:
            if attempt == 7:
                raise
            # OneDrive/scanner readers can briefly hold a Windows file handle.
            # Retry only the local metadata replacement, never a TTS request.
            time.sleep(0.1 * (attempt + 1))


def wav_info(path):
    with wave.open(str(path), "rb") as wav:
        data = {"duration_seconds": round(wav.getnframes()/wav.getframerate(), 6),
                "sample_rate": wav.getframerate(), "channels": wav.getnchannels(),
                "sample_width": wav.getsampwidth(), "frame_count": wav.getnframes()}
    if data["duration_seconds"] <= 1 or data["frame_count"] <= 0:
        raise ValueError("Decoded narration is empty or too short.")
    return data


async def generate_one(index, scene, gate):
    entry = manifest["scenes"][index-1]
    if entry["status"] == "generated":
        print(f"SCENE {index:02d} SKIP checksum-verified successful output", flush=True)
        return
    mp3 = OUT / f"scene-{index:02d}.mp3"
    partial = OUT / f"scene-{index:02d}.partial.mp3"
    wav = WAV_DIR / f"scene-{index:02d}.wav"
    async with gate:
        if mp3.exists() or wav.exists() or partial.exists():
            entry["status"] = "failed"
            entry["error"] = "Target/partial already exists; inspect before retrying, no overwrite."
            write_manifest()
            return
        start = time.monotonic()
        entry["status"] = "generating"
        write_manifest()
        print(f"SCENE {index:02d} START ({scene['word_count']} words)", flush=True)
        try:
            communicate = edge_tts.Communicate(scene["narration"], VOICE, rate=RATE, volume="+0%", pitch="+0Hz")
            await communicate.save(str(partial))
            if not partial.is_file() or partial.stat().st_size < 1000:
                raise ValueError("TTS returned an empty or invalid MP3.")
            result = await asyncio.to_thread(subprocess.run,
                [str(FFMPEG), "-v", "error", "-n", "-i", str(partial), "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                capture_output=True, text=True)
            if result.returncode:
                raise ValueError("MP3 decode failed: " + result.stderr.strip())
            entry.update(wav_info(wav))
            with mp3.open("xb") as dest, partial.open("rb") as src:
                shutil.copyfileobj(src, dest)
            entry["mp3_sha256"] = hashlib.sha256(mp3.read_bytes()).hexdigest()
            entry["wav_sha256"] = hashlib.sha256(wav.read_bytes()).hexdigest()
            entry["mp3_bytes"] = mp3.stat().st_size
            entry["generation_elapsed_seconds"] = round(time.monotonic()-start, 3)
            entry["status"] = "generated"
            entry["completed_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            # Keep partial as the untouched download provenance; never overwrite outputs.
            write_manifest()
            print(f"SCENE {index:02d} COMPLETE {entry['duration_seconds']:.3f}s", flush=True)
        except Exception as exc:
            entry["status"] = "failed"
            entry["error_type"] = type(exc).__name__
            entry["error"] = str(exc)
            entry["generation_elapsed_seconds"] = round(time.monotonic()-start, 3)
            write_manifest()
            print(f"SCENE {index:02d} FAILED: {type(exc).__name__}: {exc}", flush=True)


async def main():
    if MANIFEST.exists():
        candidates = [MANIFEST]
        pending = MANIFEST.with_suffix(".json.pending")
        if pending.exists():
            candidates.append(pending)
        previous = json.loads(max(candidates, key=lambda p: p.stat().st_mtime_ns).read_text(encoding="utf-8"))
        if previous.get("voice") != VOICE or previous.get("rate") != RATE:
            raise RuntimeError("Existing narration voice/settings changed; do not mix voices.")
        old_entries = {item["scene_id"]: item for item in previous["scenes"]}
        for index, entry in enumerate(manifest["scenes"], 1):
            old = old_entries.get(entry["scene_id"])
            if not old or old.get("text") != entry["text"]:
                raise RuntimeError("Existing narration text changed; inspect before generation.")
            mp3 = OUT / f"scene-{index:02d}.mp3"
            wav = WAV_DIR / f"scene-{index:02d}.wav"
            partial = OUT / f"scene-{index:02d}.partial.mp3"
            if mp3.exists() and wav.exists():
                mp3_hash = hashlib.sha256(mp3.read_bytes()).hexdigest()
                wav_hash = hashlib.sha256(wav.read_bytes()).hexdigest()
                if old.get("mp3_sha256") != mp3_hash or old.get("wav_sha256") != wav_hash:
                    raise RuntimeError(f"Scene{index:02d}checksum mismatch; preserve and reconcile.")
                entry.update(old)
                entry.update(wav_info(wav))
                entry["status"] = "generated"
                if entry.get("error"):
                    entry["reconciliation_note"] = "Audio already completed before local manifest file-lock error; validated hashes and preserved without another TTS call."
                    entry.pop("error", None)
                    entry.pop("error_type", None)
            elif mp3.exists() or wav.exists():
                raise RuntimeError(f"Scene{index:02d}has an incomplete output pair; reconcile before retry.")
            elif partial.exists():
                if partial.stat().st_size:
                    raise RuntimeError(f"Scene{index:02d}has nonempty partial audio; reconcile before retry.")
                archived = OUT / f"scene-{index:02d}.cancelled-zero-bytes.mp3"
                if archived.exists():
                    raise RuntimeError("Zero-byte cancellation archive already exists; inspect before retry.")
                partial.rename(archived)
                entry["reconciliation_note"] = "Prior process cancelled after local manifest file-lock error; received zero audio bytes. Empty artifact preserved separately; this is a known failed take."
            else:
                entry["reconciliation_note"] = "No output file existed after prior local process stopped; generation had not started for this scene."
        manifest["created_utc"] = previous["created_utc"]
        manifest["resumed_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_manifest()
    gate = asyncio.Semaphore(2)
    await asyncio.gather(*(generate_one(i, scene, gate) for i, scene in enumerate(SCENES, 1)))
    if not all(x["status"] == "generated" for x in manifest["scenes"]):
        manifest["status"] = "stopped_after_failed_scenes"
        write_manifest()
        print("GENERATION PARTIAL: failed scenes require inspection before retry.", flush=True)
        return 1

    combined = OUT / "narration-full.wav"
    with wave.open(str(combined), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24000)
        for i in range(1, len(SCENES)+1):
            with wave.open(str(WAV_DIR / f"scene-{i:02d}.wav"), "rb") as source:
                target.writeframes(source.readframes(source.getnframes()))
    combined_mp3 = OUT / "narration-full.mp3"
    result = await asyncio.to_thread(subprocess.run,
        [str(FFMPEG), "-v", "error", "-n", "-i", str(combined), "-c:a", "libmp3lame", "-b:a", "128k", str(combined_mp3)],
        capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Full MP3 conversion failed: " + result.stderr.strip())
    manifest["combined_wav"] = "audio-ai/narration-full.wav"
    manifest["combined_mp3"] = "audio-ai/narration-full.mp3"
    manifest["combined_duration_seconds"] = wav_info(combined)["duration_seconds"]
    manifest["combined_wav_sha256"] = hashlib.sha256(combined.read_bytes()).hexdigest()
    manifest["combined_mp3_sha256"] = hashlib.sha256(combined_mp3.read_bytes()).hexdigest()
    manifest["status"] = "complete"
    write_manifest()
    print(json.dumps({"status": "complete", "scenes": len(SCENES), "total_audio_seconds": manifest["total_audio_seconds"], "combined_duration_seconds": manifest["combined_duration_seconds"], "voice": VOICE, "rate": RATE}), flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
