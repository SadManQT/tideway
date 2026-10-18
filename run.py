"""Run the Tideway local sandbox (Python 3.11+, standard library only)."""
import argparse
import errno
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
                if key.strip() in ("OPENAI_API_KEY", "OPENAI_MODEL", "TIDEWAY_HOST", "TIDEWAY_PORT",
                                   "TIDEWAY_LOCAL_MODEL_URL", "TIDEWAY_LOCAL_TEXT_MODEL", "TIDEWAY_LOCAL_VISION_MODEL",
                                   "TIDEWAY_LOCAL_STRUCTURED_PLANS", "TIDEWAY_SEMANTIC_SCREENING", "TIDEWAY_DECISION_LAB"):
                    os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


if __name__ == "__main__":
    if sys.version_info < (3, 11):
        sys.exit("Tideway needs Python 3.11 or newer.")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    parser = argparse.ArgumentParser(description="Tideway: approval-gated cash-flow rescue (synthetic sandbox)")
    parser.add_argument("--host", default=os.getenv("TIDEWAY_HOST", "127.0.0.1"),
                        help="Bind address (loopback by default; Docker uses 0.0.0.0 behind a local port mapping)")
    parser.add_argument("--port", type=int, default=int(os.getenv("TIDEWAY_PORT", "8787")))
    parser.add_argument("--db", default=str(ROOT / "data" / "tideway.sqlite3"))
    parser.add_argument("--no-demo", action="store_true", help="Start without the synthetic demo businesses")
    args = parser.parse_args()
    try:
        serve(args.db, args.port, os.getenv("OPENAI_API_KEY", "").strip(), os.getenv("OPENAI_MODEL", "gpt-5-mini"),
              not args.no_demo, args.host)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        sys.exit(f"Port {args.port} is already in use, probably by another Tideway still running.\n"
                 f"Stop it with Ctrl+C in its terminal, or start this one on another port:\n"
                 f"  python3 run.py --port {args.port + 1}")
