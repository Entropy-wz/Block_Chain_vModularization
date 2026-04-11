from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..llm.llm_backend import LLMDecision
from .selfish_strategy import SelfishStrategyContext, SelfishStrategyPlan, build_selfish_strategy


@dataclass(frozen=True)
class StrategyHookContext:
    miner_id: str
    private_lead: int
    decision: LLMDecision
    received_block_id: str = ""


@dataclass(frozen=True)
class StrategyHookPlan:
    publish_new_block: bool = True
    publish_private_blocks: int = 0
    rebroadcast_head: bool = False


class MiningStrategy(ABC):
    @abstractmethod
    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        raise NotImplementedError

    @abstractmethod
    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        raise NotImplementedError


class HonestMiningStrategy(MiningStrategy):
    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        # Honest miner should publish immediately when winning a block.
        return StrategyHookPlan(
            publish_new_block=True,
            publish_private_blocks=0,
            rebroadcast_head=(ctx.decision.action == "rebroadcast"),
        )

    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        return StrategyHookPlan(
            publish_new_block=True,
            publish_private_blocks=0,
            rebroadcast_head=(ctx.decision.action == "rebroadcast"),
        )


class AbstractSelfishMining(MiningStrategy):
    def __init__(self, strategy_name: str, reputation_provider=None, allow_llm_override: bool = True):
        self.reputation_provider = reputation_provider
        self.allow_llm_override = allow_llm_override
        self.selfish_strategy = build_selfish_strategy(strategy_name, reputation_provider=reputation_provider)

    def _default_plan(self, event_kind: str, lead: int) -> StrategyHookPlan:
        rep = 0.0
        if self.reputation_provider is not None:
            try:
                rep = float(self.reputation_provider())
            except Exception:
                rep = 0.0
        out: SelfishStrategyPlan = self.selfish_strategy.decide(
            SelfishStrategyContext(event_kind=event_kind, private_lead=lead, reputation=rep)
        )
        release = max(0, int(out.publish_private_blocks))
        return StrategyHookPlan(
            publish_new_block=bool(out.publish_new_block),
            publish_private_blocks=release,
            rebroadcast_head=bool(out.rebroadcast_head),
        )

    def _llm_override_plan(self, decision: LLMDecision, private_lead: int) -> StrategyHookPlan | None:
        action = (getattr(decision, "action", "") or "").strip().lower()
        if action not in {"publish_if_win", "withhold_if_win", "publish_private", "rebroadcast", "hold"}:
            return None
        if action == "publish_if_win":
            return StrategyHookPlan(publish_new_block=True)
        if action in {"withhold_if_win", "hold"}:
            return StrategyHookPlan(publish_new_block=False)
        if action == "rebroadcast":
            return StrategyHookPlan(rebroadcast_head=True)
        release = max(0, min(int(getattr(decision, "release_private_blocks", 0)), max(0, int(private_lead))))
        return StrategyHookPlan(publish_private_blocks=release)

    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        default_plan = self._default_plan("on_block_mined", ctx.private_lead)
        if not self.allow_llm_override:
            return default_plan
        override = self._llm_override_plan(ctx.decision, ctx.private_lead)
        return override if override is not None else default_plan

    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        default_plan = self._default_plan("on_block_received", ctx.private_lead)
        if not self.allow_llm_override:
            return default_plan
        override = self._llm_override_plan(ctx.decision, ctx.private_lead)
        return override if override is not None else default_plan


class StandardSelfishMining(AbstractSelfishMining):
    """Classic Eyal & Sirer Selfish Mining via module strategy."""
    def __init__(self, reputation_provider=None, allow_llm_override: bool = True):
        super().__init__("classic", reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)


class SociallyAwareSelfishMining(AbstractSelfishMining):
    """Socially-aware selfish mining via module strategy."""
    def __init__(self, reputation_provider=None, allow_llm_override: bool = True):
        super().__init__("social", reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)


class StubbornMining(AbstractSelfishMining):
    """Stubborn mining via module strategy."""
    def __init__(self, reputation_provider=None, allow_llm_override: bool = True):
        super().__init__("stubborn", reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)


def build_mining_strategy(
    strategy_name: str,
    reputation_provider=None,
    selfish_strategy_name: str = "classic",
    allow_llm_override: bool = True,
) -> MiningStrategy:
    name = (strategy_name or "").strip().lower()
    if name == "selfish":
        if selfish_strategy_name == "stubborn":
            return StubbornMining(reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)
        if selfish_strategy_name == "social":
            return SociallyAwareSelfishMining(reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)
        return StandardSelfishMining(reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)
    if name == "social_selfish":
        return SociallyAwareSelfishMining(reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)
    if name == "stubborn":
        return StubbornMining(reputation_provider=reputation_provider, allow_llm_override=allow_llm_override)
    return HonestMiningStrategy()
