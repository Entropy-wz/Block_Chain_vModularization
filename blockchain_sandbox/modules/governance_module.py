from typing import Any, Callable, Dict

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule


class GovernanceModule(ISimulationModule):
    def __init__(self, ban_reputation_threshold: float = -10.0, reputation_provider: Callable[[str], float] = lambda x: 0.0):
        self.ban_reputation_threshold = ban_reputation_threshold
        self.reputation_provider = reputation_provider
        self.ctx: ISimulationContext = None
        self.bus: IEventBus = None

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        self.bus = bus

    def on_step_start(self, ctx: ISimulationContext) -> None:
        # Check reputation for banning
        for node_id, node in ctx.nodes.items():
            if node.is_miner and not getattr(node, "is_banned", False):
                rep = self.reputation_provider(node_id)
                if rep <= self.ban_reputation_threshold:
                    setattr(node, "is_banned", True)
                    ctx.graph.ban_node(node_id)
                    # Publish governance event
                    self.bus.publish(EventTypes.NODE_BANNED, {
                        "node_id": node_id,
                        "reason": f"reputation_too_low ({rep:.1f})",
                        "step": ctx.current_step
                    })

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        return {}

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        return ""

    def expected_decision_keys(self) -> Dict[str, str]:
        return {}
