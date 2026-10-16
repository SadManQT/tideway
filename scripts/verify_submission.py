"""Run the offline suite and preserve actual counts, environment and source hashes."""
from __future__ import annotations

import contextlib
import hashlib
import json
import platform
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def source_digest(source_root=None):
    """Hash runtime/test sources, optionally in an extracted release tree."""
    root = Path(source_root) if source_root is not None else ROOT
    paths = [root / "run.py"]
    workflow = root / ".github/workflows/ci.yml"
    if workflow.is_file():
        paths.append(workflow)
    for folder in ("tideway", "tests", "web", "scripts"):
        paths.extend(p for p in (root / folder).rglob("*") if p.suffix in (".py", ".js", ".mjs", ".css", ".html", ".json")
                     and "__pycache__" not in p.parts)
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), hashes


def base_commit():
    """A source ZIP must remain testable without Git or a .git directory."""
    if not (ROOT / ".git").exists():
        return None
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main():
    out = ROOT / "evidence"
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (out / "test-run.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stderr(log), contextlib.redirect_stdout(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    digest, files = source_digest()
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "python": platform.python_version(), "platform": platform.system(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "passed": result.wasSuccessful(),
              "seconds": round(time.monotonic() - started, 2),
              "base_commit": base_commit(),
              "source_tree_sha256": digest, "source_files": files,
              "model_inference_tested": False,
              "note": "Counts include offline tests with injected model outputs; this is not a real-model benchmark."}
    (out / "test-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{result.testsRun} tests: {len(result.failures)} failures, {len(result.errors)} errors, {len(result.skipped)} skipped.")
    if not result.wasSuccessful():
        print((out / "test-run.log").read_text(encoding="utf-8")[-10000:])
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
