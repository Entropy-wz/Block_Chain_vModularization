from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from ..core.entities import Block
from ..core.interfaces import ISimulationContext
from .agent import AgentObservation
from .llm_backend import LLMDecision

@dataclass
class RouteResult:
    needs_llm: bool
    priority: int
    fallback_decision: Optional[LLMDecision] = None
    trigger_reason: str = ""

class DecisionRouter:
    def __init__(self, simulation: ISimulationContext, cooldown_steps: int = 10):
        self.sim = simulation
        self.cooldown_steps = cooldown_steps
        self._last_call_steps: Dict[str, int] = {}

    def _get_reputation(self, miner_id: str) -> float:
        for module in self.sim.modules:
            if hasattr(module, "forum"):
                return float(module.forum.reputation_of(miner_id))
        return 0.0

    def _get_jam_status(self, miner_id: str) -> bool:
        for module in self.sim.modules:
            if hasattr(module, "active_jams"):
                for jam in getattr(module, "active_jams"):
                    if jam.target_id == miner_id:
                        return True
        return False

    def route_decision(self, miner_id: str, obs: AgentObservation, current_time: float) -> RouteResult:
        current_step = int(current_time * 100.0)
        last_step = self._last_call_steps.get(miner_id, -1000)
        
        # 1. 挖掘事件：如果挖掘到了新区块，肯定要调 LLM 进行策略调整（如果是自私矿工则更为重要）
        if obs.event_kind == "on_block_mined":
            self._last_call_steps[miner_id] = current_step
            return RouteResult(needs_llm=True, priority=0, trigger_reason="block_mined")

        # 2. 冷却期检测（如果在 N 步内都没有调过大模型，需要周期性地看一次全局状态）
        if (current_step - last_step) > self.cooldown_steps:
            self._last_call_steps[miner_id] = current_step
            return RouteResult(needs_llm=True, priority=10, trigger_reason="cooldown_expired")

        # 3. 关键状态判断：私有链
        if obs.private_lead > 0:
            self._last_call_steps[miner_id] = current_step
            return RouteResult(needs_llm=True, priority=5, trigger_reason="private_chain_active")

        # 4. 关键状态判断：Fork 侦测 (收到不同于本地头的等高或更高区块)
        trigger_block = None
        b_store = getattr(self.sim, "block_storage", None)
        if obs.trigger_block_id:
            if b_store:
                trigger_block = b_store.get_summary(obs.trigger_block_id)
            elif obs.trigger_block_id in self.sim.blocks:
                trigger_block = self.sim.blocks[obs.trigger_block_id]
        
        my_head_id = self.sim.nodes[miner_id].local_head_id or self.sim.genesis_id
        
        # 简单判定分叉：如果有竞争头，或者是自私矿工遇到了较强算力者的区块
        if trigger_block:
            my_h = self.sim.chain_heights.get(my_head_id, 0)
            if trigger_block.height >= my_h and trigger_block.block_id != my_head_id:
                 self._last_call_steps[miner_id] = current_step
                 return RouteResult(needs_llm=True, priority=0, trigger_reason="fork_detected")

        # 5. 社会与网络状态判定
        # 自身受到攻击
        if self._get_jam_status(miner_id):
            self._last_call_steps[miner_id] = current_step
            return RouteResult(needs_llm=True, priority=0, trigger_reason="jam_attack_detected")
            
        # 自身名誉受损严重
        if self._get_reputation(miner_id) < -3.0:
            self._last_call_steps[miner_id] = current_step
            return RouteResult(needs_llm=True, priority=0, trigger_reason="reputation_dropped")

        # 若是诚实矿工，在平稳期可以直接使用兜底逻辑
        if not obs.is_selfish:
            return RouteResult(
                needs_llm=False,
                priority=10,
                fallback_decision=LLMDecision(action="rebroadcast", reason="router: honest routine"),
                trigger_reason="honest_routine_short_circuit"
            )

        # 自私矿工在平稳期（落后或无特殊压力）兜底逻辑
        return RouteResult(
            needs_llm=False,
            priority=10,
            fallback_decision=LLMDecision(action="hold", reason="router: selfish routine withhold"),
            trigger_reason="selfish_routine_short_circuit"
        )