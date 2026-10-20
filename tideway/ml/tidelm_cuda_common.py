"""Shared helpers for the CUDA (PyTorch + PEFT) TideLM path on Windows/Linux with an NVIDIA GPU.

Optional tooling only: the app itself never imports this module and stays standard-library-only.
Needs a separate environment with torch (CUDA build), transformers, peft and accelerate; see
docs/TIDELM_CUDA.md. Qwen3 "thinking" is disabled (enable_thinking=False) everywhere: in training,
evaluation and serving the assistant turn starts after the same empty <think></think> block.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = "Qwen/Qwen3-1.7B"
DEFAULT_REVISION = "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e"  # Hugging Face commit used for the recorded run
DEFAULT_ADAPTER = Path.home() / "tideway-models" / "tidelm-cuda-adapter"
EVIDENCE = ROOT / "evidence" / "ml-cuda"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def data_hashes(data_dir):
    data_dir = Path(data_dir)
    return {name: sha256_file(data_dir / name) for name in ("train.jsonl", "valid.jsonl", "test.jsonl")
            if (data_dir / name).is_file()}


def adapter_hashes(adapter_dir):
    adapter_dir = Path(adapter_dir)
    return {p.name: sha256_file(p) for p in sorted(adapter_dir.iterdir()) if p.is_file()}


def read_jsonl(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def chat_prompt(tokenizer, system, user):
    """The exact prompt text used in training, evaluation and serving (thinking disabled)."""
    return tokenizer.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                         add_generation_prompt=True, tokenize=False, enable_thinking=False)


def environment():
    import torch
    info = {"python": sys.version.split()[0], "platform": platform.platform(), "torch": torch.__version__,
            "torch_cuda": torch.version.cuda, "cudnn": torch.backends.cudnn.version(),
            "cuda_available": torch.cuda.is_available()}
    for name in ("transformers", "peft", "accelerate", "safetensors", "tokenizers", "huggingface_hub"):
        try:
            module = __import__(name)
            info[name] = getattr(module, "__version__", "unknown")
        except ImportError:
            info[name] = None
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        info.update(gpu=props.name, gpu_total_memory_gb=round(props.total_memory / 2 ** 30, 2),
                    gpu_compute_capability=f"{props.major}.{props.minor}", bf16_supported=torch.cuda.is_bf16_supported())
    try:
        import subprocess
        info["nvidia_driver"] = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                                               capture_output=True, text=True, timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        info["nvidia_driver"] = None
    return info


def load_model(base, revision=None, adapter=None, merge=True, device="cuda"):
    """Base model in bf16 on the GPU, optionally with the TideLM LoRA adapter (merged for faster decoding)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    kwargs = {"revision": revision} if revision and not Path(base).exists() else {}
    tokenizer = AutoTokenizer.from_pretrained(base, **kwargs)
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16, **kwargs).to(device)
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(adapter))
        if merge:
            model = model.merge_and_unload()
    model.eval()
    gen = model.generation_config
    gen.do_sample, gen.temperature, gen.top_p, gen.top_k = False, None, None, None  # greedy everywhere
    return model, tokenizer


def stop_ids(tokenizer):
    ids = {tokenizer.convert_tokens_to_ids("<|im_end|>"), tokenizer.eos_token_id}
    return sorted(i for i in ids if isinstance(i, int) and i >= 0)
