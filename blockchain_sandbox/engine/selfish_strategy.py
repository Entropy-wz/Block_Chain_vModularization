from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass(frozen=True)
class SelfishStrategyContext:
    event_kind: str
    private_lead: int
    reputation: float = 0.0
    ds_enabled: bool = False
    ds_target_confirmations: int = 2
    confirmations_seen: int = 0
    free_shot_eligible: bool = False
    difficulty_epoch_index: int = 0
    difficulty_epoch_progress: float = 0.0
    difficulty_phase: str = "early"  # early/mid/late
    difficulty_level: float = 1.0
    intermittent_mode: str = "post_adjust_burst"


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


class StubbornDoubleSpendStrategy(SelfishStrategy):
    def decide(self, ctx: SelfishStrategyContext) -> SelfishStrategyPlan:
        lead = max(0, int(ctx.private_lead))
        if ctx.event_kind == "on_block_mined":
            # Stubborn family defaults to withholding mined blocks.
            return SelfishStrategyPlan(publish_new_block=False)
        if lead <= 0:
            return SelfishStrategyPlan()

        if not ctx.ds_enabled:
            return SelfishStrategyPlan(publish_private_blocks=1)

        target = max(1, int(ctx.ds_target_confirmations))
        seen = max(0, int(ctx.confirmations_seen))

        # "Free-shot" window: once confirmations are close enough, release more aggressively.
        if ctx.free_shot_eligible and seen >= max(0, target - 1):
            return SelfishStrategyPlan(publish_private_blocks=min(lead, 2))
        if seen >= target:
            return SelfishStrategyPlan(publish_private_blocks=min(lead, 2))
        return SelfishStrategyPlan(publish_private_blocks=1)


class IntermittentEpochStrategy(SelfishStrategy):
    def decide(self, ctx: SelfishStrategyContext) -> SelfishStrategyPlan:
        lead = max(0, int(ctx.private_lead))
        mode = (ctx.intermittent_mode or "post_adjust_burst").strip().lower()
        phase = (ctx.difficulty_phase or "early").strip().lower()

        if mode == "epoch_end_burst":
            aggressive = phase == "late"
        else:
            aggressive = phase == "early"

        if ctx.event_kind == "on_block_mined":
            # In non-attack phase, prefer conservative publication.
            return SelfishStrategyPlan(publish_new_block=(not aggressive))

        if lead <= 0:
            return SelfishStrategyPlan()

        if aggressive:
            if lead == 1:
                return SelfishStrategyPlan(publish_private_blocks=1)
            return SelfishStrategyPlan(publish_private_blocks=1)

        # Conservative stage: realize gains faster.
        if lead == 1:
            return SelfishStrategyPlan(publish_private_blocks=1)
        return SelfishStrategyPlan(publish_private_blocks=min(lead, 2))


_SELFISH_REGISTRY: Dict[str, Callable[[Optional[Callable[[], float]]], SelfishStrategy]] = {
    "classic": lambda reputation_provider=None: ClassicSelfishStrategy(),
    "stubborn": lambda reputation_provider=None: StubbornSelfishStrategy(),
    "social": lambda reputation_provider=None: SocialSelfishStrategy(reputation_provider=reputation_provider),
    "stubborn_ds": lambda reputation_provider=None: StubbornDoubleSpendStrategy(),
    "intermittent_epoch": lambda reputation_provider=None: IntermittentEpochStrategy(),
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
