from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class SelfishStrategyContext:
    event_kind: str
    private_lead: int
    reputation: float = 0.0


@dataclass(frozen=True)
class SelfishStrategyPlan:
    publish_new_block: bool = False
    publish_private_blocks: int = 0
    rebroadcast_head: bool = False


class SelfishStrategy(ABC):
    @abstractmethod
    def decide(self, ctx: SelfishStrategyContext) -> SelfishStrategyPlan:
        raise NotImplementedError


class ClassicSelfishStrategy(SelfishStrategy):
    def decide(self, ctx: SelfishStrategyContext) -> SelfishStrategyPlan:
        lead = max(0, int(ctx.private_lead))
        if ctx.event_kind == "on_block_mined":
            return SelfishStrategyPlan(publish_new_block=False)
        if lead <= 0:
            return SelfishStrategyPlan()
        if lead == 1:
            return SelfishStrategyPlan(publish_private_blocks=1)
        if lead == 2:
            return SelfishStrategyPlan(publish_private_blocks=2)
        return SelfishStrategyPlan(publish_private_blocks=1)


class StubbornSelfishStrategy(SelfishStrategy):
    def decide(self, ctx: SelfishStrategyContext) -> SelfishStrategyPlan:
        lead = max(0, int(ctx.private_lead))
        if ctx.event_kind == "on_block_mined":
            return SelfishStrategyPlan(publish_new_block=False)
        if lead <= 0:
            return SelfishStrategyPlan()
        return SelfishStrategyPlan(publish_private_blocks=1)


class SocialSelfishStrategy(SelfishStrategy):
    def __init__(self, reputation_provider: Optional[Callable[[], float]] = None) -> None:
        self.reputation_provider = reputation_provider

    def decide(self, ctx: SelfishStrategyContext) -> SelfishStrategyPlan:
        lead = max(0, int(ctx.private_lead))
        rep = ctx.reputation
        if self.reputation_provider is not None:
            try:
                rep = float(self.reputation_provider())
            except Exception:
                rep = ctx.reputation

        if ctx.event_kind == "on_block_mined":
            if rep < -5.0:
                return SelfishStrategyPlan(publish_new_block=True)
            return SelfishStrategyPlan(publish_new_block=False)

        if lead <= 0:
            return SelfishStrategyPlan()
        if rep < -5.0:
            return SelfishStrategyPlan(publish_private_blocks=lead)
        if lead == 1:
            return SelfishStrategyPlan(publish_private_blocks=1)
        if lead == 2:
            return SelfishStrategyPlan(publish_private_blocks=2)
        return SelfishStrategyPlan(publish_private_blocks=1)


_SELFISH_REGISTRY: Dict[str, Callable[[Optional[Callable[[], float]]], SelfishStrategy]] = {
    "classic": lambda reputation_provider=None: ClassicSelfishStrategy(),
    "stubborn": lambda reputation_provider=None: StubbornSelfishStrategy(),
    "social": lambda reputation_provider=None: SocialSelfishStrategy(reputation_provider=reputation_provider),
}


def register_selfish_strategy(
    name: str,
    factory: Callable[[Optional[Callable[[], float]]], SelfishStrategy],
) -> None:
    key = (name or "").strip().lower()
    if not key:
        return
    _SELFISH_REGISTRY[key] = factory


def build_selfish_strategy(
    name: str,
    reputation_provider: Optional[Callable[[], float]] = None,
) -> SelfishStrategy:
    key = (name or "").strip().lower() or "classic"
    factory = _SELFISH_REGISTRY.get(key) or _SELFISH_REGISTRY["classic"]
    return factory(reputation_provider)
