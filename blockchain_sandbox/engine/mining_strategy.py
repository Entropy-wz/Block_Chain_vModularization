from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Set

from ..llm.llm_backend import LLMDecision
from .selfish_strategy import SelfishStrategyContext, SelfishStrategyPlan, build_selfish_strategy

_SELFISH_CTX_FIELDS = set(getattr(SelfishStrategyContext, "__dataclass_fields__", {}).keys())


@dataclass(frozen=True)
class StrategyHookContext:
    miner_id: str
    private_lead: int
    decision: LLMDecision
    event_kind: str = "on_block_received"
    persona_state: Dict[str, float] | None = None
    strategy_runtime: Dict[str, Any] | None = None
    received_block_id: str = ""


@dataclass(frozen=True)
class StrategyHookPlan:
    publish_new_block: bool = True
    publish_private_blocks: int = 0
    rebroadcast_head: bool = False
    chosen_action: str = ""
    baseline_action: str = ""
    constrained: bool = False
    persona_deviation: bool = False
    fallback_to_strategy: bool = False
    deviation_reason: str = ""
    strategy_name: str = ""
    allowed_actions: tuple[str, ...] = ()


class MiningStrategy(ABC):
    @abstractmethod
    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        raise NotImplementedError

    @abstractmethod
    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        raise NotImplementedError

    def llm_guidance(self, event_kind: str, private_lead: int) -> Dict[str, Any]:
        return {
            "strategy_name": "honest",
            "strategy_baseline_action": "publish_if_win" if event_kind == "on_block_mined" else "rebroadcast",
            "strategy_allowed_actions": "publish_if_win,rebroadcast,hold",
        }


class HonestMiningStrategy(MiningStrategy):
    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        # Honest miner should publish immediately when winning a block.
        action = (getattr(ctx.decision, "action", "") or "").strip().lower()
        if action not in {"publish_if_win", "rebroadcast", "hold"}:
            action = "publish_if_win"
        return StrategyHookPlan(
            publish_new_block=True,
            publish_private_blocks=0,
            rebroadcast_head=(action == "rebroadcast"),
            chosen_action=action,
            baseline_action="publish_if_win",
            constrained=False,
            persona_deviation=False,
            fallback_to_strategy=(action == "publish_if_win" and (getattr(ctx.decision, "action", "") or "").strip().lower() not in {"publish_if_win", "rebroadcast", "hold"}),
            deviation_reason="",
            strategy_name="honest",
            allowed_actions=("hold", "publish_if_win", "rebroadcast"),
        )

    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        action = (getattr(ctx.decision, "action", "") or "").strip().lower()
        if action not in {"publish_if_win", "rebroadcast", "hold"}:
            action = "rebroadcast"
        return StrategyHookPlan(
            publish_new_block=True,
            publish_private_blocks=0,
            rebroadcast_head=(action == "rebroadcast"),
            chosen_action=action,
            baseline_action="rebroadcast",
            constrained=False,
            persona_deviation=False,
            fallback_to_strategy=(action == "rebroadcast" and (getattr(ctx.decision, "action", "") or "").strip().lower() not in {"publish_if_win", "rebroadcast", "hold"}),
            deviation_reason="",
            strategy_name="honest",
            allowed_actions=("hold", "publish_if_win", "rebroadcast"),
        )

    def llm_guidance(self, event_kind: str, private_lead: int) -> Dict[str, Any]:
        return {
            "strategy_name": "honest",
            "strategy_baseline_action": "publish_if_win" if event_kind == "on_block_mined" else "rebroadcast",
            "strategy_allowed_actions": "publish_if_win,rebroadcast,hold",
        }


class AbstractSelfishMining(MiningStrategy):
    def __init__(
        self,
        strategy_name: str,
        reputation_provider=None,
        allow_llm_override: bool = True,
        strategy_context_provider=None,
    ):
        self.reputation_provider = reputation_provider
        self.allow_llm_override = allow_llm_override
        self.strategy_context_provider = strategy_context_provider
        self.strategy_name = (strategy_name or "classic").strip().lower() or "classic"
        self.selfish_strategy = build_selfish_strategy(strategy_name, reputation_provider=reputation_provider)

    def _runtime_ctx(self, event_kind: str, lead: int) -> Dict[str, Any]:
        extra: Dict[str, Any] = {}
        if self.strategy_context_provider is not None:
            try:
                provided = self.strategy_context_provider(event_kind=event_kind, private_lead=lead)
                if isinstance(provided, dict):
                    extra = dict(provided)
            except Exception:
                extra = {}
        return extra

    def _default_plan(self, event_kind: str, lead: int, runtime_ctx: Dict[str, Any]) -> StrategyHookPlan:
        rep = 0.0
        if self.reputation_provider is not None:
            try:
                rep = float(self.reputation_provider())
            except Exception:
                rep = 0.0
        safe_ctx = {k: v for k, v in runtime_ctx.items() if k in _SELFISH_CTX_FIELDS}
        out: SelfishStrategyPlan = self.selfish_strategy.decide(
            SelfishStrategyContext(event_kind=event_kind, private_lead=lead, reputation=rep, **safe_ctx)
        )
        release = max(0, int(out.publish_private_blocks))
        return StrategyHookPlan(
            publish_new_block=bool(out.publish_new_block),
            publish_private_blocks=release,
            rebroadcast_head=bool(out.rebroadcast_head),
        )

    def _plan_to_action(self, plan: StrategyHookPlan, event_kind: str) -> str:
        if plan.publish_private_blocks > 0:
            return "publish_private"
        if plan.rebroadcast_head:
            return "rebroadcast"
        if event_kind == "on_block_mined":
            return "publish_if_win" if plan.publish_new_block else "withhold_if_win"
        return "hold"

    def _strategy_domain(self, event_kind: str, lead: int, runtime_ctx: Dict[str, Any]) -> Set[str]:
        strictness = str(runtime_ctx.get("strategy_constraint_strictness", "safe")).strip().lower()
        action_set = str(runtime_ctx.get("persona_action_set", "extended")).strip().lower()
        if self.strategy_name == "classic":
            domain = {"publish_if_win", "withhold_if_win", "publish_private", "rebroadcast", "hold"}
        elif self.strategy_name == "stubborn":
            domain = {"withhold_if_win", "publish_private", "hold", "spite_withhold", "feint_release"}
        elif self.strategy_name == "social":
            domain = {"publish_if_win", "publish_private", "rebroadcast", "hold", "temporary_honest", "panic_publish"}
        elif self.strategy_name == "stubborn_ds":
            domain = {"withhold_if_win", "publish_private", "hold", "spite_withhold", "feint_release", "panic_publish"}
        elif self.strategy_name == "intermittent_epoch":
            phase = str(runtime_ctx.get("difficulty_phase", "early")).strip().lower()
            mode = str(runtime_ctx.get("intermittent_mode", "post_adjust_burst")).strip().lower()
            aggressive = phase == "late" if mode == "epoch_end_burst" else phase == "early"
            if aggressive:
                domain = {"withhold_if_win", "publish_private", "hold", "spite_withhold", "feint_release"}
            else:
                domain = {"publish_if_win", "publish_private", "rebroadcast", "hold", "temporary_honest", "panic_publish"}
        else:
            domain = {"publish_if_win", "withhold_if_win", "publish_private", "rebroadcast", "hold"}

        # Lead-sensitive legality: avoid pseudo "publish_private" / "feint_release" when no private chain exists.
        if lead <= 0:
            domain.discard("publish_private")
            domain.discard("feint_release")
            if event_kind != "on_block_mined":
                domain.discard("withhold_if_win")

        persona_actions = {"panic_publish", "temporary_honest", "spite_withhold", "feint_release"}
        if action_set == "basic":
            domain -= persona_actions
        if strictness == "strict":
            domain &= {"publish_if_win", "withhold_if_win", "publish_private", "rebroadcast", "hold"}
        elif strictness == "loose":
            domain |= persona_actions
        return domain

    def _persona_action(
        self,
        event_kind: str,
        private_lead: int,
        persona_state: Dict[str, float] | None,
        runtime_ctx: Dict[str, Any],
    ) -> str | None:
        ps = persona_state or {}
        level = str(runtime_ctx.get("persona_deviation_level", "medium")).strip().lower()
        action_set = str(runtime_ctx.get("persona_action_set", "extended")).strip().lower()
        decision_mode = str(runtime_ctx.get("llm_decision_mode", "persona_first")).strip().lower()
        fear = float(ps.get("fear", 0.0))
        stubborn = float(ps.get("stubbornness", 0.0))
        revenge = float(ps.get("revenge", 0.0))
        fatigue = float(ps.get("fatigue", 0.0))
        if level == "low":
            t_revenge, t_fear, t_fatigue, t_stubborn = 0.78, 0.82, 0.84, 0.86
        elif level in {"high", "strong"}:
            t_revenge, t_fear, t_fatigue, t_stubborn = 0.48, 0.52, 0.56, 0.58
        else:
            t_revenge, t_fear, t_fatigue, t_stubborn = 0.62, 0.64, 0.66, 0.70

        # Decision mode should materially affect deviation intensity.
        if decision_mode == "strategy_first":
            t_revenge += 0.20
            t_fear += 0.20
            t_fatigue += 0.20
            t_stubborn += 0.20
        elif decision_mode in {"high_persona", "persona_strong"}:
            t_revenge -= 0.12
            t_fear -= 0.12
            t_fatigue -= 0.12
            t_stubborn -= 0.12

        if action_set == "basic":
            if fear >= t_fear:
                return "panic_publish"
            if fatigue >= t_fatigue:
                return "temporary_honest"
            return None

        if revenge >= t_revenge and private_lead >= 0:
            return "spite_withhold"
        if fear >= t_fear:
            return "panic_publish"
        if fatigue >= t_fatigue:
            return "temporary_honest"
        if stubborn >= t_stubborn and private_lead > 0:
            return "feint_release"
        return None

    def _llm_override_plan(
        self,
        decision: LLMDecision,
        private_lead: int,
        event_kind: str,
        runtime_ctx: Dict[str, Any],
        allowed_actions: Set[str],
        baseline_action: str,
        baseline_release: int,
        persona_action: str | None,
    ) -> StrategyHookPlan:
        action = (getattr(decision, "action", "") or "").strip().lower()
        decision_mode = str(runtime_ctx.get("llm_decision_mode", "persona_first")).strip().lower()
        constrained = False
        fallback_to_strategy = False
        persona_deviation = False
        deviation_reason = ""

        if action not in allowed_actions:
            constrained = True
            if persona_action and persona_action in allowed_actions:
                action = persona_action
                deviation_reason = "persona-override-invalid-llm"
                persona_deviation = action != baseline_action
            else:
                action = baseline_action
                fallback_to_strategy = True
                deviation_reason = "fallback-to-strategy-invalid-llm"
        elif (
            decision_mode == "persona_first"
            and action == "hold"
            and persona_action
            and persona_action in allowed_actions
        ):
            # "persona-first": avoid dead-flat hold when persona has clear tendency.
            action = persona_action
            persona_deviation = action != baseline_action
            deviation_reason = "persona-first-bias"
        elif decision_mode in {"high_persona", "persona_strong"} and persona_action and persona_action in allowed_actions:
            # Strong persona mode can override even non-hold actions.
            action = persona_action
            persona_deviation = action != baseline_action
            deviation_reason = "persona-strong-override"
        elif decision_mode == "strategy_first" and action != baseline_action:
            action = baseline_action
            fallback_to_strategy = True
            deviation_reason = "strategy-first-hard-fallback"

        release = max(0, min(int(getattr(decision, "release_private_blocks", 0)), max(0, int(private_lead))))
        if action == "publish_private" and release <= 0 and private_lead > 0:
            release = min(max(1, baseline_release), private_lead)

        plan = self._apply_action(action=action, event_kind=event_kind, release=release, private_lead=private_lead)
        if action == "publish_private" and plan.publish_private_blocks <= 0:
            constrained = True
            action = baseline_action
            plan = self._apply_action(
                action=baseline_action,
                event_kind=event_kind,
                release=max(0, baseline_release),
                private_lead=private_lead,
            )
            fallback_to_strategy = True
            deviation_reason = "fallback-no-private-lead"

        return StrategyHookPlan(
            publish_new_block=plan.publish_new_block,
            publish_private_blocks=plan.publish_private_blocks,
            rebroadcast_head=plan.rebroadcast_head,
            chosen_action=action,
            baseline_action=baseline_action,
            constrained=constrained,
            persona_deviation=persona_deviation,
            fallback_to_strategy=fallback_to_strategy,
            deviation_reason=deviation_reason,
            strategy_name=self.strategy_name,
            allowed_actions=tuple(sorted(allowed_actions)),
        )

    def _apply_action(self, action: str, event_kind: str, release: int, private_lead: int) -> StrategyHookPlan:
        if action == "publish_if_win":
            return StrategyHookPlan(publish_new_block=True)
        if action == "withhold_if_win":
            return StrategyHookPlan(publish_new_block=False)
        if action == "hold":
            if event_kind == "on_block_mined":
                return StrategyHookPlan(publish_new_block=False)
            return StrategyHookPlan(publish_new_block=True, publish_private_blocks=0, rebroadcast_head=False)
        if action == "rebroadcast":
            return StrategyHookPlan(rebroadcast_head=True)
        if action == "panic_publish":
            if private_lead > 0:
                return StrategyHookPlan(publish_private_blocks=max(1, private_lead))
            return StrategyHookPlan(publish_new_block=(event_kind == "on_block_mined"), rebroadcast_head=(event_kind != "on_block_mined"))
        if action == "temporary_honest":
            return StrategyHookPlan(publish_new_block=(event_kind == "on_block_mined"), rebroadcast_head=(event_kind != "on_block_mined"))
        if action == "spite_withhold":
            return StrategyHookPlan(publish_new_block=False)
        if action == "feint_release":
            return StrategyHookPlan(publish_private_blocks=1 if private_lead > 0 else 0)
        # publish_private or unknown mapped by caller
        return StrategyHookPlan(publish_private_blocks=release)

    def _finalize_default_plan(self, default_plan: StrategyHookPlan, event_kind: str, allowed_actions: Set[str]) -> StrategyHookPlan:
        baseline_action = self._plan_to_action(default_plan, event_kind)
        if baseline_action not in allowed_actions:
            baseline_action = "hold"
        return StrategyHookPlan(
            publish_new_block=default_plan.publish_new_block,
            publish_private_blocks=default_plan.publish_private_blocks,
            rebroadcast_head=default_plan.rebroadcast_head,
            chosen_action=baseline_action,
            baseline_action=baseline_action,
            constrained=False,
            persona_deviation=False,
            fallback_to_strategy=False,
            deviation_reason="",
            strategy_name=self.strategy_name,
            allowed_actions=tuple(sorted(allowed_actions)),
        )

    def on_block_mined(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        runtime_ctx = ctx.strategy_runtime or self._runtime_ctx("on_block_mined", ctx.private_lead)
        allowed_actions = self._strategy_domain("on_block_mined", ctx.private_lead, runtime_ctx)
        default_plan = self._default_plan("on_block_mined", ctx.private_lead, runtime_ctx)
        base = self._finalize_default_plan(default_plan, "on_block_mined", allowed_actions)
        if not self.allow_llm_override:
            return base
        persona_action = self._persona_action("on_block_mined", ctx.private_lead, ctx.persona_state, runtime_ctx)
        return self._llm_override_plan(
            decision=ctx.decision,
            private_lead=ctx.private_lead,
            event_kind="on_block_mined",
            runtime_ctx=runtime_ctx,
            allowed_actions=allowed_actions,
            baseline_action=base.baseline_action,
            baseline_release=base.publish_private_blocks,
            persona_action=persona_action,
        )

    def on_block_received(self, ctx: StrategyHookContext) -> StrategyHookPlan:
        runtime_ctx = ctx.strategy_runtime or self._runtime_ctx("on_block_received", ctx.private_lead)
        allowed_actions = self._strategy_domain("on_block_received", ctx.private_lead, runtime_ctx)
        default_plan = self._default_plan("on_block_received", ctx.private_lead, runtime_ctx)
        base = self._finalize_default_plan(default_plan, "on_block_received", allowed_actions)
        if not self.allow_llm_override:
            return base
        persona_action = self._persona_action("on_block_received", ctx.private_lead, ctx.persona_state, runtime_ctx)
        return self._llm_override_plan(
            decision=ctx.decision,
            private_lead=ctx.private_lead,
            event_kind="on_block_received",
            runtime_ctx=runtime_ctx,
            allowed_actions=allowed_actions,
            baseline_action=base.baseline_action,
            baseline_release=base.publish_private_blocks,
            persona_action=persona_action,
        )

    def llm_guidance(self, event_kind: str, private_lead: int) -> Dict[str, Any]:
        runtime_ctx = self._runtime_ctx(event_kind, private_lead)
        default_plan = self._default_plan(event_kind, private_lead, runtime_ctx)
        baseline_action = self._plan_to_action(default_plan, event_kind)
        allowed_actions = self._strategy_domain(event_kind, private_lead, runtime_ctx)
        return {
            "strategy_name": self.strategy_name,
            "strategy_baseline_action": baseline_action,
            "strategy_allowed_actions": ",".join(sorted(allowed_actions)),
            "strategy_phase": str(runtime_ctx.get("difficulty_phase", "")),
        }


class StandardSelfishMining(AbstractSelfishMining):
    """Classic Eyal & Sirer Selfish Mining via module strategy."""
    def __init__(self, reputation_provider=None, allow_llm_override: bool = True, strategy_context_provider=None):
        super().__init__(
            "classic",
            reputation_provider=reputation_provider,
            allow_llm_override=allow_llm_override,
            strategy_context_provider=strategy_context_provider,
        )


class SociallyAwareSelfishMining(AbstractSelfishMining):
    """Socially-aware selfish mining via module strategy."""
    def __init__(self, reputation_provider=None, allow_llm_override: bool = True, strategy_context_provider=None):
        super().__init__(
            "social",
            reputation_provider=reputation_provider,
            allow_llm_override=allow_llm_override,
            strategy_context_provider=strategy_context_provider,
        )


class StubbornMining(AbstractSelfishMining):
    """Stubborn mining via module strategy."""
    def __init__(self, reputation_provider=None, allow_llm_override: bool = True, strategy_context_provider=None):
        super().__init__(
            "stubborn",
            reputation_provider=reputation_provider,
            allow_llm_override=allow_llm_override,
            strategy_context_provider=strategy_context_provider,
        )


def build_mining_strategy(
    strategy_name: str,
    reputation_provider=None,
    selfish_strategy_name: str = "classic",
    allow_llm_override: bool = True,
    strategy_context_provider=None,
) -> MiningStrategy:
    name = (strategy_name or "").strip().lower()
    if name == "selfish":
        if selfish_strategy_name == "stubborn":
            return StubbornMining(
                reputation_provider=reputation_provider,
                allow_llm_override=allow_llm_override,
                strategy_context_provider=strategy_context_provider,
            )
        if selfish_strategy_name == "social":
            return SociallyAwareSelfishMining(
                reputation_provider=reputation_provider,
                allow_llm_override=allow_llm_override,
                strategy_context_provider=strategy_context_provider,
            )
        # Modular path: allow new registered strategy names directly.
        if selfish_strategy_name not in {"classic", "stubborn", "social"}:
            return AbstractSelfishMining(
                selfish_strategy_name,
                reputation_provider=reputation_provider,
                allow_llm_override=allow_llm_override,
                strategy_context_provider=strategy_context_provider,
            )
        return StandardSelfishMining(
            reputation_provider=reputation_provider,
            allow_llm_override=allow_llm_override,
            strategy_context_provider=strategy_context_provider,
        )
    if name == "social_selfish":
        return SociallyAwareSelfishMining(
            reputation_provider=reputation_provider,
            allow_llm_override=allow_llm_override,
            strategy_context_provider=strategy_context_provider,
        )
    if name == "stubborn":
        return StubbornMining(
            reputation_provider=reputation_provider,
            allow_llm_override=allow_llm_override,
            strategy_context_provider=strategy_context_provider,
        )
    return HonestMiningStrategy()
