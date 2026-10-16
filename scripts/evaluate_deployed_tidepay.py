"""Evaluate exact shipped TidePay weights on untouched synthetic SME cohorts."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tideway.ml.deployed_evaluation import DEFAULTS, run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/readiness-v3/tidepay")
    parser.add_argument("--businesses-per-seed", type=int, default=DEFAULTS["businesses_per_seed"])
    parser.add_argument("--bootstrap", type=int, default=DEFAULTS["bootstrap_repetitions"])
    args = parser.parse_args()
    if args.businesses_per_seed < 2 or args.bootstrap < 0:
        parser.error("businesses-per-seed >= 2 and bootstrap >= 0 required")
    report = run(args.out, {"businesses_per_seed": args.businesses_per_seed,
                            "bootstrap_repetitions": args.bootstrap})
    print(json.dumps({"output": str(args.out), "balance": report["balance"], "results": report["results"],
                      "deployed_sha256": report["artifacts"]["deployed"]["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
