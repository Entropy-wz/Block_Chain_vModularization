from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..llm.llm_backend import LLMDecision


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
    @abstractmethod
    def evaluate_mine(self, lead: int) -> StrategyHookPlan:
        pass

    @abstractmethod
    def evaluate_receive(self, lead: int) -> StrategyHookPlan:
        pass

    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        action = ctx.decision.action
        if action == "publish_if_win":
            return StrategyHookPlan(publish_new_block=True)
        if action == "publish_private":
            release = max(0, ctx.decision.release_private_blocks)
            return StrategyHookPlan(publish_new_block=False, publish_private_blocks=release)
        
        # Fallback to pure algorithm
        return self.evaluate_mine(ctx.private_lead)

    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        action = ctx.decision.action
        if action == "publish_private":
            release = max(0, ctx.decision.release_private_blocks)
            return StrategyHookPlan(publish_private_blocks=release)

        # Fallback to pure algorithm
        return self.evaluate_receive(ctx.private_lead)


class StandardSelfishMining(AbstractSelfishMining):
    """Classic Eyal & Sirer Selfish Mining"""
    def evaluate_mine(self, lead: int) -> StrategyHookPlan:
        return StrategyHookPlan(publish_new_block=False)

    def evaluate_receive(self, lead: int) -> StrategyHookPlan:
        if lead <= 0:
            return StrategyHookPlan()
        if lead == 1:
            return StrategyHookPlan(publish_private_blocks=1)
        if lead == 2:
            return StrategyHookPlan(publish_private_blocks=2)
        return StrategyHookPlan(publish_private_blocks=1)


class SociallyAwareSelfishMining(AbstractSelfishMining):
    """Selfish mining that falls back to honest behavior if reputation gets too low (-5.0)."""
    def __init__(self, reputation_provider=None):
        self.reputation_provider = reputation_provider

    def evaluate_mine(self, lead: int) -> StrategyHookPlan:
        # If reputation is dangerously low, act honestly to repair it
        if self.reputation_provider and self.reputation_provider() < -5.0:
            return StrategyHookPlan(publish_new_block=True)
        return StrategyHookPlan(publish_new_block=False)

    def evaluate_receive(self, lead: int) -> StrategyHookPlan:
        if lead <= 0:
            return StrategyHookPlan()
        # If reputation is dangerously low, release everything we have to catch up honestly
        if self.reputation_provider and self.reputation_provider() < -5.0:
            return StrategyHookPlan(publish_private_blocks=lead)
        if lead == 1:
            return StrategyHookPlan(publish_private_blocks=1)
        if lead == 2:
            return StrategyHookPlan(publish_private_blocks=2)
        return StrategyHookPlan(publish_private_blocks=1)


class StubbornMining(AbstractSelfishMining):
    """Stubborn Mining variant (keeps lead, refuses to tie break easily)"""
    def evaluate_mine(self, lead: int) -> StrategyHookPlan:
        return StrategyHookPlan(publish_new_block=False)

    def evaluate_receive(self, lead: int) -> StrategyHookPlan:
        if lead <= 0:
            return StrategyHookPlan()
        return StrategyHookPlan(publish_private_blocks=1)


def build_mining_strategy(strategy_name: str, reputation_provider=None) -> MiningStrategy:
    if strategy_name == "selfish":
        return StandardSelfishMining()
    if strategy_name == "social_selfish":
        return SociallyAwareSelfishMining(reputation_provider)
    if strategy_name == "stubborn":
        return StubbornMining()
    return HonestMiningStrategy()
