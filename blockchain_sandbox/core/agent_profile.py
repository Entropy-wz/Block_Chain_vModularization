from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, Dict, Optional, Tuple

import tomllib

from .persona import MinerPersona


Range = Tuple[float, float]


@dataclass(frozen=True)
class RoleDefaults:
    risk_appetite: Range
    aggression: Range
    patience: Range
    sociability: Range
    investment_style: str
    narrative_style: str


@dataclass(frozen=True)
class AgentProfileConfig:
    selfish_ratio: float
    explicit_selfish: set[str]
    selfish_defaults: RoleDefaults
    honest_defaults: RoleDefaults
    persona_overrides: Dict[str, MinerPersona]
    role_overrides: Dict[str, str]

    def is_selfish(self, miner_id: str, miner_index: int, num_miners: int) -> bool:
        role = self.role_overrides.get(miner_id, "").strip().lower()
        if role == "selfish":
            return True
        if role == "honest":
            return False
        if miner_id in self.explicit_selfish:
            return True
        threshold = int(round(num_miners * self.selfish_ratio))
        threshold = max(0, min(num_miners, threshold))
        return miner_index < threshold

    def build_persona(self, miner_id: str, is_selfish: bool, rng: Random) -> MinerPersona:
        if miner_id in self.persona_overrides:
            return self.persona_overrides[miner_id]
        d = self.selfish_defaults if is_selfish else self.honest_defaults
        suffix = "aggressive_speculator" if is_selfish else "steady_fundamentalist"
        return MinerPersona(
            name=f"{miner_id}_{suffix}",
            risk_appetite=_sample_range(d.risk_appetite, rng),
            aggression=_sample_range(d.aggression, rng),
            patience=_sample_range(d.patience, rng),
            sociability=_sample_range(d.sociability, rng),
            investment_style=d.investment_style,
            narrative_style=d.narrative_style,
        )


def load_agent_profile_config(path: Optional[str]) -> AgentProfileConfig:
    if not path:
        return _default_profile_config()
    p = Path(path)
    if not p.exists():
        return _default_profile_config()

    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    policy = _as_dict(raw.get("policy"))
    defaults = _as_dict(raw.get("defaults"))
    selfish_defaults = _parse_role_defaults(_as_dict(defaults.get("selfish")), _default_selfish())
    honest_defaults = _parse_role_defaults(_as_dict(defaults.get("honest")), _default_honest())

    role_overrides: Dict[str, str] = {}
    persona_overrides: Dict[str, MinerPersona] = {}
    miners = _as_dict(raw.get("miners"))
    for miner_id, payload in miners.items():
        entry = _as_dict(payload)
        role = str(entry.get("role", "")).strip().lower()
        if role in {"selfish", "honest"}:
            role_overrides[miner_id] = role
        persona = _parse_persona_override(miner_id, entry)
        if persona is not None:
            persona_overrides[miner_id] = persona

    selfish_ratio = _clamp(_to_float(policy.get("selfish_ratio"), 0.25), 0.0, 1.0)
    explicit = {
        str(x).strip()
        for x in _to_list(policy.get("explicit_selfish"))
        if str(x).strip()
    }
    return AgentProfileConfig(
        selfish_ratio=selfish_ratio,
        explicit_selfish=explicit,
        selfish_defaults=selfish_defaults,
        honest_defaults=honest_defaults,
        persona_overrides=persona_overrides,
        role_overrides=role_overrides,
    )


def _default_profile_config() -> AgentProfileConfig:
    return AgentProfileConfig(
        selfish_ratio=0.25,
        explicit_selfish=set(),
        selfish_defaults=_default_selfish(),
        honest_defaults=_default_honest(),
        persona_overrides={},
        role_overrides={},
    )


def _default_selfish() -> RoleDefaults:
    return RoleDefaults(
        risk_appetite=(0.72, 0.94),
        aggression=(0.68, 0.93),
        patience=(0.55, 0.90),
        sociability=(0.35, 0.90),
        investment_style="event_driven",
        narrative_style="provocative",
    )


def _default_honest() -> RoleDefaults:
    return RoleDefaults(
        risk_appetite=(0.25, 0.60),
        aggression=(0.20, 0.55),
        patience=(0.45, 0.90),
        sociability=(0.35, 0.85),
        investment_style="value_stability",
        narrative_style="measured",
    )


def _parse_role_defaults(data: Dict[str, Any], fallback: RoleDefaults) -> RoleDefaults:
    return RoleDefaults(
        risk_appetite=_to_range(data.get("risk_appetite"), fallback.risk_appetite),
        aggression=_to_range(data.get("aggression"), fallback.aggression),
        patience=_to_range(data.get("patience"), fallback.patience),
        sociability=_to_range(data.get("sociability"), fallback.sociability),
        investment_style=str(data.get("investment_style", fallback.investment_style)).strip(),
        narrative_style=str(data.get("narrative_style", fallback.narrative_style)).strip(),
    )


def _parse_persona_override(miner_id: str, data: Dict[str, Any]) -> Optional[MinerPersona]:
    keys = {
        "name",
        "risk_appetite",
        "aggression",
        "patience",
        "sociability",
        "investment_style",
        "narrative_style",
    }
    if not any(k in data for k in keys):
        return None
    return MinerPersona(
        name=str(data.get("name", f"{miner_id}_custom")).strip(),
        risk_appetite=_clamp(_to_float(data.get("risk_appetite"), 0.5), 0.0, 1.0),
        aggression=_clamp(_to_float(data.get("aggression"), 0.5), 0.0, 1.0),
        patience=_clamp(_to_float(data.get("patience"), 0.5), 0.0, 1.0),
        sociability=_clamp(_to_float(data.get("sociability"), 0.5), 0.0, 1.0),
        investment_style=str(data.get("investment_style", "balanced")).strip(),
        narrative_style=str(data.get("narrative_style", "measured")).strip(),
    )


def _sample_range(value: Range, rng: Random) -> float:
    lo, hi = value
    return max(0.0, min(1.0, lo + rng.random() * max(0.0, hi - lo)))


def _to_range(raw: Any, fallback: Range) -> Range:
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        lo = _to_float(raw[0], fallback[0])
        hi = _to_float(raw[1], fallback[1])
        lo, hi = sorted((lo, hi))
        return (_clamp(lo, 0.0, 1.0), _clamp(hi, 0.0, 1.0))
    x = _to_float(raw, fallback[0])
    x = _clamp(x, 0.0, 1.0)
    return (x, x)


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
