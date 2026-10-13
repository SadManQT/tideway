"""Package only the final editable presentation assets; exclude secrets/caches."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "Probaho-presentation-source.zip"


def relative_file(value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        raise ValueError(f"Unexpected external file in final scene manifest: {path}")


def main() -> None:
    timeline = ROOT / "render/timed-scenes.json"
    if not timeline.exists():
        raise SystemExit("Final measured timeline is not ready.")
    payload = json.loads(timeline.read_text(encoding="utf-8-sig"))
    if len(payload["scenes"]) != 12 or payload.get("partial_preview"):
        raise SystemExit("Refusing to package an incomplete presentation.")
    for scene in payload["scenes"]:
        for name in ("voice_file", "screenshot"):
            if scene.get(name):
                scene[name] = relative_file(scene[name])
        if scene.get("ui_assets"):
            scene["ui_assets"] = [relative_file(value) for value in scene["ui_assets"]]
    portable = ROOT / "render/timed-scenes-portable.json"
    portable.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    chosen = [ROOT / "README.md", ROOT / "verify_final_video.py", portable]
    patterns = {
        "script": ["*.json", "*.md", "*.txt"],
        "audio-ai": ["README.md", "audio-manifest.json", "generate_ai_narration.py", "scene-??.mp3", "narration-full.wav", "narration-full.mp3", "wav/scene-??.wav"],
        "render": ["render_presentation.py", "assemble_timed_scenes.py", "README.md", "final-frames/scene-??.png", "final-frames/contact-sheet.png"],
        "assets": ["*.png", "realflow.webm", "capture-manifest.json", "capture_ui.py", "execution-evidence.json", "results.csv"],
        "qa": ["*.json", "*.md", "*.txt", "*.jpg"],
    }
    for folder, globs in patterns.items():
        for pattern in globs:
            chosen.extend((ROOT / folder).glob(pattern))
    chosen = sorted(set(path for path in chosen if path.is_file()))
    forbidden = {".env", ".env.local"}
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in chosen:
            rel = path.relative_to(ROOT)
            if path.name in forbidden or "packages" in rel.parts:
                raise SystemExit(f"Refusing to include a credential or cache file: {rel}")
            archive.write(path, Path("Probaho-presentation") / rel)
    with zipfile.ZipFile(OUTPUT) as archive:
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"Archive verification failed: {bad}")
    print(json.dumps({"output": str(OUTPUT), "files": len(chosen), "bytes": OUTPUT.stat().st_size, "duration_seconds": payload["target_seconds"]}))


if __name__ == "__main__":
    main()
