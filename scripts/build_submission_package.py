"""Build a local, integrity-checked source/deliverable ZIP. Never push or submit."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_submission import source_digest  # noqa: E402

EXCLUDED_ROOTS = {".git", ".aws", ".agents", ".codex", ".claude", ".opencode", ".vscode",
                  ".venv", "venv", "node_modules", "data", "models", "tmp", "dist", "demo", "personal-prep"}
RELEASE_FOLDERS = {"tideway", "web", "scripts", "tests", "docs", "slides", "evidence", "licenses", "examples"}
RELEASE_CONFIG_FILES = {".github/workflows/ci.yml"}
RELEASE_ROOT_FILES = {"README.md", "LICENSE", "THIRD_PARTY_NOTICES", "Makefile", "Dockerfile", ".dockerignore",
                      ".gitignore", ".gitattributes", ".python-version", ".env.example", "requirements.txt",
                      "requirements.lock", "requirements-evaluation.txt", "run.py", "start.cmd", "start.ps1",
                      "submission-team.example.json", "submission-team.public.json"}
PRIVATE_COMPONENTS = {name.casefold() for name in EXCLUDED_ROOTS} | {
    "__pycache__", ".ds_store", "submission-team.json", "private", ".private", "secrets", "credentials",
    ".ssh", ".gnupg", "identity-documents", "passports"}
PRIVATE_SUFFIXES = {".pyc", ".pyo", ".zip", ".sqlite", ".sqlite3", ".db", ".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
PRIVATE_NAMES = re.compile(r"(?:passport|national[-_ ]?id|identity[-_ ]?document|private[-_ ]?(?:team|contact|roster)|credentials|secrets)", re.I)


def allowed_source(name):
    if not isinstance(name, str) or "\\" in name or any(ord(c) < 32 for c in name):
        return False
    p = PurePosixPath(name)
    if p.name.casefold() in {"guide.html", "guide.css", "guide.js", "23-guide-mobile.png", "24-guide-desktop.png"}:
        return False
    if (p.is_absolute() or ".." in p.parts or not p.parts or p.as_posix() != name
            or any(":" in part for part in p.parts) or p.parts[0] in EXCLUDED_ROOTS):
        return False
    if name in RELEASE_CONFIG_FILES:
        return True
    if p.parts[0] not in RELEASE_FOLDERS and name not in RELEASE_ROOT_FILES:
        return False
    if any(part.casefold() in PRIVATE_COMPONENTS for part in p.parts) or p.suffix.casefold() in PRIVATE_SUFFIXES:
        return False
    if any(PRIVATE_NAMES.search(part) for part in p.parts):
        return False
    if any(part.casefold().startswith("submission-team") for part in p.parts) and name not in {
        "submission-team.example.json", "submission-team.public.json"}:
        return False
    if any(part.startswith(".") for part in p.parts) and name not in RELEASE_ROOT_FILES:
        return False
    return not any(part.casefold().startswith(".env") and part != ".env.example" for part in p.parts)


def source_file(root, name):
    """Never follow a file or directory symlink into private workstation state."""
    if not allowed_source(name):
        return None
    root = root.resolve()
    path = root / name
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root and parent.is_relative_to(root)):
        return None
    return path if path.is_file() and path.resolve().is_relative_to(root) else None


def team_gaps(team):
    gaps = []
    if not team.get("team_name"):
        gaps.append("Team name")
    if not team.get("leader"):
        gaps.append("Team leader")
    if not 2 <= len(team.get("members", [])) <= 5:
        gaps.append("Roster of 2-5 members")
    if any(not member.get("role") for member in team.get("members", [])):
        gaps.append("Team roles")
    for field, label in (("registration_confirmed", "Registration confirmation"),
                         ("submission_route_confirmed", "Submission route"),
                         ("eligibility_confirmed", "Eligibility confirmation"),
                         ("reviewer_access_confirmed", "Reviewer access to final source version")):
        if not team.get(field):
            gaps.append(label)
    return gaps


def main():
    test = json.loads((ROOT / "evidence/test-summary.json").read_text(encoding="utf-8"))
    digest, _ = source_digest()
    if not test["passed"] or test["source_tree_sha256"] != digest:
        sys.exit("Source changed or tests failed. Run python scripts/verify_submission.py before packaging.")
    browser = json.loads((ROOT / "evidence/screens/browser-verification.json").read_text(encoding="utf-8"))
    if not browser.get("passed") or browser.get("source_tree_sha256") != digest:
        sys.exit("A passing browser report for the current source is required before packaging.")
    team_path = ROOT / "submission-team.public.json"
    team = json.loads(team_path.read_text(encoding="utf-8")) if team_path.is_file() else {}
    gaps = team_gaps(team)
    gaps.append("Demo video explicitly deferred by the team; add before sending or clarify evidence requirement")
    gaps.append("Native MLX/TideLM adapter and receipt-model device verification (compatible Qwen3 inference is separate)")
    gaps.append("Consented SME feedback, stronger unseen instruction screening and independent security review")
    if (ROOT / ".git").exists():
        names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                        cwd=ROOT).decode("utf-8").split("\0")
    else:
        names = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()]
    entries = {}
    for name in sorted(set(filter(None, names))):
        path = source_file(ROOT, name)
        if path is not None:
            entries["Tideway/source/" + name] = path.read_bytes()
    for name in ("slides/pitch.pdf", "docs/architecture.pdf", "docs/security-assessment.pdf",
                 "docs/submission-notes.pdf", "docs/MODEL_CARD.md", "docs/SETUP_WINDOWS_MAC.md"):
        path = source_file(ROOT, name)
        if path is None:
            sys.exit(f"Deliverable missing or symlinked: {name}")
        entries["Tideway/deliverables/" + Path(name).name] = path.read_bytes()
    intro = ("# Tideway - The Last BrainCell\n\n"
             "Start with deliverables/submission-notes.pdf. Run `python run.py` inside source/.\n"
             "This is a local review package. It has not been pushed or submitted.\n"
             f"Validated source tree SHA-256: {digest}\n\n"
             "## Team-controlled outstanding items\n\n" + "\n".join("- " + gap for gap in gaps) + "\n")
    entries["Tideway/README-FIRST.md"] = intro.encode("utf-8")
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "base_commit": test["base_commit"], "includes_local_uncommitted_changes": True,
                "source_tree_sha256": digest, "tests_run": test["tests_run"],
                "technical_checks_passed": True, "submitted": False,
                "readiness": "technical package prepared; team-controlled steps outstanding",
                "outstanding": gaps,
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(entries.items())}}
    entries["Tideway/package-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / "Tideway-submission.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for name, data in sorted(entries.items()):
            zipped.writestr(name, data)
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
        for name, expected in manifest["files"].items():
            if hashlib.sha256(zipped.read(name)).hexdigest() != expected["sha256"]:
                raise RuntimeError(f"ZIP round-trip mismatch: {name}")
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS.txt").write_text(f"{sha}  {archive.name}\n", encoding="utf-8")
    (output / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(entries)} ZIP entries, {archive.stat().st_size:,} bytes -> {archive.relative_to(ROOT)}")
    print(f"SHA-256 {sha}")
    print("Outstanding: " + "; ".join(gaps))


if __name__ == "__main__":
    main()
