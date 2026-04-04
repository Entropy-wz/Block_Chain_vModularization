from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from blockchain_sandbox.core.config import LLMConfig


def load_llm_config_from_yaml(path: str) -> LLMConfig:
    p = Path(path)
    if not p.exists():
        raise RuntimeError(f"LLM config file not found: {p}")

    raw = p.read_text(encoding="utf-8")
    data = _parse_minimal_yaml(raw)

    keys = data.get("api_key", [])
    api_key = keys[0] if keys else ""
    model = data.get("model_name", "gpt-4o-mini")
    base_url = data.get("base_url", "")
    use_chat = _to_bool(data.get("use_chat_completions", "false"))
    temperature = _to_float(data.get("temperature", "0.2"), 0.2)
    max_output_tokens = _to_int(data.get("max_output_tokens", "220"), 220)
    timeout_seconds = _to_int(data.get("timeout_seconds", "30"), 30)
    max_concurrent = _to_int(data.get("max_concurrent_requests", "5"), 5)

    return LLMConfig(
        backend="compatible",
        model=model,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        seed=1234,
        api_key=api_key,
        base_url=base_url,
        use_chat_completions=use_chat,
        max_concurrent_requests=max_concurrent,
    )


def _parse_minimal_yaml(text: str) -> Dict[str, object]:
    out: Dict[str, object] = {}
    lines = [ln.rstrip() for ln in text.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "api_key":
            arr: List[str] = []
            while i < len(lines):
                candidate = lines[i].strip()
                if not candidate or candidate.startswith("#"):
                    i += 1
                    continue
                if candidate.startswith("- "):
                    arr.append(candidate[2:].strip().strip('"').strip("'"))
                    i += 1
                    continue
                break
            out[key] = arr
        else:
            out[key] = value.strip('"').strip("'")
    return out


def _to_bool(v: object) -> bool:
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "on"}


def _to_int(v: object, default: int) -> int:
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _to_float(v: object, default: float) -> float:
    try:
        return float(str(v).strip())
    except Exception:
        return default

