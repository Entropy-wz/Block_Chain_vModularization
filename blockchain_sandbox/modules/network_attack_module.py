from typing import Any, Dict, List, Optional, Tuple

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule


class NetworkAttackModule(ISimulationModule):
    def __init__(self, max_steps_of_jam_effect: int = 6, enable_jamming: bool = True):
        self.max_steps_of_jam_effect = max_steps_of_jam_effect
        self.enable_jamming = enable_jamming
        self.jam_events = 0
        # (restore_at, src, dst, factor)
        self._jam_restore_schedule: List[Tuple[float, str, Optional[str], float]] = []
        self.ctx: ISimulationContext = None

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        bus.subscribe(EventTypes.AGENT_DECISION_MADE, self._on_agent_decision)

    def on_step_start(self, ctx: ISimulationContext) -> None:
        self._restore_jam_if_due(ctx.current_time)

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        obs = {}
        if self.enable_jamming:
            obs["jam_target"] = self._pick_jam_target(miner_id)
        return obs

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        prompt = ""
        if self.enable_jamming:
            prompt += "You may choose action='jam_target' to slow down a specific miner's block propagation. Use 'target_miner' to specify who, and 'jam_steps' to specify duration.\n"
        return prompt

    def expected_decision_keys(self) -> Dict[str, str]:
        keys = {}
        if self.enable_jamming:
            keys["jam_steps"] = "int"
            keys["target_miner"] = "string"
        return keys

    def _on_agent_decision(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        effective = payload.get("effective")
        if not miner_id or not effective:
            return

        action = getattr(effective, "action", "")
        if self.enable_jamming and action == "jam_target":
            target_miner = getattr(effective, "target_miner", "")
            if target_miner and target_miner in self.ctx.nodes and target_miner != miner_id:
                jam_steps_req = getattr(effective, "jam_steps", 2)
                jam_steps = max(1, min(jam_steps_req, self.max_steps_of_jam_effect))
                
                self._jam_target_links(
                    now_time=self.ctx.current_time,
                    target_miner=target_miner,
                    factor=1.8,
                    duration_steps=jam_steps,
                )
                self.jam_events += 1

    def _jam_target_links(self, now_time: float, target_miner: str, factor: float, duration_steps: int) -> None:
        self.ctx.graph.apply_latency_multiplier(target_miner, factor=factor)
        restore_at = now_time + float(duration_steps)
        self._jam_restore_schedule.append((restore_at, target_miner, None, factor))

    def _restore_jam_if_due(self, current_time: float) -> None:
        if not self._jam_restore_schedule:
            return
        remain: List[Tuple[float, str, Optional[str], float]] = []
        for restore_at, src, dst, factor in self._jam_restore_schedule:
            if restore_at <= current_time and factor != 0:
                self.ctx.graph.apply_latency_multiplier(src, dst, factor=(1.0 / factor))
            else:
                remain.append((restore_at, src, dst, factor))
        self._jam_restore_schedule = remain

    def _pick_jam_target(self, miner_id: str) -> str:
        candidates = [
            n for n in self.ctx.nodes.values()
            if n.is_miner and n.node_id != miner_id and n.strategy_name == "honest"
        ]
        if not candidates:
            return ""
        best = None
        best_score = float("-inf")
        for c in candidates:
            # We don't have direct access to forum here (clean separation), 
            # so we just pick largest honest hash power if no forum context
            score = c.hash_power * 2.0
            if score > best_score:
                best_score = score
                best = c.node_id
        return best or candidates[0].node_id
