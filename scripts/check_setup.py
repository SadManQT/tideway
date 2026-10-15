"""Report core setup and optional model availability without installing anything."""
from pathlib import Path
import json
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from run import load_env  # noqa: E402
from tideway.tidelm import TideLM  # noqa: E402
from tideway.vision import TideVision  # noqa: E402


def main():
    load_env()
    report = {"platform": platform.system(), "architecture": platform.machine(),
              "python": platform.python_version(), "core_ready": sys.version_info >= (3, 11),
              "text_model": TideLM().status(), "vision_model": TideVision().status(),
              "note": "Optional model unavailability does not prevent the core offline sandbox from running."}
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["core_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
