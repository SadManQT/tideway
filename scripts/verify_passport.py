"""Verify a Tideway credit passport offline, with the issuer's public key only.

    python scripts/verify_passport.py passport.json [--public-key HEX]

Needs only Python and tideway/ed25519.py (pure standard library). It does not
contact Tideway, so a lender can check that the passport is genuine and unaltered.
Pass --public-key with the key the business published to pin the issuer.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("tideway_ed25519", Path(__file__).resolve().parents[1] / "tideway" / "ed25519.py")
ed25519 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ed25519)


def check(document, expected_public_key=None, now=None):
    block = document.get("public_signature") if isinstance(document, dict) else None
    if not isinstance(block, dict) or block.get("alg") != "Ed25519":
        return False, "No Ed25519 public signature found."
    try:
        public, signature = bytes.fromhex(block["public_key"]), bytes.fromhex(block["signature"])
    except (KeyError, TypeError, ValueError):
        return False, "Public key or signature is not valid hex."
    if expected_public_key and public.hex() != expected_public_key.lower():
        return False, "Signed by a different key than the one you expected."
    body = {key: value for key, value in document.items() if key not in ("signature", "public_signature")}
    message = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if not ed25519.verify(public, message, signature):
        return False, "Signature does not match: the passport was altered or not signed by this key."
    try:
        expires = datetime.fromisoformat(document["expires_at"].replace("Z", "+00:00"))
    except (KeyError, AttributeError, ValueError):
        return False, "Signature valid, but the expiry date is unreadable."
    if expires <= (now or datetime.now(timezone.utc)):
        return False, f"Signature valid, but the passport expired at {document['expires_at']}."
    return True, f"Genuine and unaltered. Issuer key {block.get('key_id', public.hex()[:16])}; valid until {document['expires_at']}."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("passport", type=Path)
    parser.add_argument("--public-key", help="Expected issuer public key (64 hex characters)")
    args = parser.parse_args(argv)
    ok, message = check(json.loads(args.passport.read_text(encoding="utf-8")), args.public_key)
    print(("VALID: " if ok else "INVALID: ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
