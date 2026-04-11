from blockchain_sandbox.engine.selfish_no_llm import (
    SelfishNoLLMConfig,
    SelfishState,
    advance_state_once,
    simulate_selfish_no_llm,
)
from blockchain_sandbox.engine.selfish_strategy import build_selfish_strategy


class StubRandom:
    def __init__(self, values):
        self.values = list(values)
        self.i = 0

    def random(self):
        if self.i >= len(self.values):
            return 0.0
        v = self.values[self.i]
        self.i += 1
        return v


def test_transition_zero_lead_honest_extends():
    rng = StubRandom([0.9])  # honest wins when alpha=0.35
    t = advance_state_once(
        SelfishState(lead=0, race=False),
        alpha=0.35,
        gamma=0.5,
        strategy=build_selfish_strategy("classic"),
        rng=rng,
    )
    assert t.next_state == SelfishState(lead=0, race=False)
    assert t.honest_gain == 1
    assert t.selfish_gain == 0


def test_transition_one_lead_to_race():
    rng = StubRandom([0.9])  # honest wins
    t = advance_state_once(
        SelfishState(lead=1, race=False),
        alpha=0.35,
        gamma=0.5,
        strategy=build_selfish_strategy("classic"),
        rng=rng,
    )
    assert t.next_state == SelfishState(lead=1, race=True)
    assert t.note == "publish_to_trigger_race"


def test_transition_two_plus_honest_causes_release():
    rng = StubRandom([0.9])  # honest wins
    t2 = advance_state_once(
        SelfishState(lead=2, race=False),
        alpha=0.35,
        gamma=0.5,
        strategy=build_selfish_strategy("classic"),
        rng=rng,
    )
    assert t2.next_state == SelfishState(lead=0, race=False)
    assert t2.selfish_gain == 2

    rng2 = StubRandom([0.9])  # honest wins
    t3 = advance_state_once(
        SelfishState(lead=4, race=False),
        alpha=0.35,
        gamma=0.5,
        strategy=build_selfish_strategy("classic"),
        rng=rng2,
    )
    assert t3.next_state == SelfishState(lead=3, race=False)
    assert t3.selfish_gain == 1


def test_gamma_boundaries_on_race_resolution():
    # honest wins first draw; second draw decides gamma-branch
    rng_gamma0 = StubRandom([0.9, 0.1])
    t0 = advance_state_once(
        SelfishState(lead=1, race=True),
        alpha=0.35,
        gamma=0.0,
        strategy=build_selfish_strategy("classic"),
        rng=rng_gamma0,
    )
    assert t0.selfish_gain == 0
    assert t0.honest_gain == 2

    rng_gamma1 = StubRandom([0.9, 0.9])
    t1 = advance_state_once(
        SelfishState(lead=1, race=True),
        alpha=0.35,
        gamma=1.0,
        strategy=build_selfish_strategy("classic"),
        rng=rng_gamma1,
    )
    assert t1.selfish_gain == 1
    assert t1.honest_gain == 1


def test_simulation_reproducible_with_fixed_seed():
    cfg = SelfishNoLLMConfig(alpha=0.35, gamma=0.5, target_blocks=1200, random_seed=123)
    a = simulate_selfish_no_llm(cfg)
    b = simulate_selfish_no_llm(cfg)
    assert a.selfish_blocks == b.selfish_blocks
    assert a.honest_blocks == b.honest_blocks
    assert a.theory_gap_abs == b.theory_gap_abs


def test_selfish_share_increases_with_alpha():
    low = simulate_selfish_no_llm(SelfishNoLLMConfig(alpha=0.2, gamma=0.5, target_blocks=3000, random_seed=7))
    high = simulate_selfish_no_llm(SelfishNoLLMConfig(alpha=0.35, gamma=0.5, target_blocks=3000, random_seed=7))
    assert high.simulated_selfish_share > low.simulated_selfish_share


def test_nonclassic_strategy_disables_theory_match():
    res = simulate_selfish_no_llm(
        SelfishNoLLMConfig(alpha=0.35, gamma=0.5, target_blocks=500, random_seed=7, strategy_name="stubborn")
    )
    assert res.theoretical_selfish_share is None
    assert res.theory_gap_abs is None
    assert res.theory_match is None
