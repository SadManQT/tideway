"""One-command render of the Tideway pitch video.

    C:\\Users\\Administrator\\tideway-tools-venv\\Scripts\\python.exe scripts\\pitch_video\\build.py

Steps: narrate every scene (cached TTS) -> start Tideway on port 8792 with a fresh
data/video.sqlite3 -> record every scene in headless Chrome (record.mjs) -> stop the
app -> compose dist/video/tideway-pitch.mp4 (H.264 + AAC, 1920x1080, 30 fps, yuv420p,
faststart) with crossfades, burned-in captions and a sidecar .srt -> build-log.json
and four review stills. Fails loudly if the video would exceed max_seconds (4:55).
"""
from __future__ import annotations

import argparse
import array
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import narrate  # noqa: E402

RATE = narrate.RATE


def log(message: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {message}", flush=True)


def app_python() -> str:
    if os.environ.get("TIDEWAY_PYTHON"):
        return os.environ["TIDEWAY_PYTHON"]
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python311" / "python.exe"
    return str(candidate) if candidate.is_file() else sys.executable


def reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_app(port: int, db: Path, out_dir: Path) -> subprocess.Popen:
    base = f"http://127.0.0.1:{port}"
    if reachable(f"{base}/api/config"):
        raise SystemExit(f"Port {port} is already serving something; stop it first (the video needs a fresh database).")
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = Path(f"{db}{suffix}")
        if path.exists():
            path.unlink()
    db.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "OPENAI_API_KEY": "", "PYTHONIOENCODING": "utf-8"}
    handle = (out_dir / "app.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([app_python(), "run.py", "--port", str(port), "--db", str(db)], cwd=ROOT,
                            stdout=handle, stderr=subprocess.STDOUT, env=env,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(240):
        if proc.poll() is not None:
            raise SystemExit(f"Tideway exited early; see {out_dir / 'app.log'}")
        if reachable(f"{base}/api/config"):
            log(f"Tideway running at {base} (fresh {db.relative_to(ROOT)})")
            return proc
        time.sleep(0.25)
    proc.kill()
    raise SystemExit("Tideway did not start within 60 s")


def stop_app(proc: subprocess.Popen | None) -> None:
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def require_disk(path: Path, step: str, minimum_mb: int = 400) -> None:
    free = shutil.disk_usage(path).free / 1e6
    if free < minimum_mb:
        raise SystemExit(f"PAUSED before {step}: only {free:.0f} MB free on {path.anchor} (need >= {minimum_mb} MB). Free space and re-run.")
    log(f"disk ok before {step}: {free:.0f} MB free")


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def read_wav(path: Path) -> array.array:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != RATE or handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise SystemExit(f"Unexpected audio format in {path}")
        data = array.array("h")
        data.frombytes(handle.readframes(handle.getnframes()))
        return data


def srt_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chunk_caption(text: str, limit: int = 88) -> list[str]:
    """Split a sentence into caption-sized pieces at punctuation, then words."""
    if len(text) <= limit:
        return [text]
    pieces, current = [], ""
    for part in re.split(r"(?<=[,;:])\s+", text):
        candidate = f"{current} {part}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
        current = part
        while len(current) > limit:
            cut = current.rfind(" ", 0, limit)
            cut = cut if cut > 20 else limit
            pieces.append(current[:cut].strip())
            current = current[cut:].strip()
    if current:
        pieces.append(current)
    return pieces


def build_srt(timeline: list[dict], narration: dict, lead: float) -> str:
    cues = []
    for item in timeline:
        audio = narration["scenes"].get(item["id"])
        if not audio:
            continue
        base = item["start"] + lead
        for sentence in audio["sentences"]:
            pieces = chunk_caption(sentence["text"])
            total = sum(len(p) for p in pieces) or 1
            cursor = sentence["start"]
            span = max(0.3, sentence["end"] - sentence["start"])
            for piece in pieces:
                length = span * len(piece) / total
                cues.append((base + cursor, base + cursor + length, piece))
                cursor += length
    lines = []
    for index, (start, end, text) in enumerate(cues, 1):
        lines += [str(index), f"{srt_time(start)} --> {srt_time(min(end, start + 7))}", text, ""]
    return "\n".join(lines)


def ffmpeg_version(ffmpeg: str) -> str:
    out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).stdout
    return out.splitlines()[0] if out else "unknown"


def probe_duration(ffmpeg: str, path: Path) -> float:
    err = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3)) if match else 0.0


def compose(ffmpeg: str, work: Path, out_dir: Path, board: dict, record: dict, narration: dict, burn: bool) -> dict:
    timing = record["timing"]
    xfade, lead, fps = timing["xfade"], timing["lead"], timing["fps"]
    scenes = [s for s in record["scenes"] if not s.get("skipped")]
    if not scenes:
        raise SystemExit("No scenes were recorded")
    timeline, start = [], 0.0
    for index, scene in enumerate(scenes):
        timeline.append({**scene, "start": round(start, 3)})
        start += scene["length"] - (xfade if index < len(scenes) - 1 else 0)
    total = round(start, 3)
    limit = board.get("max_seconds", 295)
    if total > limit:
        raise SystemExit(f"FAIL: video would be {total:.1f} s, over the {limit} s limit. Shorten narration or remove scenes.")

    # Narration track: each scene's speech starts `lead` seconds into its clip.
    track = array.array("h", bytes(2 * int(round(total * RATE)) + 2 * RATE))
    for item in timeline:
        audio = narration["scenes"].get(item["id"])
        if not audio:
            continue
        samples = read_wav(work / audio["wav"])
        offset = int(round((item["start"] + lead) * RATE))
        track[offset:offset + len(samples)] = samples
    del track[int(round(total * RATE)):]
    track_path = work / "narration-track.wav"
    with wave.open(str(track_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(track.tobytes())

    srt = build_srt(timeline, narration, lead)
    srt_path = out_dir / "tideway-pitch.srt"
    srt_path.write_text(srt, encoding="utf-8")
    (work / "captions.srt").write_text(srt, encoding="utf-8")

    inputs, chains = [], []
    for index, item in enumerate(timeline):
        inputs += ["-i", str(work / item["clip"])]
        chains.append(f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS,fps={fps},format=yuv420p[v{index}]")
    last = "v0"
    for index in range(1, len(timeline)):
        label = f"x{index}"
        chains.append(f"[{last}][v{index}]xfade=transition=fade:duration={xfade}:offset={timeline[index]['start']:.3f}[{label}]")
        last = label
    style = ("FontName=Segoe UI,Fontsize=12,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00481300,BackColour=&H00481300,"
             "BorderStyle=3,Outline=6,Shadow=0,MarginV=14,MarginL=40,MarginR=40,WrapStyle=0")
    final_video = last
    if burn:
        chains.append(f"[{last}]subtitles=captions.srt:force_style='{style}'[vout]")
        final_video = "vout"
    output = out_dir / "tideway-pitch.mp4"
    partial = out_dir / "tideway-pitch.partial.mp4"
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-stats", *inputs, "-i", str(track_path),
               "-filter_complex", ";".join(chains), "-map", f"[{final_video}]", "-map", f"{len(timeline)}:a",
               "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
               "-ac", "2", "-movflags", "+faststart", "-t", f"{total:.3f}", str(partial)]
    log(f"composing {len(timeline)} scenes, {total:.1f} s, subtitles {'burned in' if burn else 'sidecar only'}")
    result = subprocess.run(command, cwd=work)
    if result.returncode != 0 and burn:
        log("subtitle burn-in failed; retrying with sidecar .srt only")
        chains = [c for c in chains if "subtitles=" not in c]
        command[command.index("-filter_complex") + 1] = ";".join(chains)
        command[command.index("-map") + 1] = f"[{last}]"
        burn = False
        result = subprocess.run(command, cwd=work)
    if result.returncode != 0:
        raise SystemExit("ffmpeg composition failed")
    partial.replace(output)
    track_path.unlink(missing_ok=True)
    return {"output": output, "srt": srt_path, "timeline": timeline, "total": total, "burned": burn}


def stills(ffmpeg: str, video: Path, total: float, out_dir: Path) -> list[str]:
    target = out_dir / "stills"
    target.mkdir(exist_ok=True)
    names = []
    for pct in (10, 35, 60, 85):
        name = target / f"still-{pct:02d}.jpg"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{total * pct / 100:.2f}", "-i", str(video),
                        "-frames:v", "1", "-q:v", "3", str(name)], check=True)
        names.append(str(name.relative_to(ROOT)).replace("\\", "/"))
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--storyboard", type=Path, default=HERE / "storyboard.json")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "video")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "video.sqlite3")
    parser.add_argument("--voice")
    parser.add_argument("--no-burn-subtitles", action="store_true", help="only write the .srt sidecar")
    parser.add_argument("--keep-clips", action="store_true", help="keep per-scene clips in dist/video/work/clips")
    parser.add_argument("--reuse-recording", action="store_true", help="skip the app and recorder; recompose existing clips")
    args = parser.parse_args()

    started = time.time()
    out_dir = args.out.resolve()
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    board = json.loads(args.storyboard.read_text(encoding="utf-8"))
    ffmpeg = narrate.find_ffmpeg()
    os.environ["FFMPEG"] = ffmpeg
    log(f"ffmpeg: {ffmpeg_version(ffmpeg)}")

    narration = narrate.narrate(args.storyboard, work, args.voice)
    timing = {"lead": 0.35, "tail": 0.55, "xfade": 0.5, **board.get("timing", {})}
    estimate = sum(max(s.get("min_seconds", 0), timing["lead"] + narration["scenes"][s["id"]]["duration"] + timing["tail"] + timing["xfade"])
                   for s in board["scenes"] if s["id"] in narration["scenes"] and not s.get("optional"))
    log(f"narration {sum(v['duration'] for v in narration['scenes'].values()):.1f} s; required scenes alone need >= {estimate:.0f} s")
    if estimate > board.get("max_seconds", 295):
        raise SystemExit(f"FAIL: required narration alone needs ~{estimate:.0f} s, over {board.get('max_seconds', 295)} s")

    if not args.reuse_recording:
        require_disk(out_dir, "recording")
        for old in (work / "clips").glob("*.mp4"):
            old.unlink()
        app = start_app(args.port, args.db.resolve(), out_dir)
        try:
            log("recording scenes in headless Chrome")
            node = shutil.which("node") or "node"
            subprocess.run([node, str(HERE / "record.mjs"), "--work", str(work), "--storyboard", str(args.storyboard.resolve()),
                            "--base", f"http://127.0.0.1:{args.port}", "--ffmpeg", ffmpeg], cwd=ROOT, check=True)
        except subprocess.CalledProcessError as error:
            raise SystemExit(f"FAIL: recorder failed ({error.returncode}); see dist/video/work/debug and dist/video/app.log") from error
        finally:
            stop_app(app)
            log("Tideway stopped")
    record = json.loads((work / "record.json").read_text(encoding="utf-8"))
    require_disk(out_dir, "composition")
    result = compose(ffmpeg, work, out_dir, board, record, narration, not args.no_burn_subtitles)
    output = result["output"]
    duration = probe_duration(ffmpeg, output)
    if duration > board.get("max_seconds", 295) + 0.5:
        raise SystemExit(f"FAIL: rendered video is {duration:.1f} s, over the limit")
    still_files = stills(ffmpeg, output, duration, out_dir)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    node_version = subprocess.run([shutil.which("node") or "node", "--version"], capture_output=True, text=True).stdout.strip()
    build_log = {
        "built_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "output": str(output.relative_to(ROOT)).replace("\\", "/"), "subtitles_srt": str(result["srt"].relative_to(ROOT)).replace("\\", "/"),
        "subtitles_burned_in": result["burned"], "duration_seconds": round(duration, 2), "max_seconds": board.get("max_seconds", 295),
        "size_bytes": output.stat().st_size, "sha256": digest,
        "video": {"codec": "H.264 (libx264, crf 20)", "resolution": "1920x1080", "fps": record["timing"]["fps"], "pix_fmt": "yuv420p", "faststart": True},
        "audio": {"codec": "AAC 160 kbps stereo 48 kHz", "loudness": "loudnorm I=-16 LUFS"},
        "voice": narration["voice"], "voice_rate": narration["rate"], "tts_engine": narration["engine"],
        "ffmpeg": ffmpeg_version(ffmpeg), "node": node_version, "browser": record.get("browser"),
        "source_commit": git("rev-parse", "HEAD"), "source_dirty": bool(git("status", "--porcelain")),
        "storyboard_sha256": hashlib.sha256(args.storyboard.read_bytes()).hexdigest(),
        "app": {"port": args.port, "database": "fresh data/video.sqlite3 (synthetic demo data)"},
        "timing": record["timing"],
        "scenes": [{"id": t["id"], "kind": t["kind"], "start_seconds": t["start"], "length_seconds": t["length"],
                    "narration_seconds": round(narration["scenes"].get(t["id"], {}).get("duration", 0), 2),
                    "actions_seconds": t.get("actions_seconds")} for t in result["timeline"]],
        "skipped_scenes": [{"id": s["id"], "reason": s["skipped"]} for s in record["scenes"] if s.get("skipped")],
        "page_errors": record.get("page_errors", []),
        "stills": still_files,
        "render_seconds": round(time.time() - started, 1),
    }
    (out_dir / "build-log.json").write_text(json.dumps(build_log, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.keep_clips and not args.reuse_recording:
        shutil.rmtree(work / "clips", ignore_errors=True)
    log(f"DONE {output} - {duration:.1f} s, {output.stat().st_size / 1e6:.1f} MB")
    for skipped in build_log["skipped_scenes"]:
        log(f"skipped {skipped['id']}: {skipped['reason']}")


if __name__ == "__main__":
    main()
