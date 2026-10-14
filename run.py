"""Run the Tideway local sandbox (Python 3.11+, standard library only)."""
import argparse
import os
import sys
from pathlib import Path

from tideway.server import serve

ROOT = Path(__file__).resolve().parent


def load_env():
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() in ("OPENAI_API_KEY", "OPENAI_MODEL", "TIDEWAY_PORT"):
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("Tideway needs Python 3.11 or newer.")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    parser = argparse.ArgumentParser(description="Tideway: approval-gated cash-flow rescue (synthetic sandbox)")
    parser.add_argument("--port", type=int, default=int(os.getenv("TIDEWAY_PORT", "8787")))
    parser.add_argument("--db", default=str(ROOT / "data" / "tideway.sqlite3"))
    parser.add_argument("--no-demo", action="store_true", help="Start without the synthetic demo businesses")
    args = parser.parse_args()
    serve(args.db, args.port, os.getenv("OPENAI_API_KEY", "").strip(), os.getenv("OPENAI_MODEL", "gpt-5-mini"), not args.no_demo)
