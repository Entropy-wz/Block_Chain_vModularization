from blockchain_sandbox.engine.selfish_strategy import (
    SelfishStrategyContext,
    build_selfish_strategy,
)


def test_classic_strategy_core_states():
    s = build_selfish_strategy("classic")
    mine = s.decide(SelfishStrategyContext(event_kind="on_block_mined", private_lead=0))
    assert mine.publish_new_block is False
    assert mine.publish_private_blocks == 0

    r1 = s.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=1))
    assert r1.publish_private_blocks == 1
    r2 = s.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=2))
    assert r2.publish_private_blocks == 2
    r3 = s.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=5))
    assert r3.publish_private_blocks == 1


def test_stubborn_strategy_receive_rule():
    s = build_selfish_strategy("stubborn")
    r0 = s.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=0))
    r3 = s.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=3))
    assert r0.publish_private_blocks == 0
    assert r3.publish_private_blocks == 1


def test_social_strategy_reputation_switch():
    s = build_selfish_strategy("social")
    low_rep_mine = s.decide(SelfishStrategyContext(event_kind="on_block_mined", private_lead=0, reputation=-8.0))
    low_rep_recv = s.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=4, reputation=-8.0))
    assert low_rep_mine.publish_new_block is True
    assert low_rep_recv.publish_private_blocks == 4


def test_invalid_strategy_name_falls_back_to_classic():
    unknown = build_selfish_strategy("not_exist")
    ref = build_selfish_strategy("classic")
    a = unknown.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=2))
    b = ref.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=2))
    assert a.publish_private_blocks == b.publish_private_blocks
