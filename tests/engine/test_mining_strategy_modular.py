from blockchain_sandbox.engine.mining_strategy import StrategyHookContext, build_mining_strategy
from blockchain_sandbox.llm.llm_backend import LLMDecision


def test_llm_override_respects_whitelist():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="classic", allow_llm_override=True)
    ctx = StrategyHookContext(
        miner_id="M0",
        private_lead=3,
        decision=LLMDecision(action="publish_private", reason="test", release_private_blocks=2),
    )
    plan = strategy.on_block_received(ctx)
    assert plan.publish_private_blocks == 2


def test_llm_invalid_action_falls_back_to_default():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="stubborn", allow_llm_override=True)
    ctx = StrategyHookContext(
        miner_id="M0",
        private_lead=3,
        decision=LLMDecision(action="jam_target", reason="invalid_for_selfish_override"),
    )
    plan = strategy.on_block_received(ctx)
    # stubborn receive default: release exactly 1 when lead > 0
    assert plan.publish_private_blocks == 1


def test_disable_override_uses_strategy_default():
    strategy = build_mining_strategy("selfish", selfish_strategy_name="classic", allow_llm_override=False)
    ctx = StrategyHookContext(
        miner_id="M0",
        private_lead=1,
        decision=LLMDecision(action="publish_if_win", reason="would_override_if_enabled"),
    )
    plan = strategy.on_block_mined(ctx)
    # classic on mine default: withhold (publish_new_block=False)
    assert plan.publish_new_block is False


def test_stubborn_ds_reads_strategy_context_provider():
    strategy = build_mining_strategy(
        "selfish",
        selfish_strategy_name="stubborn_ds",
        allow_llm_override=False,
        strategy_context_provider=lambda **_: {
            "ds_enabled": True,
            "ds_target_confirmations": 2,
            "confirmations_seen": 2,
            "free_shot_eligible": True,
        },
    )
    ctx = StrategyHookContext(
        miner_id="M0",
        private_lead=3,
        decision=LLMDecision(action="hold", reason="default"),
    )
    plan = strategy.on_block_received(ctx)
    assert plan.publish_private_blocks == 2
