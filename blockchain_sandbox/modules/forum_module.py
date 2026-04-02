import os
from typing import Any, Dict

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule
from ..social.forum import ForumState


class ForumModule(ISimulationModule):
    def __init__(self):
        self.forum = ForumState()
        self.ctx: ISimulationContext = None

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        bus.subscribe(EventTypes.AGENT_DECISION_MADE, self._on_agent_decision)
        bus.subscribe(EventTypes.NODE_BANNED, self._on_node_banned)

    def on_step_start(self, ctx: ISimulationContext) -> None:
        pass
        
    def _on_node_banned(self, payload: Dict[str, Any]) -> None:
        node_id = payload.get("node_id")
        reason = payload.get("reason", "unknown")
        step = payload.get("step", 0)
        
        if node_id:
            self.forum.publish(
                step=step,
                author_id="SYSTEM",
                board="governance",
                tone=0.0,
                target_id=node_id,
                content=f"Node {node_id} has been physically disconnected from the network due to {reason}.",
            )

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        return {
            "forum_global_sentiment": self.forum.global_sentiment(),
            "forum_personal_sentiment": self.forum.personal_sentiment(miner_id, ctx.graph),
            "forum_hot_board": self.forum.hottest_board(),
            "forum_feed_digest": self.forum.brief_feed_text(miner_id, ctx.graph),
            "own_reputation": self.forum.reputation_of(miner_id),
            "reputation_risk": "critical" if self.forum.reputation_of(miner_id) <= -8.0 else ("elevated" if self.forum.reputation_of(miner_id) <= -4.0 else "normal")
        }

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        return (
            "Social-topology guidance: reputation matters. If reputation gets very low (especially near -10), "
            "network-level disconnection risk is high. In crisis, de-escalate via call_truce and less hostile actions. "
            "Keep mining action and social action coherent (no contradictory signaling). "
        )

    def expected_decision_keys(self) -> Dict[str, str]:
        return {
            "social_action": "string (none, post_fud, post_hype, call_truce)",
            "social_target": "string",
            "social_board": "string",
            "social_tone": "float [-1.0, 1.0]",
            "social_content": "string"
        }

    def _on_agent_decision(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        effective = payload.get("effective")
        if not miner_id or not effective:
            return

        action = (getattr(effective, "social_action", "none") or "none").strip().lower()
        if action == "none":
            return

        board = (getattr(effective, "social_board", "mining") or "mining").strip().lower()
        if board not in {"mining", "security", "governance", "market"}:
            board = "mining"

        target = (getattr(effective, "social_target", "") or "").strip()
        if not target:
            target = (getattr(effective, "target_miner", "") or "").strip()
        
        # Verify target exists
        if target and target not in self.ctx.nodes:
            target = ""

        tone = getattr(effective, "social_tone", 0.0)
        tone = max(-1.0, min(1.0, tone))
        
        if action == "post_fud":
            tone = tone if tone < 0 else -max(0.2, abs(tone))
            if not target:
                target = self._pick_jam_target(miner_id)
        elif action == "post_hype":
            tone = tone if tone > 0 else max(0.2, abs(tone))
        elif action == "call_truce":
            tone = 0.12
            board = "governance"
        else:
            return

        content = (getattr(effective, "social_content", "") or "").strip() or self._default_social_content(action, miner_id, target)
        self.forum.publish(
            step=self.ctx.current_step,
            author_id=miner_id,
            board=board,
            tone=tone,
            target_id=target,
            content=content,
        )

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
            hostility = abs(min(0.0, self.forum.reputation_of(c.node_id)))
            score = c.hash_power * 2.0 + hostility * 0.05
            if score > best_score:
                best_score = score
                best = c.node_id
        return best or candidates[0].node_id

    def _default_social_content(self, action: str, miner_id: str, target: str) -> str:
        if action == "post_fud":
            return f"{target or 'Some pools'} show suspicious block behavior; stay alert."
        if action == "post_hype":
            return f"{miner_id} shares strong relay performance and stable output."
        return "Network health requires coordination and less hostility."
