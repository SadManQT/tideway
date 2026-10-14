"""Download Tideway's trained TideLM adapter from the GitHub release and verify it.

Run: python3 scripts/get_tidelm.py   (then: pip install mlx-lm, Apple Silicon only)
"""
import hashlib
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

RELEASE = "https://github.com/SadManQT/tideway/releases/download/tidelm-v1/"
FILES = {"adapters.safetensors": "9980aa8e251dd3dff9dd83cbb36fb38ad18fac6e4b9f34023e4514d1cd65aefd",
         "adapter_config.json": "a1cd14355f2302011eb720f7a96bc228a4f8c6dd64ae01c8fcc962c1782e6c9e"}
TARGET = Path(__file__).resolve().parent.parent / "models" / "tidelm-adapter"


def fetch(url):
    """HTTPS with certificate checks always on.  python.org builds on macOS ship without CA certificates,
    so use certifi's bundle when it is installed, and otherwise explain the one-time fix."""
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    try:
        return urllib.request.urlopen(url, timeout=120, context=context).read()
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            sys.exit("HTTPS certificate check failed. Run 'pip install certifi' (or, for python.org Python on macOS, "
                     "'Install Certificates.command' in the Python folder) and try again.")
        raise


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        path = TARGET / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            print(f"{name}: already present and verified")
            continue
        print(f"downloading {name} ...")
        data = fetch(RELEASE + name)
        if hashlib.sha256(data).hexdigest() != expected:
            sys.exit(f"{name}: checksum mismatch; refusing to install it.")
        path.write_bytes(data)
        print(f"{name}: verified (sha256 {expected[:12]}...)")
    print(f"TideLM adapter ready in {TARGET}")


if __name__ == "__main__":
    main()
