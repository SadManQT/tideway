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


def source_paths(source_root=None):
    """The exact source set shared by tests, browser stamps and package checks."""
    root = Path(source_root) if source_root is not None else ROOT
    paths = [root / "run.py"]
    for name in (".github/workflows/ci.yml", "Dockerfile", ".dockerignore"):
        config = root / name
        if config.is_file():
            paths.append(config)
    for folder in ("tideway", "tests", "web", "scripts"):
        paths.extend(p for p in (root / folder).rglob("*") if p.suffix in (".py", ".js", ".mjs", ".css", ".html", ".json", ".svg")
                     and "__pycache__" not in p.parts)
    return sorted(paths)


def line_ending_issues(source_root=None):
    """Detect bytes that contradict tracked LF source policy; never alter hashes."""
    root = Path(source_root) if source_root is not None else ROOT
    return [p.relative_to(root).as_posix() for p in source_paths(root) if b"\r" in p.read_bytes()]


def source_digest(source_root=None):
    """Hash actual bytes, including line endings; no normalized-hash shortcut."""
    root = Path(source_root) if source_root is not None else ROOT
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths(root)}
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
    out.mkdir(parents=True, exist_ok=True)
    before_digest, _ = source_digest()
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    with (out / "test-run.log").open("w", encoding="utf-8") as log:
        with contextlib.redirect_stderr(log), contextlib.redirect_stdout(log):
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    digest, files = source_digest()
    report = {"run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "python": platform.python_version(), "platform": platform.system(),
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skipped": len(result.skipped), "passed": result.wasSuccessful() and before_digest == digest,
              "source_unchanged_during_tests": before_digest == digest,
              "seconds": round(time.monotonic() - started, 2),
              "base_commit": base_commit(),
              "source_tree_sha256": digest, "source_files": files,
              "model_inference_tested": False,
              "note": "Counts include offline tests with injected model outputs; this is not a real-model benchmark."}
    (out / "test-summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{result.testsRun} tests: {len(result.failures)} failures, {len(result.errors)} errors, {len(result.skipped)} skipped.")
    if not result.wasSuccessful():
        print((out / "test-run.log").read_text(encoding="utf-8")[-10000:])
    if before_digest != digest:
        print("Source changed during tests. Restart verification after edits are complete.")
    return 0 if report['passed'] else 1


if __name__ == "__main__":
    sys.exit(main())
