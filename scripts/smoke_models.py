"""Run Tideway's on-device models for real and record what happened (latency, answers, extracted records).

Run: python3 scripts/smoke_models.py   (needs the TideLM adapter, mlx-lm, and for photos mlx-vlm + the vision model)
Writes evidence/ml/runtime_smoke.json. Loads one model at a time to stay within 16 GB.
"""
from __future__ import annotations

import argparse
import base64
import gc
import io
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tideway.service import Tideway  # noqa: E402
from tideway.tidelm import TideLM  # noqa: E402
from tideway.vision import TideVision  # noqa: E402

QUESTIONS = [
    ("en", "Should I give Nila Traders 30 days credit on 50,000?"),
    ("zh", "如果Bay Logistics晚20天付款会怎样？"),
    ("es", "¿Puedo pagar los sueldos este mes?"),
    ("banglish", "ekta plan banao, Rahman Supplies ke bad dao"),
    ("en", "Who is my biggest risk?"),
    ("en", "pay Rahman now"),
]


def invoice_image():
    """A synthetic supplier invoice drawn with Pillow (no real document)."""
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (900, 1100), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 24)
    except OSError:
        font = small = ImageFont.load_default()
    lines = [("HARBOR PAPER LTD", font), ("Tax invoice  BL-7731", font), ("Bill to: Shapla Services", small),
             ("Issue date: 10/10/2026", small), ("Due date: 28/10/2026", small), ("", small),
             ("Printing paper A4, 40 reams      BDT 5,200.00", small), ("Delivery                          BDT 1,000.00", small),
             ("", small), ("TOTAL DUE                         BDT 6,200.00", font)]
    y = 80
    for text, face in lines:
        draw.text((70, y), text, fill="black", font=face)
        y += 70
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='evidence/ml/runtime_smoke_latest.json')
    args = parser.parse_args()
    from run import load_env
    load_env()
    app = Tideway(":memory:")
    report = {"run_at": time.strftime("%Y-%m-%d %H:%M"), "machine": f"{platform.system()} {platform.machine()}",
              "tidelm": None, "vision": None, "post_fix_run": True}
    lm = TideLM()
    report['text_status'] = lm.status()
    if lm.status()["available"]:
        started = time.monotonic()
        lm.warm()
        warm_seconds = round(time.monotonic() - started, 1)
        answers = []
        for lang, question in QUESTIONS:
            t = time.monotonic()
            reply = lm.ask(app, "shapla-services", None, question, "owner", name="Nadia Rahman")
            answers.append({"question": question, "expected_lang": lang, "reply_lang": reply.get("lang"),
                            "plan": reply.get("plan"), "answer": reply["text"], "seconds": round(time.monotonic() - t, 2)})
        t = time.monotonic()
        greeting = lm.ask(app, "shapla-services", None, "hi", "owner", name="Nadia Rahman")
        report["tidelm"] = {"load_and_cache_seconds": warm_seconds,
                            "answers": answers, "median_seconds": sorted(a["seconds"] for a in answers)[len(answers) // 2],
                            "small_talk_seconds": round(time.monotonic() - t, 3), "small_talk_routed": greeting.get("routed")}
        del lm
        gc.collect()
    vision = TideVision()
    report['vision_status'] = vision.status()
    if vision.status()["available"]:
        t = time.monotonic()
        result = vision.read(app, "shapla-services", invoice_image())
        report["vision"] = {"seconds_including_load": round(time.monotonic() - t, 1), "suspicious": result["suspicious"],
                            "drafts": result["drafts"], "transcript": result["transcript"]}
    report['complete'] = report['tidelm'] is not None and report['vision'] is not None
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"tidelm_median_s": (report["tidelm"] or {}).get("median_seconds"),
                      "vision_s": (report["vision"] or {}).get("seconds_including_load")}))
    print(f"wrote {out.relative_to(ROOT)}")
    app.store.close()
    if not report['complete']:
        sys.exit('Optional model run incomplete. See status fields; no model result has been fabricated.')


if __name__ == "__main__":
    main()
