from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ..core.persona import MinerPersona
from .llm_backend import LLMBackend, LLMDecision


@dataclass
class AgentObservation:
    step: int
    miner_id: str
    is_selfish: bool
    hash_power: float
    local_public_height: int
    private_lead: int
    rivalry_pressure: float
    known_competitor_heads: Dict[str, int]
    persona: MinerPersona
    modules_context: Dict[str, Any] = field(default_factory=dict)
    event_kind: str = "periodic"
    trigger_block_id: str = ""


@dataclass
class MinerAgent:
    miner_id: str
    is_selfish: bool
    hash_power: float
    llm: LLMBackend
    modules_system_prompts: List[str] = field(default_factory=list)
    modules_decision_keys: Dict[str, str] = field(default_factory=dict)
    memory: List[str] = field(default_factory=list)
    trace_callback: Optional[Callable[[Dict[str, object]], None]] = None

    def _build_prompts(self, obs: AgentObservation) -> tuple[str, str]:
        system_prompt = (
            "You are a strategic Bitcoin mining agent in a simulation sandbox. "
            "Primary objective: maximize your expected canonical-chain reward share over time, "
            "not merely the count of mined blocks. "
            "You have a distinct persona profile (risk, aggression, style, sociability). "
            "Use persona as style bias, but stay utility-rational under current network conditions. "
            "\n\n"
            "Economic guidance: withhold only when expected advantage is positive. "
            "If private lead is fragile or rivals are catching up, prefer timely publish_private to protect payoff. "
            "Excessive stubborn withholding increases orphan risk and can reduce long-term reward. "
            "\n\n"
        )
        for mp in self.modules_system_prompts:
            if mp:
                system_prompt += f"{mp}\n\n"
                
        expected_keys = {
            "action": "string (publish_if_win, withhold_if_win, publish_private, rebroadcast, hold, jam_target)",
            "reason": "string",
            "release_private_blocks": "integer"
        }
        expected_keys.update(self.modules_decision_keys)
        
        keys_str = ", ".join(expected_keys.keys())
        types_str = "; ".join(f"{k} must be {v}" for k, v in expected_keys.items())
        
        system_prompt += (
            f"Output format: return strict JSON only (no markdown/code fences) with keys exactly: {keys_str}. "
            f"Type rules: {types_str}. "
        )

        compact_heads = ",".join(f"{k}:{v}" for k, v in sorted(obs.known_competitor_heads.items()))

        recent = self.memory[-3:] if self.memory else ["none"]
        recent_memory_str = " | ".join(recent)

        user_prompt = (
            f"step={obs.step};miner_id={obs.miner_id};is_selfish={str(obs.is_selfish).lower()};"
            f"event_kind={obs.event_kind};trigger_block_id={obs.trigger_block_id};"
            f"hash_power={obs.hash_power:.5f};local_public_height={obs.local_public_height};"
            f"private_lead={obs.private_lead};rivalry_pressure={obs.rivalry_pressure:.4f};"
            f"heads={compact_heads};"
            f"persona={obs.persona.name};risk={obs.persona.risk_appetite:.2f};"
            f"aggression={obs.persona.aggression:.2f};patience={obs.persona.patience:.2f};"
            f"sociability={obs.persona.sociability:.2f};style={obs.persona.investment_style};"
            f"narrative_style={obs.persona.narrative_style};"
        )
        
        for k, v in obs.modules_context.items():
            if isinstance(v, float):
                user_prompt += f"{k}={v:+.3f};"
            else:
                user_prompt += f"{k}={v};"
                
        user_prompt += f"recent_memory=[{recent_memory_str}]"
        return system_prompt, user_prompt

    def _post_process_decision(self, obs: AgentObservation, decision: LLMDecision, system_prompt: str, user_prompt: str) -> None:
        if self.trace_callback is not None:
            trace_payload = {
                "step": obs.step,
                "miner_id": obs.miner_id,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "decision": {
                    "action": decision.action,
                    "reason": decision.reason,
                    "release_private_blocks": decision.release_private_blocks,
                }
            }
            for key in self.modules_decision_keys:
                trace_payload["decision"][key] = getattr(decision, key, None)
                
            self.trace_callback(trace_payload)
            
        short_content = getattr(decision, "social_content", "")
        if short_content:
            short_content = short_content[:40].replace("\n", " ") + "..."
        else:
            short_content = "none"
        self.memory.append(f"t={obs.step} action={decision.action} content={short_content}")
        if len(self.memory) > 60:
            self.memory = self.memory[-60:]

    def decide(self, obs: AgentObservation) -> LLMDecision:
        system_prompt, user_prompt = self._build_prompts(obs)
        decision = self.llm.decide(system_prompt, user_prompt)
        self._post_process_decision(obs, decision, system_prompt, user_prompt)
        return decision

    async def decide_async(self, obs: AgentObservation) -> LLMDecision:
        system_prompt, user_prompt = self._build_prompts(obs)
        decision = await self.llm.decide_async(system_prompt, user_prompt)
        self._post_process_decision(obs, decision, system_prompt, user_prompt)
        return decision
