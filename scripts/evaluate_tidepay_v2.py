"""Reproduce audited TidePay v2; stdlib only, no production model overwrite."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tideway.ml.evaluation_v2 import DEFAULTS, run  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/upgrade-v1/tidepay")
    parser.add_argument("--seed", type=int, default=DEFAULTS["seed"])
    parser.add_argument("--rounds", type=int, default=DEFAULTS["rounds"])
    parser.add_argument("--businesses", type=int, default=DEFAULTS["businesses"])
    parser.add_argument("--bootstrap", type=int, default=DEFAULTS["bootstrap_repetitions"])
    args = parser.parse_args()
    if args.rounds < 1 or args.businesses < 2 or args.bootstrap < 0:
        parser.error("rounds >= 1, businesses >= 2, bootstrap >= 0 required")
    report = run(args.out, {"seed": args.seed, "rounds": args.rounds, "businesses": args.businesses,
                            "bootstrap_repetitions": args.bootstrap})
    print(json.dumps({"output": str(args.out), "balance": report["balance"], "results": report["results"],
                      "elapsed_seconds": report["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
