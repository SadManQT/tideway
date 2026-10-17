"""Security primitives: operator PINs, signed mandates and rate limiting.

Mandates are AP2-inspired: an approved bundle becomes a canonical JSON
document (who approved what, for which records, amounts, dates, hashes,
expiry and nonce) signed with HMAC-SHA256 under a local key that never
leaves the server.  Execution verifies the signature and every bound field
again.  HMAC is a symmetric stand-in; a production system would use
asymmetric signatures or verifiable credentials and a hardware-backed key.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path

from .domain import ValidationError, canonical_json


PIN_ITERATIONS = 120_000
MANDATE_VERSION = "tideway-mandate-v1"


def hash_pin(pin: str, salt: bytes | None = None) -> tuple[str, str]:
    if not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 12:
        raise ValidationError("PIN must contain 4-12 digits.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PIN_ITERATIONS)
    return salt.hex(), digest.hex()


def check_pin(pin, salt_hex, digest_hex) -> bool:
    if not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 12:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), PIN_ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def load_key(path) -> bytes:
    """Load a valid key or atomically publish one; never rotate an existing key."""
    if path is None:
        return secrets.token_bytes(32)
    path = Path(path)
    def read_existing():
        data = path.read_bytes()
        if len(data) != 64 or any(value not in b"0123456789abcdefABCDEF" for value in data):
            raise ValidationError("Invalid local signing key. Preserve the file and restore the original key from backup; "
                                  "automatic key replacement would invalidate existing signatures.")
        return bytes.fromhex(data.decode("ascii"))

    try:
        return read_existing()
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    # Readers must never observe a half-written key. A same-directory hard link
    # publishes the complete file without replacing a concurrent creator's key.
    descriptor, temporary = tempfile.mkstemp(prefix=".tideway-key-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(key.hex().encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            return read_existing()
        return key
    finally:
        os.unlink(temporary)


def sign(key: bytes, document: dict) -> str:
    body = {k: v for k, v in document.items() if k != "signature"}
    return hmac.new(key, canonical_json(body).encode(), hashlib.sha256).hexdigest()


def verify(key: bytes, document: dict) -> bool:
    signature = document.get("signature") if isinstance(document, dict) else None
    if (not isinstance(signature, str) or len(signature) != 64
            or any(character not in "0123456789abcdef" for character in signature)):
        return False
    return hmac.compare_digest(sign(key, document), signature)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter:
    """Small token bucket per client key (sessions, or the anonymous login form)."""

    def __init__(self, capacity=60, refill_per_second=1.0):
        self.capacity, self.refill = capacity, refill_per_second
        self.buckets = {}
        self.lock = threading.Lock()

    def allow(self, key) -> bool:
        now = time.monotonic()
        with self.lock:
            tokens, updated = self.buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - updated) * self.refill)
            if len(self.buckets) > 10_000:
                # A bucket that has refilled to capacity is identical to a fresh one, so dropping it changes nothing.
                full_after = self.capacity / self.refill
                self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < full_after}
            if tokens < 1:
                self.buckets[key] = (tokens, now)
                return False
            self.buckets[key] = (tokens - 1, now)
            return True
