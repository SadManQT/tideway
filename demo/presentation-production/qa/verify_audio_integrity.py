from pathlib import Path
from array import array
import hashlib, json, math, sys, wave
from datetime import datetime, timezone

QA = Path(__file__).resolve().parent
BASE = QA.parent
manifest_path = BASE / "audio-ai" / "audio-manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["status"] == "complete" and len(manifest["scenes"]) == 12
results = []
concatenated_pcm_hash = hashlib.sha256()
all_checks = []
total_frames = 0


def dbfs(value):
    return round(20 * math.log10(value / 32768), 3) if value > 0 else None


for entry in manifest["scenes"]:
    wav_path = BASE / entry["wav_file"]
    mp3_path = BASE / entry["file"]
    with wave.open(str(wav_path), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        frames = source.getnframes()
        raw = source.readframes(frames)
    assert width == 2 and channels == 1
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    square_sum = sum(value * value for value in samples)
    rms = math.sqrt(square_sum / len(samples))
    peak = max(abs(value) for value in samples)
    clipped = sum(value >= 32767 or value <= -32768 for value in samples)
    near_clipped = sum(abs(value) >= int(32768 * .995) for value in samples)
    # Ten-millisecond windows quantify quiet margins without editing any audio.
    window = max(1, rate // 100)
    quiet_threshold = 32768 * 10 ** (-45 / 20)
    active = []
    longest_quiet = 0
    quiet_run = 0
    for first in range(0, len(samples), window):
        block = samples[first:first + window]
        block_rms = math.sqrt(sum(value * value for value in block) / len(block))
        if block_rms >= quiet_threshold:
            active.append(first)
            longest_quiet = max(longest_quiet, quiet_run)
            quiet_run = 0
        else:
            quiet_run += len(block)
    longest_quiet = max(longest_quiet, quiet_run)
    duration = frames / rate
    sha_wav = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    sha_mp3 = hashlib.sha256(mp3_path.read_bytes()).hexdigest()
    checks = {
        "wav_exists_and_nonempty": wav_path.stat().st_size > 44 and frames > 0,
        "mp3_exists_and_nonempty": mp3_path.stat().st_size > 1000,
        "wav_sha256_matches_manifest": sha_wav == entry["wav_sha256"],
        "mp3_sha256_matches_manifest": sha_mp3 == entry["mp3_sha256"],
        "duration_matches_manifest": abs(duration - entry["duration_seconds"]) < .000001,
        "profile_matches_manifest": rate == entry["sample_rate"] == 24000 and channels == entry["channels"] == 1 and width == entry["sample_width"] == 2,
        "not_silent": rms > 32768 * 10 ** (-50 / 20) and bool(active),
        "no_full_scale_clipped_samples": clipped == 0,
    }
    item = {
        "scene_index": entry["scene_index"], "scene_id": entry["scene_id"],
        "mp3_file": entry["file"], "wav_file": entry["wav_file"],
        "wav_sha256": sha_wav, "mp3_sha256": sha_mp3,
        "duration_seconds": round(duration, 6), "sample_rate": rate,
        "channels": channels, "sample_width": width, "frames": frames,
        "rms_pcm": round(rms, 3), "rms_dbfs": dbfs(rms),
        "peak_pcm": peak, "peak_dbfs": dbfs(peak),
        "clipped_samples": clipped, "near_full_scale_samples": near_clipped,
        "quiet_threshold_dbfs": -45,
        "leading_quiet_seconds": round(active[0] / rate, 3) if active else round(duration, 3),
        "trailing_quiet_seconds": round((len(samples) - min(len(samples), active[-1] + window)) / rate, 3) if active else round(duration, 3),
        "longest_quiet_window_seconds": round(longest_quiet / rate, 3),
        "checks": checks,
        "status": "passed" if all(checks.values()) else "failed",
    }
    results.append(item)
    all_checks.extend(checks.values())
    concatenated_pcm_hash.update(raw)
    total_frames += frames

combined_path = BASE / manifest["combined_wav"]
combined_mp3 = BASE / manifest["combined_mp3"]
with wave.open(str(combined_path), "rb") as combined:
    combined_frames = combined.getnframes()
    combined_rate = combined.getframerate()
    combined_raw = combined.readframes(combined_frames)
combined_checks = {
    "scene_frame_sum_matches_combined": total_frames == combined_frames,
    "combined_pcm_is_exact_scene_concatenation": hashlib.sha256(combined_raw).hexdigest() == concatenated_pcm_hash.hexdigest(),
    "combined_wav_sha256_matches_manifest": hashlib.sha256(combined_path.read_bytes()).hexdigest() == manifest["combined_wav_sha256"],
    "combined_mp3_sha256_matches_manifest": hashlib.sha256(combined_mp3.read_bytes()).hexdigest() == manifest["combined_mp3_sha256"],
    "combined_duration_matches_manifest": abs(combined_frames/combined_rate - manifest["combined_duration_seconds"]) < .000001,
    "all_scenes_use_one_recorded_voice_profile": manifest["voice"] == "en-US-GuyNeural" and manifest["rate"] == "-8%",
}
all_checks.extend(combined_checks.values())
report = {
    "project": "Probaho", "status": "passed" if all(all_checks) else "failed",
    "checked_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "manifest": "audio-ai/audio-manifest.json", "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "voice": manifest["voice"], "rate": manifest["rate"],
    "scene_count": len(results), "total_duration_seconds": round(combined_frames/combined_rate, 6),
    "total_clipped_samples": sum(item["clipped_samples"] for item in results),
    "total_near_full_scale_samples": sum(item["near_full_scale_samples"] for item in results),
    "all_scenes_nonempty_and_not_silent": all(item["checks"]["not_silent"] and item["checks"]["wav_exists_and_nonempty"] and item["checks"]["mp3_exists_and_nonempty"] for item in results),
    "combined_checks": combined_checks, "scenes": results,
    "scope_note": "Technical audio integrity only. This does not replace ASR/subjective speech-content or pronunciation review. No voice take was modified.",
}
out = QA / "audio-integrity.json"
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"status":report["status"],"scene_count":report["scene_count"],"total_duration_seconds":report["total_duration_seconds"],"total_clipped_samples":report["total_clipped_samples"],"all_scenes_nonempty_and_not_silent":report["all_scenes_nonempty_and_not_silent"],"rms_dbfs_range":[min(x["rms_dbfs"] for x in results),max(x["rms_dbfs"] for x in results)],"peak_dbfs_range":[min(x["peak_dbfs"] for x in results),max(x["peak_dbfs"] for x in results)],"report":str(out)},indent=2))
if report["status"] != "passed":
    raise SystemExit(1)
