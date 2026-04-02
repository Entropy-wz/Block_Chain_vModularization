from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ..core.graph_model import Edge


@dataclass(frozen=True)
class PropagationDecision:
    forward_edges: List[Edge]


class MinerStrategy:
    name = "base"

    def select_propagation_edges(self, outgoing_edges: List[Edge]) -> PropagationDecision:
        return PropagationDecision(forward_edges=outgoing_edges)

    def mining_multiplier(self) -> float:
        return 1.0


class HonestStrategy(MinerStrategy):
    name = "honest"


class DegreeBiasedStrategy(MinerStrategy):
    name = "degree_biased"

    def select_propagation_edges(self, outgoing_edges: List[Edge]) -> PropagationDecision:
        # Prefer lower latency and higher reliability links.
        ranked = sorted(outgoing_edges, key=lambda e: (e.latency, -e.reliability))
        keep = max(1, int(len(ranked) * 0.6))
        return PropagationDecision(forward_edges=ranked[:keep])

    def mining_multiplier(self) -> float:
        # Slightly lower due to selective routing overhead.
        return 0.95


class SelfishLikeStrategy(MinerStrategy):
    name = "selfish_like"

    def select_propagation_edges(self, outgoing_edges: List[Edge]) -> PropagationDecision:
        # Simulates delayed and partial disclosure.
        keep = max(1, int(len(outgoing_edges) * 0.4))
        return PropagationDecision(forward_edges=outgoing_edges[:keep])

    def mining_multiplier(self) -> float:
        return 1.05


def build_strategy(name: str) -> MinerStrategy:
    if name == HonestStrategy.name:
        return HonestStrategy()
    if name == DegreeBiasedStrategy.name:
        return DegreeBiasedStrategy()
    if name == SelfishLikeStrategy.name:
        return SelfishLikeStrategy()
    return HonestStrategy()
