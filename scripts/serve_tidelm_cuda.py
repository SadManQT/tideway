"""Serve the CUDA-trained TideLM adapter as a loopback-only OpenAI-compatible endpoint for Tideway.

Implements exactly what tideway/local_model.py calls:
  GET  /v1/models            -> {"object": "list", "data": [{"id": MODEL_ID, ...}]}
  POST /v1/chat/completions  -> {"choices": [{"message": {"role": "assistant", "content": ...}}], ...}
Decoding is always greedy (temperature is ignored) with Qwen3 thinking disabled, the same prompt format as
training and evaluation. `response_format` (json_object or json_schema) is accepted but not enforced by
constrained decoding: the model is trained to emit JSON and Tideway re-validates every answer itself.
Image content is rejected (text model). Binds 127.0.0.1 only; requests with a non-loopback Host are refused.

Run (ML venv, repo root):
  python scripts/serve_tidelm_cuda.py --adapter %USERPROFILE%/tideway-models/tidelm-cuda-adapter --port 8796
Then start Tideway (standard-library Python) with:
  TIDEWAY_LOCAL_MODEL_URL=http://127.0.0.1:8796/v1  TIDEWAY_LOCAL_TEXT_MODEL=tidelm-cuda-qwen3-1.7b
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tideway.ml.tidelm_cuda_common import (DEFAULT_ADAPTER, DEFAULT_BASE, DEFAULT_REVISION, adapter_hashes,  # noqa: E402
                                           chat_prompt, load_model, stop_ids)

MAX_BODY = 1 << 20
MAX_TOKENS_CAP = 1024


class Engine:
    def __init__(self, args):
        started = time.time()
        self.model, self.tokenizer = load_model(args.model, args.revision, args.adapter or None, merge=not args.no_merge)
        self.lock = threading.Lock()
        self.model_id = args.model_id
        self.load_seconds = round(time.time() - started, 1)
        self.adapter_sha256 = adapter_hashes(args.adapter) if args.adapter else None

    def complete(self, system, user, max_tokens):
        import torch
        prompt = chat_prompt(self.tokenizer, system, user)
        encoded = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        with self.lock, torch.no_grad():
            started = time.time()
            output = self.model.generate(**encoded, max_new_tokens=max_tokens, do_sample=False,
                                         eos_token_id=stop_ids(self.tokenizer), pad_token_id=self.tokenizer.pad_token_id)
            elapsed = time.time() - started
        new = output[0, encoded["input_ids"].shape[1]:]
        finished = len(new) > 0 and int(new[-1]) in stop_ids(self.tokenizer)
        text = self.tokenizer.decode(new, skip_special_tokens=True)
        return text, int(encoded["input_ids"].shape[1]), int(len(new)), "stop" if finished else "length", elapsed


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str):
                raise ValueError("Only text content is supported by this text model.")
            parts.append(part["text"])
        return "\n".join(parts)
    raise ValueError("Message content must be text.")


def make_handler(engine, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "TideLM-CUDA/1"

        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)

        def error(self, status, message):
            self.reply(status, {"error": {"message": message, "type": "invalid_request_error"}})

        def host_ok(self):
            return self.client_address[0] in ("127.0.0.1", "::1") and self.headers.get("Host", "") in allowed_hosts

        def do_GET(self):
            if not self.host_ok():
                return self.error(403, "Loopback only.")
            if self.path.split("?")[0] in ("/v1/models", "/v1/models/"):
                return self.reply(200, {"object": "list", "data": [{
                    "id": engine.model_id, "object": "model", "created": 0, "owned_by": "tideway-local",
                    "adapter_sha256": engine.adapter_sha256}]})
            return self.error(404, "Not found.")

        def do_POST(self):
            if not self.host_ok():
                return self.error(403, "Loopback only.")
            if self.path.split("?")[0] != "/v1/chat/completions":
                return self.error(404, "Not found.")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    return self.error(413, "Request body too large or empty.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Body must be a JSON object.")
                if body.get("model") not in (None, engine.model_id):
                    return self.error(404, f"Unknown model; this server serves {engine.model_id}.")
                if body.get("stream"):
                    raise ValueError("Streaming is not supported.")
                messages = body.get("messages")
                if not isinstance(messages, list) or not messages:
                    raise ValueError("messages must be a non-empty list.")
                system = "\n".join(text_of(m.get("content")) for m in messages if isinstance(m, dict) and m.get("role") == "system")
                users = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
                if not users or len(users) + (1 if system else 0) != len(messages):
                    raise ValueError("Send one system message (optional) and one user message.")
                user = text_of(users[-1].get("content"))
                max_tokens = body.get("max_tokens", 512)
                if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
                    raise ValueError("max_tokens must be a positive integer.")
                fmt = body.get("response_format")
                if fmt is not None and (not isinstance(fmt, dict) or fmt.get("type") not in ("text", "json_object", "json_schema")):
                    raise ValueError("Unsupported response_format.")
            except (ValueError, json.JSONDecodeError) as exc:
                return self.error(400, str(exc))
            try:
                text, prompt_tokens, new_tokens, finish, elapsed = engine.complete(system, user, min(max_tokens, MAX_TOKENS_CAP))
            except Exception as exc:  # report, never crash the server
                sys.stderr.write(f"generation failed: {type(exc).__name__}: {exc}\n")
                return self.error(500, "Generation failed.")
            self.reply(200, {"id": "chatcmpl-" + uuid.uuid4().hex[:24], "object": "chat.completion", "created": int(time.time()),
                             "model": engine.model_id,
                             "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}],
                             "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": new_tokens,
                                       "total_tokens": prompt_tokens + new_tokens},
                             "tideway_generation_seconds": round(elapsed, 3),
                             "tideway_response_format_enforced": False})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=DEFAULT_BASE, help="Hugging Face id or local directory of the base model")
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--adapter", default=str(DEFAULT_ADAPTER), help="LoRA adapter directory ('' serves the base model)")
    parser.add_argument("--model-id", default="tidelm-cuda-qwen3-1.7b")
    parser.add_argument("--port", type=int, default=8796)
    parser.add_argument("--no-merge", action="store_true")
    args = parser.parse_args()
    engine = Engine(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine, args.port))
    print(f"TideLM CUDA server: http://127.0.0.1:{args.port}/v1 model={engine.model_id} adapter={args.adapter or 'none'} "
          f"loaded in {engine.load_seconds}s", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
