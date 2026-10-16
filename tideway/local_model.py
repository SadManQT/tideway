"""Opt-in, loopback-only OpenAI-compatible inference for Windows and macOS.

This transports prompts, not permissions. Existing tool/draft validators remain
the authority boundary. A compatible model is not the evaluated TideLM adapter.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit


class LocalModelUnavailable(RuntimeError):
    pass


class LocalModel:
    def __init__(self, url, model):
        self.model = model.strip()
        self.url = url.strip().rstrip("/")
        self._cache = None
        self._checked = 0.0
        self.error = None
        try:
            parsed = urlsplit(self.url)
            if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path != "/v1" or not self.model or len(self.model) > 200
                    or "cloud" in self.model.lower() or any(ord(c) < 32 for c in self.model)):
                raise ValueError
            self.host, self.port = parsed.hostname, parsed.port or 80
        except ValueError:
            self.error = "Use a local http://127.0.0.1:PORT/v1 endpoint and an explicit installed model ID."

    @classmethod
    def configured(cls, kind="text"):
        model = os.getenv("TIDEWAY_LOCAL_TEXT_MODEL" if kind == "text" else "TIDEWAY_LOCAL_VISION_MODEL", "")
        url = os.getenv("TIDEWAY_LOCAL_MODEL_URL", "")
        return cls(url, model) if model else None

    def _request(self, method, path, payload=None, timeout=45):
        if self.error:
            raise LocalModelUnavailable(self.error)
        connection = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        deadline = time.monotonic() + timeout
        try:
            body = json.dumps(payload).encode("utf-8") if payload is not None else None
            connection.request(method, "/v1/" + path, body,
                               {"Content-Type": "application/json", "Connection": "close"})
            response = connection.getresponse()
            # HTTPConnection never follows redirects, including redirects off-host.
            if response.status != 200:
                raise LocalModelUnavailable(f"Local model server returned HTTP {response.status}.")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LocalModelUnavailable("Local model request exceeded its time budget.")
                # Keep a total deadline even if a server drips response bytes.
                sock = connection.sock or getattr(getattr(response.fp, "raw", None), "_sock", None)
                if sock is not None:
                    sock.settimeout(remaining)
                chunk = response.read1(min(16384, 262145 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > 262144:
                    raise LocalModelUnavailable("Local model response exceeded the 256 KiB limit.")
            raw = b"".join(chunks)
            return json.loads(raw)
        except (OSError, http.client.HTTPException, UnicodeError, ValueError, RecursionError) as exc:
            raise LocalModelUnavailable("Local model is unavailable or returned invalid JSON. Check the local server and model ID.") from exc
        finally:
            connection.close()

    def status(self):
        if self._cache is not None and time.monotonic() - self._checked < 5:
            return dict(self._cache)
        result = {"available": False, "loaded": False, "model": self.model,
                  "backend": "local-compatible", "label": f"Local model: {self.model} (unbenchmarked)",
                  "evaluated_tidelm_adapter": False, "reason": self.error}
        try:
            data = self._request("GET", "models", timeout=0.7)
            ids = {row.get("id") for row in data.get("data", []) if isinstance(row, dict)}
            if self.model not in ids:
                raise LocalModelUnavailable("Configured model ID is not installed on the local server.")
            result.update(available=True, reason=None)
        except (LocalModelUnavailable, AttributeError, TypeError) as exc:
            result["reason"] = str(exc) if isinstance(exc, LocalModelUnavailable) else "Invalid model list from the local server."
        self._cache, self._checked = result, time.monotonic()
        return dict(result)

    def generate(self, system, user, max_tokens=700, image_path=None):
        content = user
        if image_path:
            encoded = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
            content = [{"type": "text", "text": user},
                       {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}}]
        data = self._request("POST", "chat/completions", {
            "model": self.model, "messages": [{"role": "system", "content": system},
                                               {"role": "user", "content": content}],
            "stream": False, "temperature": 0, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        })
        try:
            answer = data["choices"][0]["message"]["content"]
        except (TypeError, KeyError, IndexError) as exc:
            raise LocalModelUnavailable("Local model returned no message content.") from exc
        if not isinstance(answer, str) or not answer.strip():
            raise LocalModelUnavailable("Local model returned empty or invalid message content.")
        return answer
