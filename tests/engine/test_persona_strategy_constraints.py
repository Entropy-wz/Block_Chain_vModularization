from blockchain_sandbox.engine.mining_strategy import StrategyHookContext, build_mining_strategy
from blockchain_sandbox.llm.llm_backend import LLMDecision
from blockchain_sandbox.reporting.agentic_metrics import MinerDetail, _decision_audit_summary


class _DummyResult:
    def __init__(self, prompt_traces):
        self.prompt_traces = prompt_traces


def test_invalid_llm_action_is_constrained_to_strategy_baseline():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="classic", allow_llm_override=True)
    plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=2,
            decision=LLMDecision(action="jam_target", reason="invalid"),
            event_kind="on_block_received",
        )
    )
    assert plan.constrained is True
    assert plan.fallback_to_strategy is True
    assert plan.baseline_action == "publish_private"
    assert plan.chosen_action == "publish_private"
    assert plan.publish_private_blocks >= 1


def test_intermittent_allowed_domain_changes_with_phase():
    strategy = build_mining_strategy(
        "selfish",
        selfish_strategy_name="intermittent_epoch",
        allow_llm_override=True,
        strategy_context_provider=lambda **_: {
            "difficulty_phase": "late",
            "intermittent_mode": "epoch_end_burst",
        },
    )
    guide = strategy.llm_guidance(event_kind="on_block_received", private_lead=1)
    allowed = set(str(guide["strategy_allowed_actions"]).split(","))
    assert "spite_withhold" in allowed
    assert "temporary_honest" not in allowed


def test_persona_first_prefers_persona_action_on_hold():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=1,
            decision=LLMDecision(action="hold", reason="neutral"),
            event_kind="on_block_received",
            persona_state={"fear": 0.1, "stubbornness": 0.2, "revenge": 0.8, "fatigue": 0.1},
        )
    )
    assert plan.persona_deviation is True
    assert plan.chosen_action == "spite_withhold"


def test_persona_deviation_level_changes_trigger_threshold():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    persona_state = {"fear": 0.10, "stubbornness": 0.20, "revenge": 0.70, "fatigue": 0.20}
    low_plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=1,
            decision=LLMDecision(action="hold", reason="neutral"),
            event_kind="on_block_received",
            persona_state=persona_state,
            strategy_runtime={"persona_deviation_level": "low", "llm_decision_mode": "persona_first"},
        )
    )
    high_plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=1,
            decision=LLMDecision(action="hold", reason="neutral"),
            event_kind="on_block_received",
            persona_state=persona_state,
            strategy_runtime={"persona_deviation_level": "high", "llm_decision_mode": "persona_first"},
        )
    )
    assert low_plan.persona_deviation is False
    assert high_plan.persona_deviation is True


def test_action_set_basic_disables_extended_persona_actions():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=1,
            decision=LLMDecision(action="hold", reason="neutral"),
            event_kind="on_block_received",
            persona_state={"fear": 0.1, "stubbornness": 0.2, "revenge": 0.9, "fatigue": 0.1},
            strategy_runtime={"persona_action_set": "basic", "llm_decision_mode": "persona_first"},
        )
    )
    assert plan.persona_deviation is False
    assert plan.chosen_action == "hold"


def test_constraint_strict_removes_persona_actions_from_domain():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    guide_safe = strategy.llm_guidance(event_kind="on_block_received", private_lead=1)
    guide_strict = strategy.llm_guidance(event_kind="on_block_received", private_lead=1)
    # Explicit strict context via direct hook call
    plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=1,
            decision=LLMDecision(action="spite_withhold", reason="test"),
            event_kind="on_block_received",
            strategy_runtime={"strategy_constraint_strictness": "strict"},
        )
    )
    assert "spite_withhold" in set(str(guide_safe["strategy_allowed_actions"]).split(","))
    assert plan.chosen_action != "spite_withhold"


def test_strategy_first_forces_baseline_action():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    plan = strategy.on_block_received(
        StrategyHookContext(
            miner_id="M0",
            private_lead=1,
            decision=LLMDecision(action="hold", reason="test"),
            event_kind="on_block_received",
            strategy_runtime={"llm_decision_mode": "strategy_first"},
        )
    )
    assert plan.baseline_action == "publish_private"
    assert plan.chosen_action == "publish_private"
    assert plan.fallback_to_strategy is True


def test_no_publish_private_in_guidance_when_private_lead_zero():
    stubborn = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    intermittent = build_mining_strategy("selfish", selfish_strategy_name="intermittent_epoch", allow_llm_override=True)
    st_allowed = set(str(stubborn.llm_guidance(event_kind="on_block_received", private_lead=0)["strategy_allowed_actions"]).split(","))
    it_allowed = set(str(intermittent.llm_guidance(event_kind="on_block_received", private_lead=0)["strategy_allowed_actions"]).split(","))
    assert "publish_private" not in st_allowed
    assert "publish_private" not in it_allowed


def test_decision_audit_uses_executed_action_and_consistency_check():
    traces = [
        {
            "miner_id": "M0",
            "decision": {"action": "publish_private"},
            "effective_decision": {"action": "publish_private"},
            "executed_action": "hold",
            "decision_audit": {
                "strategy_name": "stubborn",
                "baseline_action": "hold",
                "fallback_to_strategy": True,
                "deviation_reason": "strategy-first-hard-fallback",
            },
        },
        {
            "miner_id": "M0",
            "decision": {"action": "hold"},
            "effective_decision": {"action": "hold"},
            "executed_action": "panic_publish",
            "decision_audit": {
                "strategy_name": "stubborn",
                "baseline_action": "hold",
                "fallback_to_strategy": False,
                "deviation_reason": "persona-strong-override",
            },
        },
    ]
    result = _DummyResult(traces)
    miner_details = [
        MinerDetail(
            miner_id="M0",
            strategy="selfish",
            hash_power=0.1,
            mined_blocks=1,
            canonical_blocks=1,
            orphan_blocks=0,
            orphan_ratio=0.0,
            mined_share=1.0,
            canonical_share=1.0,
            mined_vs_hp_ratio=1.0,
            canonical_vs_hp_ratio=1.0,
            economic_net_profit=0.0,
            economic_roi=0.0,
            economic_share=0.0,
            economic_vs_hp_ratio=0.0,
            top_actions=[],
            last_raw_action="",
            last_effective_action="",
            last_executed_action="",
            last_reason="",
            last_prompt="",
        )
    ]
    audit = _decision_audit_summary(result, miner_details)
    assert audit["raw_action_dist"]["publish_private"] == 1
    assert audit["effective_action_dist"]["hold"] == 1
    assert audit["executed_action_dist"]["hold"] == 1
    assert audit["executed_action_dist"]["panic_publish"] == 1
    assert audit["strategy_constrained_rate"] > 0.0
    assert audit["persona_deviation_rate"] > 0.0
    assert audit["audit_consistency"] is True
    assert audit["audit_mismatch_count"] == 0
