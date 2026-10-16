"""Provision a checksum-pinned optional local text model; never changes app defaults.

Run --download once, then --serve in a separate terminal. Weights and native
runtime stay in ignored models/ by default; --cache-dir can use another drive.
The compatible models are not the TideLM adapter.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "models" / "local-demo"
MODEL_ID = "Qwen2.5-1.5B-Instruct-Q4_K_M"
MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_REVISION = "91cad51170dc346986eccefdc2dd33a9da36ead9"
MODEL_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL_BYTES = 1117320736
MODEL_URL = f"https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/{MODEL_REVISION}/{MODEL_FILE}"
MODEL_PROFILES = {
    "compact": {"id": MODEL_ID, "file": MODEL_FILE, "revision": MODEL_REVISION,
                "sha256": MODEL_SHA256, "bytes": MODEL_BYTES, "url": MODEL_URL},
    "qwen3-4b": {"id": "Qwen3-4B-Instruct-2507-Q4_K_M", "file": "Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
                 "revision": "a06e946bb6b655725eafa393f4a9745d460374c9",
                 "sha256": "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597",
                 "bytes": 2497281120,
                 "url": "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/"
                        "a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"},
}
RUNTIME_RELEASE = "b11678"
RUNTIMES = {
    "windows-vulkan": ("llama-b11678-bin-win-vulkan-x64.zip", 32210140,
                       "dad3ea8140d26a821ba113ad6e8cad13cc00065f995ce08bf3481c8f041d0e70"),
    "windows-cpu": ("llama-b11678-bin-win-cpu-x64.zip", 19565396,
                    "77e01fadbc1f308a179c9f931b1c23f897435b81eccd4c03aed3906a16b16ed8"),
    "macos-arm64": ("llama-b11678-bin-macos-arm64.tar.gz", 12220354,
                    "81c98d485d430272895ed216ffd5537b400a36519e9da1fa412c5dbb3d1e0f4c"),
    "macos-x64": ("llama-b11678-bin-macos-x64.tar.gz", 11703204,
                  "14745f135481637b21f5b751a5831ab51cdd12c4db2465ca81ddd671cdb33a52"),
}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def runtime_key(cpu=False):
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows" and machine in {"amd64", "x86_64"}:
        return "windows-cpu" if cpu else "windows-vulkan"
    if system == "Darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        if machine in {"x86_64", "amd64"}:
            return "macos-x64"
    raise RuntimeError("This optional helper supports Windows x64 and macOS. Use your own trusted local server elsewhere.")


def fetch(url, target, expected_size, expected_sha):
    target = Path(target)
    partial = target.with_name(target.name + ".partial")
    if target.is_symlink() or partial.is_symlink():
        raise RuntimeError("Refusing a symlinked download or partial file.")
    if target.is_file() and target.stat().st_size == expected_size and digest(target) == expected_sha:
        print(f"Verified cached {target.name}", flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(target.parent).free < expected_size + 512 * 1024 * 1024:
        raise RuntimeError("Insufficient disk space: download needs its size plus 512 MiB free headroom.")
    sha, size, announced = hashlib.sha256(), 0, 0
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Tideway-local-demo"})
        with urllib.request.urlopen(request, timeout=45) as response, partial.open("wb") as output:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                size += len(chunk)
                if size > expected_size:
                    raise RuntimeError("Download exceeds the pinned artifact size.")
                output.write(chunk)
                sha.update(chunk)
                if size - announced >= 64 * 1024 * 1024:
                    print(f"{target.name}: {size // 1048576}/{expected_size // 1048576} MiB", flush=True)
                    announced = size
        if size != expected_size or sha.hexdigest() != expected_sha:
            raise RuntimeError(f"Checksum or size mismatch for {target.name}; artifact was not installed.")
        os.replace(partial, target)
        print(f"Verified {target.name} SHA-256 {expected_sha}", flush=True)
    finally:
        if partial.exists():
            partial.unlink()


def extract_runtime(archive, destination):
    """Reject traversal and links escaping the private runtime directory."""
    archive, destination = Path(archive), Path(destination)
    if destination.is_symlink():
        raise RuntimeError("Runtime destination must not be a symbolic link.")
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    def validate_names(names):
        seen = set()
        for name in names:
            p = PurePosixPath(name)
            # Case collisions are ambiguous across the supported filesystems.
            normalized = name.rstrip("/")
            if (not normalized or p.is_absolute() or ".." in p.parts or "\\" in name
                    or p.as_posix() != normalized or any(":" in part for part in p.parts)
                    or any(ord(character) < 32 for character in name)
                    or normalized.casefold() in seen
                    or not (root / name).resolve().is_relative_to(root)):
                raise RuntimeError("Unsafe or ambiguous runtime archive entry.")
            seen.add(normalized.casefold())

    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if sum(item.file_size for item in entries) > 256 * 1024 * 1024 or len(entries) > 1000:
                raise RuntimeError("Runtime archive exceeds extraction limits.")
            # ZipInfo normalizes native separators on Windows and truncates
            # embedded NULs; validate the original archive spelling as well.
            validate_names(item.orig_filename for item in entries)
            for item in entries:
                if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                    raise RuntimeError("Unsafe runtime archive entry.")
            zipped.extractall(root)
    else:
        with tarfile.open(archive, "r:gz") as packed:
            entries = packed.getmembers()
            if sum(item.size for item in entries) > 256 * 1024 * 1024 or len(entries) > 1000:
                raise RuntimeError("Runtime archive exceeds extraction limits.")
            validate_names(item.name for item in entries)
            # Use the hardened filter, including internal-link validation. It is
            # available in the documented Python 3.11.11+ setup.
            if not hasattr(tarfile, "data_filter"):
                raise RuntimeError("Update Python to 3.11.11 or later for safe optional runtime extraction.")
            for item in entries:
                # Preflight every entry before writing the first file.
                try:
                    tarfile.data_filter(item, str(root))
                except tarfile.FilterError as error:
                    raise RuntimeError("Unsafe runtime archive entry.") from error
            packed.extractall(root, members=entries, filter="data")


def serve(archive, model, key, port, cpu=False, *, cache=None, model_id=MODEL_ID):
    """Launch only files from a fresh verified archive extraction.

    Reusing an old extraction can select an unrelated server or leave an edited
    DLL beside an authentic executable. Never execute from that cache tree.
    """
    cache = Path(cache) if cache is not None else CACHE
    with tempfile.TemporaryDirectory(prefix=f"{key}-serve-", dir=cache, ignore_cleanup_errors=True) as directory:
        runtime = Path(directory)
        extract_runtime(archive, runtime)
        filename = "llama-server.exe" if key.startswith("windows") else "llama-server"
        candidates = [path for path in runtime.rglob(filename) if path.is_file() and not path.is_symlink()]
        if len(candidates) != 1:
            raise RuntimeError("The verified runtime must contain exactly one server executable.")
        command = [str(candidates[0]), "-m", str(model), "--host", "127.0.0.1", "--port", str(port),
                   "--alias", model_id, "-c", "8192", "-t", "6", "-ngl", "0" if cpu else "99", "--no-webui"]
        return subprocess.call(command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Explicitly download the selected pinned model/runtime")
    parser.add_argument("--serve", action="store_true", help="Run the verified model on literal loopback; Ctrl+C stops it")
    parser.add_argument("--cpu", action="store_true", help="Use the Windows CPU runtime instead of Vulkan")
    parser.add_argument("--profile", choices=tuple(MODEL_PROFILES), default="compact",
                        help="compact: ~1.12 GB Qwen2.5 1.5B; qwen3-4b: ~2.50 GB Qwen3 4B")
    parser.add_argument("--cache-dir", type=Path, default=CACHE,
                        help="Explicit model/runtime cache directory; use another drive if space is limited")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port from 1024 to 65535.")
    key = runtime_key(args.cpu)
    cache = args.cache_dir.expanduser().resolve()
    profile = MODEL_PROFILES[args.profile]
    name, size, sha = RUNTIMES[key]
    archive, model = cache / name, cache / profile["file"]
    if args.download:
        fetch(f"https://github.com/ggml-org/llama.cpp/releases/download/{RUNTIME_RELEASE}/{name}", archive, size, sha)
        extract_runtime(archive, cache / key)
        fetch(profile["url"], model, profile["bytes"], profile["sha256"])
        provenance = "provenance.json" if args.profile == "compact" else f"provenance-{args.profile}.json"
        (cache / provenance).write_text(json.dumps({
            "profile": args.profile, "model_id": profile["id"], "model_url": profile["url"],
            "model_revision": profile["revision"], "model_bytes": profile["bytes"], "model_sha256": profile["sha256"],
            "runtime_release": RUNTIME_RELEASE, "runtime_archive": name, "runtime_archive_sha256": sha,
            "scope": "Optional compatible text model; not the TideLM adapter or a vision model."}, indent=2) + "\n", encoding="utf-8")
    if not archive.is_file() or not model.is_file():
        parser.error("Optional model/runtime not installed. Run this helper with --download first.")
    if digest(archive) != sha or model.stat().st_size != profile["bytes"] or digest(model) != profile["sha256"]:
        raise RuntimeError("Local model/runtime verification failed; rerun --download.")
    print(f"Cache: {cache}", flush=True)
    print(f"Model: {profile['id']}; optional compatible backend, not TideLM.", flush=True)
    print(f"TIDEWAY_LOCAL_MODEL_URL=http://127.0.0.1:{args.port}/v1", flush=True)
    print(f"TIDEWAY_LOCAL_TEXT_MODEL={profile['id']}", flush=True)
    if args.serve:
        return serve(archive, model, key, args.port, args.cpu, cache=cache, model_id=profile["id"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as error:
        print(f"Local model setup: {error}", file=sys.stderr)
        raise SystemExit(1)
