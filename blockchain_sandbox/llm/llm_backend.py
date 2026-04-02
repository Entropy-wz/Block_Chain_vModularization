from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..core.config import LLMConfig


class LLMDecision:
    def __init__(self, action: str, reason: str, target_miner: str = "", release_private_blocks: int = 0, **kwargs: Any):
        self.action = action
        self.reason = reason
        self.target_miner = target_miner
        self.release_private_blocks = release_private_blocks
        for k, v in kwargs.items():
            setattr(self, k, v)
            
    def __repr__(self):
        return f"LLMDecision(action={self.action}, reason={self.reason}, target_miner={self.target_miner}, release_private_blocks={self.release_private_blocks}, kwargs={self.__dict__})"


class LLMBackend(ABC):
    @abstractmethod
    def decide(self, system_prompt: str, user_prompt: str) -> LLMDecision:
        raise NotImplementedError


class CompatibleLLMBackend(LLMBackend):
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("openai package is required for compatible backend") from exc

        if not config.api_key:
            raise RuntimeError("LLM api_key is empty. Please configure configs/llm_provider.yaml")
        if not config.base_url:
            raise RuntimeError("LLM base_url is empty. Please configure configs/llm_provider.yaml")

        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=float(config.timeout_seconds),
            max_retries=3,
        )

    def decide(self, system_prompt: str, user_prompt: str) -> LLMDecision:
        text = ""
        if self.config.use_chat_completions:
            response = self.client.chat.completions.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_output_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = _extract_chat_text(response)
        else:
            response = self.client.responses.create(
                model=self.config.model,
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_output_tokens,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = getattr(response, "output_text", "") or ""

        data = _safe_json_parse(text)
        if not data:
            return LLMDecision(action="publish_if_win", reason="Fallback: invalid model output JSON.")

        kwargs = {}
        # Parse common known module fields if they exist in the JSON
        if "jam_steps" in data: kwargs["jam_steps"] = _coerce_int(data.get("jam_steps"), 0)
        if "social_action" in data: kwargs["social_action"] = _coerce_str(data.get("social_action"), "none")
        if "social_target" in data: kwargs["social_target"] = _coerce_str(data.get("social_target"), "")
        if "social_board" in data: kwargs["social_board"] = _coerce_str(data.get("social_board"), "mining")
        if "social_tone" in data: kwargs["social_tone"] = max(-1.0, min(1.0, _coerce_float(data.get("social_tone"), 0.0)))
        if "social_content" in data: kwargs["social_content"] = _coerce_str(data.get("social_content"), "")
        
        # Capture any remaining arbitrary keys
        for k, v in data.items():
            if k not in ["action", "reason", "target_miner", "release_private_blocks"] and k not in kwargs:
                kwargs[k] = v

        return LLMDecision(
            action=_coerce_str(data.get("action"), "publish_if_win"),
            reason=_coerce_str(data.get("reason"), "no reason"),
            target_miner=_coerce_str(data.get("target_miner"), ""),
            release_private_blocks=_coerce_int(data.get("release_private_blocks"), 0),
            **kwargs
        )


def build_llm_backend(config: LLMConfig) -> LLMBackend:
    return CompatibleLLMBackend(config)


def _safe_json_parse(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return {}
    return {}


def _extract_chat_text(response: Any) -> str:
    try:
        choices = getattr(response, "choices", []) or []
        if not choices:
            return ""
        msg = choices[0].message
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)
    except Exception:
        return ""


def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _coerce_int(value: Any, default: int) -> int:
    try:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if not s:
            return default
        # Keep leading sign and digits only.
        sign = ""
        if s[0] in "+-":
            sign = s[0]
            s = s[1:]
        digits = []
        for ch in s:
            if ch.isdigit():
                digits.append(ch)
            else:
                break
        if not digits:
            return default
        return int(sign + "".join(digits))
    except Exception:
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return default
        # If the value is mixed text (e.g. "provocative"), fallback.
        # If it starts with a numeric token, parse that token.
        token = []
        seen_digit = False
        for i, ch in enumerate(s):
            if ch.isdigit():
                token.append(ch)
                seen_digit = True
                continue
            if ch in "+-" and i == 0:
                token.append(ch)
                continue
            if ch == ".":
                token.append(ch)
                continue
            break
        if not seen_digit:
            return default
        return float("".join(token))
    except Exception:
        return default
