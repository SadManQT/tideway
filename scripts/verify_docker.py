"""Build and exercise a frozen source tree in Docker without publishing ports.

Uses the image's ordinary CMD as its non-root user. HTTP runs over container
loopback with docker exec, so this also works with an isolated private daemon.
Only uniquely named verification containers/volumes created here are removed.
No registry push, live money, model download or submission is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_submission import line_ending_issues, source_digest  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docker-cli", default="docker", help="Docker executable path")
    parser.add_argument("--docker-host", help="Explicit daemon endpoint, e.g. unix:///path/engine.sock")
    parser.add_argument("--legacy-builder", action="store_true", help="Use DOCKER_BUILDKIT=0 when buildx is unavailable")
    parser.add_argument("--out", type=Path, default=ROOT / "evidence/infrastructure-v5/docker")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    issues = line_ending_issues()
    if issues:
        parser.exit(1, "Source must satisfy tracked LF policy: " + ", ".join(issues) + "\n")
    before, files_before = source_digest()
    token = uuid.uuid4().hex[:12]
    image = f"tideway-verification:{token}"
    volume = f"tideway-verification-data-{token}"
    names = [f"tideway-verification-{token}-{suffix}" for suffix in ("initial", "recreated")]
    prefix = [args.docker_cli] + (["--host", args.docker_host] if args.docker_host else [])
    environment = os.environ.copy()
    if args.legacy_builder:
        environment["DOCKER_BUILDKIT"] = "0"
    commands, containers = [], []
    created_volume = False
    report = {"version": "docker-local-verification-v5", "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "host_python": platform.python_version(), "host_platform": platform.platform(),
              "source_tree_sha256_before": before, "source_files_before": files_before,
              "legacy_builder": args.legacy_builder, "image_tag": image, "passed": False,
              "checks": {}, "commands": commands,
              "scope": "Local Linux container build and HTTP on its isolated loopback through docker exec. No ordinary bridge, host-port publication, hosted CI, native MLX or production deployment tested."}

    def docker(stage, arguments, *, timeout=180, required=True):
        command = prefix + arguments
        start = time.perf_counter()
        try:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=timeout)
            raw, exit_code = result.stdout, result.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            raw = f"{type(exc).__name__}: {exc}\n".encode("utf-8")
            exit_code = -1
            if isinstance(exc, subprocess.TimeoutExpired) and exc.stdout:
                raw += exc.stdout if isinstance(exc.stdout, bytes) else exc.stdout.encode("utf-8")
        # Docker's progress UI may emit carriage returns; evidence is tracked
        # under the repository's LF policy so hashes remain portable.
        (out / f"{stage}.log").write_bytes(raw.replace(b"\r", b""))
        commands.append({"stage": stage, "arguments": arguments, "exit_code": exit_code,
                         "seconds": round(time.perf_counter() - start, 3), "log": f"{stage}.log"})
        if required and exit_code:
            raise RuntimeError(f"Docker {stage} failed with exit {exit_code}; see {out / (stage + '.log')}")
        return raw.decode("utf-8", errors="replace")

    def frozen(stage):
        if source_digest()[0] != before:
            raise RuntimeError(f"Source changed during {stage}; repeat Docker verification after all source edits stop")

    try:
        version = json.loads(docker("engine-version", ["version", "--format", "{{json .}}"], timeout=30))
        report["docker"] = {"client_version": version["Client"]["Version"], "server_version": version["Server"]["Version"],
                            "server_os": version["Server"]["Os"], "server_arch": version["Server"]["Arch"]}
        base = re.search(r"^FROM\s+(\S+)", (ROOT / "Dockerfile").read_text(encoding="utf-8"), re.MULTILINE).group(1)
        report["base_image_reference"] = base
        docker("base-pull", ["pull", base], timeout=300)
        base_inspect = json.loads(docker("base-inspect", ["image", "inspect", base]))[0]
        report["base_image"] = {key: base_inspect.get(key) for key in ("Id", "RepoDigests", "Created", "Architecture", "Os")}
        frozen("base pull")
        # No cache ensures this run really executes the complete build-time
        # suite rather than inheriting a previous build's test layer.
        docker("build", ["build", "--network", "none", "--no-cache", "--tag", image, "."], timeout=900)
        frozen("image build")
        inspect = json.loads(docker("image-inspect", ["image", "inspect", image]))[0]
        report["image"] = {key: inspect.get(key) for key in ("Id", "Created", "Architecture", "Os", "Size")}
        report["image"]["user"] = inspect["Config"]["User"]
        report["image"]["cmd"] = inspect["Config"]["Cmd"]
        assert inspect["Config"]["User"] == "tideway", "Image lost its non-root runtime user"
        docker("volume-create", ["volume", "create", volume])
        created_volume = True
        for index, (name, phase) in enumerate(zip(names, ("workflow", "persisted"))):
            docker(f"run-{phase}", ["run", "--detach", "--name", name, "--network", "none",
                                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
                                    "--mount", f"type=volume,source={volume},target=/app/data", image])
            containers.append(name)
            raw = docker(f"http-{phase}", ["exec", name, "python", "-S", "scripts/container_http_smoke.py", "--phase", phase], timeout=180)
            smoke = json.loads(raw)
            assert smoke["passed"], f"HTTP {phase} check reported a failure"
            report["checks"][f"http_{phase}"] = smoke
            if index == 0:
                counts = json.loads(docker("build-test-summary", ["exec", name, "cat", "/app/evidence/test-summary.json"]))
                assert counts["passed"] and counts["source_tree_sha256"] == before, "Build tests did not attest to the current source tree"
                report["build_tests"] = counts
                docker("build-test-log", ["exec", name, "cat", "/app/evidence/test-run.log"])
            docker(f"server-log-{phase}", ["logs", name])
            docker(f"stop-{phase}", ["stop", "--timeout", "10", name])
            docker(f"remove-{phase}", ["rm", name])
            containers.remove(name)
            frozen(f"HTTP {phase}")
        report["checks"]["normal_cmd_startup"] = True
        report["checks"]["named_volume_survives_container_recreation"] = True
        report["checks"]["non_root_and_no_privilege_escalation"] = True
        report["checks"]["no_published_host_ports"] = True
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(report["error"], file=sys.stderr, flush=True)
    finally:
        cleanup_start = len(commands)
        for name in containers:
            docker(f"failure-server-log-{name.rsplit('-', 1)[-1]}", ["logs", name], required=False)
            docker(f"cleanup-container-{name.rsplit('-', 1)[-1]}", ["rm", "--force", name], required=False)
        if created_volume:
            docker("cleanup-volume", ["volume", "rm", volume], required=False)
        cleanup_failures = [entry["stage"] for entry in commands[cleanup_start:]
                            if entry["stage"].startswith("cleanup-") and entry["exit_code"] != 0]
        report["cleanup_failures"] = cleanup_failures
        if cleanup_failures:
            report["passed"] = False
        # Keep the uniquely tagged, tested image for inspection. No image prune
        # or cleanup of any unrelated resource is performed.
        after, files_after = source_digest()
        report.update(source_tree_sha256_after=after, source_unchanged=before == after,
                      finished_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if before != after:
            report["passed"] = False
        report["source_files_after"] = files_after
        (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in out.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
        (out / "SHA256SUMS.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Docker verification {'passed' if report['passed'] else 'failed'} -> {out / 'report.json'}", flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
