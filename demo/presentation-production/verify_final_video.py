"""Check the actual encoded deliverable, scene motion and narration alignment."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import wave

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent


def read_pcm(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        if handle.getsampwidth() != 2:
            raise ValueError("Expected 16-bit PCM.")
        samples = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32), rate


def boxes(path: Path) -> list[dict]:
    found = []
    with path.open("rb") as handle:
        total = path.stat().st_size
        position = 0
        while position + 8 <= total:
            handle.seek(position)
            size, kind = struct.unpack(">I4s", handle.read(8))
            header = 8
            if size == 1:
                size = struct.unpack(">Q", handle.read(8))[0]
                header = 16
            elif size == 0:
                size = total - position
            if size < header or position + size > total:
                raise ValueError("Invalid MP4 box bounds.")
            found.append({"type": kind.decode("ascii", "replace"), "offset": position, "bytes": size})
            position += size
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_video = ROOT / "Probaho-presentation.mp4"
    if not default_video.exists():
        default_video = ROOT.parent / "Probaho-presentation.mp4"
    parser.add_argument("--video", type=Path, default=default_video)
    parser.add_argument("--ffmpeg", required=True)
    args = parser.parse_args()
    qa = ROOT / "qa"
    qa.mkdir(exist_ok=True)
    timeline_file = ROOT / "render/timed-scenes.json"
    if not timeline_file.exists():
        timeline_file = ROOT / "render/timed-scenes-portable.json"
    timeline = json.loads(timeline_file.read_text(encoding="utf-8-sig"))
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit("Could not open final MP4.")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps
    if (width, height) != (1920, 1080) or abs(fps - 25) > .001:
        raise SystemExit("Unexpected video dimensions or frame rate.")
    if abs(duration - timeline["target_seconds"]) > .041:
        raise SystemExit("Encoded duration does not match measured scene timeline.")
    sheet = Image.new("RGB", (960, 4 * 201), "#080f2e")
    labels = ImageDraw.Draw(sheet)
    scenes = []
    for index, scene in enumerate(timeline["scenes"]):
        pictures = []
        times = []
        for fraction in (.07, .20, .45, .65, .90):
            second = scene["start_seconds"] + fraction * scene["duration"]
            cap.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
            valid, frame = cap.read()
            if not valid:
                raise SystemExit(f"Could not decode {scene['id']} at {second}.")
            pictures.append(frame)
            times.append(round(second, 3))
        changes = [float(np.abs(left[120:970].astype(np.float32) - right[120:970].astype(np.float32)).mean()) for left, right in zip(pictures, pictures[1:])]
        if max(changes) < .3:
            raise SystemExit(f"No meaningful motion found in {scene['id']}.")
        representative = pictures[3]
        if representative.mean() < 5:
            raise SystemExit(f"Unexpected dark/blank frame in {scene['id']}.")
        tile = Image.fromarray(cv2.cvtColor(representative, cv2.COLOR_BGR2RGB)).resize((320, 180))
        x, y = (index % 3) * 320, (index // 3) * 201
        sheet.paste(tile, (x, y))
        labels.text((x + 6, y + 183), scene["id"], fill="#adbedf")
        scenes.append({"scene_id": scene["id"], "sample_seconds": times, "adjacent_frame_mean_differences": [round(value, 4) for value in changes], "motion_detected": True})
    cap.release()
    sheet.save(qa / "encoded-contact-sheet.jpg", quality=94)

    decoded = qa / "final-audio-decoded.wav"
    subprocess.run([args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(args.video), "-vn", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(decoded)], check=True)
    encoded_audio, rate = read_pcm(decoded)
    for scene, result in zip(timeline["scenes"], scenes):
        path = Path(scene["voice_file"])
        if not path.is_absolute():
            path = ROOT / path
        original, source_rate = read_pcm(path)
        if source_rate != rate:
            raise SystemExit("Unexpected narration sample rate.")
        offset = round((scene["start_seconds"] + scene.get("voice_lead_seconds", 0)) * rate)
        # Check the entire take, with tolerance for AAC sample alignment.
        target = original[::6]
        norm = float(np.linalg.norm(target))
        best = (-1.0, 0)
        for lag in range(-480, 481, 24):
            start = offset + lag
            if start < 0 or start + len(original) > len(encoded_audio):
                continue
            actual = encoded_audio[start:start + len(original):6]
            denom = norm * float(np.linalg.norm(actual))
            score = float(np.dot(target, actual) / denom) if denom else 0
            if score > best[0]:
                best = (score, lag)
        result["narration_correlation"] = round(best[0], 6)
        result["best_alignment_offset_ms"] = round(best[1] * 1000 / rate, 3)
        if best[0] < .95:
            raise SystemExit(f"Narration does not match scene {scene['id']}: {best[0]}")

    atoms = boxes(args.video)
    positions = {atom["type"]: atom["offset"] for atom in atoms}
    faststart = positions.get("moov", float("inf")) < positions.get("mdat", -1)
    if not faststart:
        raise SystemExit("Final MP4 is not prepared for fast-start playback.")
    decode = subprocess.run([args.ffmpeg, "-hide_banner", "-v", "error", "-i", str(args.video), "-f", "null", "-"], capture_output=True, text=True)
    if decode.returncode or decode.stderr.strip():
        raise SystemExit("Decode errors: " + decode.stderr)
    with args.video.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    report = {"status": "passed", "video": str(args.video.resolve()), "sha256": checksum, "bytes": args.video.stat().st_size, "width": width, "height": height, "fps": fps, "frames": frame_count, "duration_seconds": duration, "decoded_audio_duration_seconds": len(encoded_audio) / rate, "faststart": faststart, "mp4_boxes": atoms, "full_decode_errors": 0, "scenes": scenes}
    (qa / "final-video-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("scenes", "mp4_boxes")}, indent=2))


if __name__ == "__main__":
    main()
