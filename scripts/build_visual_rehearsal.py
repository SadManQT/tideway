"""Create a draft visual rehearsal video from isolated app screenshots.

This is intentionally labelled a visual rehearsal, not live-execution proof:
the final competition demo should be re-recorded as a narrated running-app
session by the team.
"""
from __future__ import annotations

from pathlib import Path

import cv2


ROOT = Path(__file__).resolve().parents[1]
FRAMES = [
    ("overview-desktop.png", "Probaho · Shapla Services · synthetic cash-gap overview"),
    ("plan-approval.png", "Review the supplier-reschedule plan · human approval and consent gate"),
    ("execution-receipt.png", "Synthetic sandbox receipt · before/after state · post-commit read-back"),
    ("records-import.png", "Business-scoped records · atomic combined import · escaped record text"),
    ("assistant-demo.png", "Local demo assistant · reads and proposes, never approves or executes"),
]


def main():
    evidence = ROOT / "evidence"
    destination = ROOT / "demo" / "demo.mp4"
    images = [(evidence / name, label) for name, label in FRAMES if (evidence / name).is_file()]
    if not images:
        raise SystemExit("No generated browser screenshots found; run python tests/browser_check.py first.")
    first = cv2.imread(str(images[0][0]))
    if first is None:
        raise SystemExit(f"Could not read {images[0][0]}")
    height, width = first.shape[:2]
    # mp4v is available in the installed OpenCV build without a system ffmpeg.
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), 1.0, (width, height))
    if not writer.isOpened():
        raise SystemExit("OpenCV could not open an MP4 writer on this machine.")
    try:
        for image_path, label in images:
            frame = cv2.imread(str(image_path))
            if frame is None:
                continue
            if frame.shape[:2] != (height, width):
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, height - 86), (width, height), (21, 61, 54), -1)
            frame = cv2.addWeighted(overlay, 0.88, frame, 0.12, 0)
            cv2.putText(frame, label, (34, height - 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (196, 239, 156), 2, cv2.LINE_AA)
            # Hold each real captured state for three seconds so it is usable
            # as a rehearsal storyboard without pretending to be live proof.
            for _ in range(3):
                writer.write(frame)
    finally:
        writer.release()
    print(f"Wrote draft visual rehearsal: {destination}")


if __name__ == "__main__":
    main()
