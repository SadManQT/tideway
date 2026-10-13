"""Run the local Probaho Topic E synthetic sandbox.

Python 3.11+ is required.  Runtime code uses only the standard library.
"""
import argparse
import os
import sys
from pathlib import Path

from finmate.server import serve

ROOT = Path(__file__).resolve().parent


def load_env():
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in ("OPENAI_API_KEY", "OPENAI_MODEL", "PROBAHO_PORT", "FINMATE_PORT"):
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    parser = argparse.ArgumentParser(description="Probaho local SME cash-flow recovery sandbox")
    parser.add_argument("--port", type=int, default=int(os.getenv("PROBAHO_PORT", os.getenv("FINMATE_PORT", "8787"))))
    parser.add_argument("--db", default=str(ROOT / "data" / "probaho.sqlite3"))
    parser.add_argument("--no-demo", action="store_true", help="Start without the synthetic SME fixtures")
    args = parser.parse_args()
    serve(args.db, args.port, os.getenv("OPENAI_API_KEY", "").strip(), os.getenv("OPENAI_MODEL", "gpt-5-mini"), not args.no_demo)
