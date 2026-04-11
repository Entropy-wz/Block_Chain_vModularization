from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Dict, List, Optional, Tuple

from .selfish_strategy import SelfishStrategy, SelfishStrategyContext, build_selfish_strategy


@dataclass(frozen=True)
class SelfishNoLLMConfig:
    alpha: float = 0.35
    gamma: float = 0.5
    target_blocks: int = 5000
    random_seed: int = 11
    strategy_name: str = "classic"


@dataclass(frozen=True)
class SelfishStepRecord:
    step: int
    lead_before: int
    race_before: bool
    winner: str
    lead_after: int
    race_after: bool
    selfish_gain: int
    honest_gain: int
    note: str


@dataclass(frozen=True)
class SelfishNoLLMResult:
    config: SelfishNoLLMConfig
    selfish_blocks: int
    honest_blocks: int
    simulated_selfish_share: float
    theoretical_selfish_share: Optional[float]
    theory_gap_abs: Optional[float]
    theory_match: Optional[bool]
    total_events: int
    lead_histogram: Dict[int, int]
    race_entries: int
    final_private_lead: int
    steps: List[SelfishStepRecord]


@dataclass(frozen=True)
class SelfishState:
    lead: int = 0
    race: bool = False


@dataclass(frozen=True)
class SelfishTransition:
    next_state: SelfishState
    winner: str
    selfish_gain: int
    honest_gain: int
    note: str


def simulate_selfish_no_llm(
    config: SelfishNoLLMConfig,
    theory_gap_threshold: float = 0.03,
) -> SelfishNoLLMResult:
    alpha = _clamp(config.alpha, 0.0, 0.499999)
    gamma = _clamp(config.gamma, 0.0, 1.0)
    target_blocks = max(1, int(config.target_blocks))
    strategy_name = (config.strategy_name or "classic").strip().lower() or "classic"
    strategy = build_selfish_strategy(strategy_name, reputation_provider=None)
    rng = Random(config.random_seed)

    selfish_blocks = 0
    honest_blocks = 0
    lead = 0
    race = False
    total_events = 0
    race_entries = 0
    lead_histogram: Dict[int, int] = {}
    records: List[SelfishStepRecord] = []

    while selfish_blocks + honest_blocks < target_blocks:
        total_events += 1
        lead_before = lead
        race_before = race
        lead_histogram[lead_before] = lead_histogram.get(lead_before, 0) + 1

        trans = advance_state_once(
            state=SelfishState(lead=lead, race=race),
            alpha=alpha,
            gamma=gamma,
            strategy=strategy,
            rng=rng,
        )
        winner = trans.winner
        selfish_gain = trans.selfish_gain
        honest_gain = trans.honest_gain
        note = trans.note
        lead = trans.next_state.lead
        race = trans.next_state.race
        if note == "publish_to_trigger_race":
            race_entries += 1

        selfish_blocks += selfish_gain
        honest_blocks += honest_gain

        if selfish_blocks + honest_blocks > target_blocks:
            overflow = selfish_blocks + honest_blocks - target_blocks
            if selfish_gain >= overflow:
                selfish_blocks -= overflow
                selfish_gain -= overflow
            else:
                rem = overflow - selfish_gain
                selfish_blocks -= selfish_gain
                selfish_gain = 0
                honest_blocks -= rem
                honest_gain -= rem

        records.append(
            SelfishStepRecord(
                step=total_events,
                lead_before=lead_before,
                race_before=race_before,
                winner=winner,
                lead_after=lead,
                race_after=race,
                selfish_gain=selfish_gain,
                honest_gain=honest_gain,
                note=note,
            )
        )

    simulated_share = selfish_blocks / max(1, selfish_blocks + honest_blocks)
    theoretical_share: Optional[float]
    gap: Optional[float]
    match: Optional[bool]
    if strategy_name == "classic":
        theoretical_share = theoretical_selfish_share(alpha=alpha, gamma=gamma)
        gap = abs(simulated_share - theoretical_share)
        match = gap <= max(0.0, theory_gap_threshold)
    else:
        theoretical_share = None
        gap = None
        match = None

    return SelfishNoLLMResult(
        config=SelfishNoLLMConfig(
            alpha=alpha,
            gamma=gamma,
            target_blocks=target_blocks,
            random_seed=config.random_seed,
            strategy_name=strategy_name,
        ),
        selfish_blocks=selfish_blocks,
        honest_blocks=honest_blocks,
        simulated_selfish_share=simulated_share,
        theoretical_selfish_share=theoretical_share,
        theory_gap_abs=gap,
        theory_match=match,
        total_events=total_events,
        lead_histogram=lead_histogram,
        race_entries=race_entries,
        final_private_lead=lead,
        steps=records,
    )


def advance_state_once(
    state: SelfishState,
    alpha: float,
    gamma: float,
    strategy: SelfishStrategy,
    rng: Random,
) -> SelfishTransition:
    a = _clamp(alpha, 0.0, 0.499999)
    g = _clamp(gamma, 0.0, 1.0)
    selfish_win = rng.random() < a
    winner = "selfish" if selfish_win else "honest"

    lead = max(0, int(state.lead))
    race = bool(state.race)

    selfish_gain = 0
    honest_gain = 0
    note = ""

    if race:
        if selfish_win:
            selfish_gain = 2
            note = "race_resolved_selfish"
        else:
            if rng.random() < g:
                selfish_gain = 1
                honest_gain = 1
                note = "race_resolved_honest_on_selfish_branch"
            else:
                honest_gain = 2
                note = "race_resolved_honest_on_honest_branch"
        return SelfishTransition(
            next_state=SelfishState(lead=0, race=False),
            winner=winner,
            selfish_gain=selfish_gain,
            honest_gain=honest_gain,
            note=note,
        )

    if selfish_win:
        plan = strategy.decide(SelfishStrategyContext(event_kind="on_block_mined", private_lead=lead, reputation=0.0))
        release = max(0, min(int(plan.publish_private_blocks), lead))
        selfish_gain += release
        lead -= release
        if plan.publish_new_block:
            selfish_gain += 1
            note = "mine_publish_new"
        else:
            lead += 1
            note = "mine_withhold_new"
        return SelfishTransition(
            next_state=SelfishState(lead=lead, race=False),
            winner=winner,
            selfish_gain=selfish_gain,
            honest_gain=honest_gain,
            note=note,
        )

    # honest winner and no race
    plan = strategy.decide(SelfishStrategyContext(event_kind="on_block_received", private_lead=lead, reputation=0.0))
    release = max(0, min(int(plan.publish_private_blocks), lead))
    if release <= 0:
        honest_gain += 1
        note = "honest_extends_public"
        return SelfishTransition(
            next_state=SelfishState(lead=lead, race=False),
            winner=winner,
            selfish_gain=selfish_gain,
            honest_gain=honest_gain,
            note=note,
        )

    if lead == 1 and release >= 1:
        note = "publish_to_trigger_race"
        return SelfishTransition(
            next_state=SelfishState(lead=1, race=True),
            winner=winner,
            selfish_gain=0,
            honest_gain=0,
            note=note,
        )

    selfish_gain += release
    lead -= release
    note = "release_private_on_receive"
    return SelfishTransition(
        next_state=SelfishState(lead=lead, race=False),
        winner=winner,
        selfish_gain=selfish_gain,
        honest_gain=honest_gain,
        note=note,
    )


def theoretical_selfish_share(alpha: float, gamma: float, max_lead_state: int = 24) -> float:
    a = _clamp(alpha, 0.0, 0.499999)
    g = _clamp(gamma, 0.0, 1.0)
    k = max(4, int(max_lead_state))

    state_names: List[str] = ["s0", "s1"] + [f"s{i}" for i in range(2, k + 1)] + ["s0p"]
    idx = {name: i for i, name in enumerate(state_names)}
    n = len(state_names)

    p = [[0.0 for _ in range(n)] for _ in range(n)]
    r_selfish = [0.0 for _ in range(n)]
    r_honest = [0.0 for _ in range(n)]

    def add(from_s: str, to_s: str, prob: float, rs: float, rh: float) -> None:
        i = idx[from_s]
        j = idx[to_s]
        p[i][j] += prob
        r_selfish[i] += prob * rs
        r_honest[i] += prob * rh

    add("s0", "s1", a, 0.0, 0.0)
    add("s0", "s0", 1.0 - a, 0.0, 1.0)

    add("s1", "s2", a, 0.0, 0.0)
    add("s1", "s0p", 1.0 - a, 0.0, 0.0)

    for lead in range(2, k):
        cur = f"s{lead}"
        nxt = f"s{lead + 1}"
        add(cur, nxt, a, 0.0, 0.0)
        if lead == 2:
            add(cur, "s0", 1.0 - a, 2.0, 0.0)
        else:
            add(cur, f"s{lead - 1}", 1.0 - a, 1.0, 0.0)

    add(f"s{k}", f"s{k}", a, 0.0, 0.0)
    add(f"s{k}", f"s{k - 1}", 1.0 - a, 1.0, 0.0)

    add("s0p", "s0", a, 2.0, 0.0)
    add("s0p", "s0", (1.0 - a) * g, 1.0, 1.0)
    add("s0p", "s0", (1.0 - a) * (1.0 - g), 0.0, 2.0)

    pi = _stationary_distribution(p)
    exp_selfish = sum(pi[i] * r_selfish[i] for i in range(n))
    exp_honest = sum(pi[i] * r_honest[i] for i in range(n))
    return exp_selfish / max(1e-12, (exp_selfish + exp_honest))


def _stationary_distribution(p: List[List[float]]) -> List[float]:
    n = len(p)
    pi = [1.0 / n for _ in range(n)]
    for _ in range(10000):
        nxt = [0.0 for _ in range(n)]
        for i in range(n):
            row = p[i]
            for j in range(n):
                nxt[j] += pi[i] * row[j]
        s = sum(nxt) or 1.0
        nxt = [x / s for x in nxt]
        diff = sum(abs(nxt[i] - pi[i]) for i in range(n))
        pi = nxt
        if diff < 1e-14:
            break
    return pi


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
