from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Tuple

from ..engine.agentic_simulation import AgenticSimulationResult
from ..modules.metrics_module import BlockWindowSnapshot


@dataclass(frozen=True)
class MinerDetail:
    miner_id: str
    strategy: str
    hash_power: float
    mined_blocks: int
    canonical_blocks: int
    orphan_blocks: int
    orphan_ratio: float
    mined_share: float
    canonical_share: float
    mined_vs_hp_ratio: float
    canonical_vs_hp_ratio: float
    top_actions: List[Tuple[str, int]]
    last_raw_action: str
    last_effective_action: str
    last_reason: str
    last_prompt: str


@dataclass(frozen=True)
class AgenticReport:
    total_blocks: int
    canonical_height: int
    heaviest_head: str
    orphan_blocks: int
    orphan_ratio: float
    fork_events: int
    jam_events: int
    network_efficiency: float
    top_miners: List[Tuple[str, int]]
    selfish_gamma: Dict[str, float]
    snapshots: List[BlockWindowSnapshot]
    forum_post_count: int
    forum_hottest_board: str
    lowest_reputation: List[Tuple[str, float]]
    miner_details: List[MinerDetail]
    snapshot_interval_blocks: int
    total_decisions: int
    fallback_decisions: int
    corr_hashpower_mined_share: float
    corr_hashpower_canonical_share: float
    mae_hashpower_vs_mined_share: float
    mae_hashpower_vs_canonical_share: float
    wasted_honest_blocks: int
    unpublished_selfish_blocks: int


def build_agentic_report(result: AgenticSimulationResult) -> AgenticReport:
    head = result.canonical_head_id
    canonical_height = result.blocks[head].height
    total_blocks = len(result.blocks)
    heaviest = getattr(result, "heaviest_head_id", head)
    orphan = result.orphan_blocks
    ratio = orphan / total_blocks if total_blocks else 0.0
    top_miners = sorted(result.block_wins_by_miner.items(), key=lambda kv: kv[1], reverse=True)[:6]

    miner_details = _build_miner_details(result)
    hp = [d.hash_power for d in miner_details]
    mined_share = [d.mined_share for d in miner_details]
    canon_share = [d.canonical_share for d in miner_details]
    total_decisions = len(result.prompt_traces)
    fallback_decisions = sum(1 for tr in result.prompt_traces if bool(tr.get("fallback", False)))
    
    # Calculate Wasted Honest Blocks & Unpublished Selfish Blocks
    wasted_honest_blocks = 0
    unpublished_selfish_blocks = 0
    
    canonical_set = _canonical_set(result)
    for block in result.blocks.values():
        if block.miner_id == "genesis": continue
        node = result.nodes.get(block.miner_id)
        if node and node.strategy_name == "honest" and block.block_id not in canonical_set:
            wasted_honest_blocks += 1
            
    if hasattr(result, "private_chain_lengths") and result.private_chain_lengths:
        for count in result.private_chain_lengths.values():
            unpublished_selfish_blocks += count
            
    return AgenticReport(
        total_blocks=total_blocks,
        canonical_height=canonical_height,
        heaviest_head=heaviest,
        orphan_blocks=orphan,
        orphan_ratio=ratio,
        fork_events=result.fork_events,
        jam_events=result.jam_events,
        network_efficiency=result.network_efficiency,
        top_miners=top_miners,
        selfish_gamma=result.gamma_estimates,
        snapshots=result.snapshots,
        forum_post_count=result.forum_post_count,
        forum_hottest_board=_hottest_board(result) if result.forum_post_count > 0 else "none",
        lowest_reputation=sorted(result.final_reputation.items(), key=lambda kv: kv[1])[:4] if result.final_reputation else [],
        miner_details=miner_details,
        snapshot_interval_blocks=result.config.snapshot_interval_blocks,
        total_decisions=total_decisions,
        fallback_decisions=fallback_decisions,
        corr_hashpower_mined_share=_corr(hp, mined_share),
        corr_hashpower_canonical_share=_corr(hp, canon_share),
        mae_hashpower_vs_mined_share=_mae(hp, mined_share),
        mae_hashpower_vs_canonical_share=_mae(hp, canon_share),
        wasted_honest_blocks=wasted_honest_blocks,
        unpublished_selfish_blocks=unpublished_selfish_blocks,
    )


def format_agentic_report(report: AgenticReport) -> str:
    if report.total_decisions:
        decision_line = (
            f"Decision calls: {report.total_decisions} "
            f"(fallback={report.fallback_decisions}, "
            f"rate={(report.fallback_decisions / report.total_decisions):.2%})"
        )
    else:
        decision_line = "Decision calls: 0 (fallback=0, rate=0.00%)"

    lines = [
        "=== LLM Agentic Blockchain Sandbox Report ===",
        f"Total blocks: {report.total_blocks}",
        f"Canonical chain height: {report.canonical_height} (heaviest: {report.heaviest_head})",
        f"Orphan blocks: {report.orphan_blocks} ({report.orphan_ratio:.2%})",
        f"  - Wasted Honest Blocks (orphaned): {report.wasted_honest_blocks}",
        f"  - Unpublished Selfish Blocks (hoarded): {report.unpublished_selfish_blocks}",
        f"Fork events: {report.fork_events}",
        f"Social jam events: {report.jam_events}",
        f"Network avg shortest latency: {report.network_efficiency:.3f}",
    ]
    if report.forum_hottest_board != "none" or report.forum_post_count > 0:
        lines.append(f"Forum posts: {report.forum_post_count}")
        lines.append(f"Forum hottest board: {report.forum_hottest_board}")
    else:
        lines.append("Forum posts: Disabled/None")
        
    lines.extend([
        decision_line,
        "Reward-Fairness Check:",
        f"  - corr(hash_power, mined_share): {report.corr_hashpower_mined_share:.3f}",
        f"  - corr(hash_power, canonical_share): {report.corr_hashpower_canonical_share:.3f}",
        f"  - mae(hash_power vs mined_share): {report.mae_hashpower_vs_mined_share:.4f}",
        f"  - mae(hash_power vs canonical_share): {report.mae_hashpower_vs_canonical_share:.4f}",
        "Top miners by discovered blocks:",
    ])
    for mid, c in report.top_miners:
        lines.append(f"  - {mid}: {c}")
    lines.append("Selfish-miner gamma estimates:")
    if report.selfish_gamma:
        for mid, g in sorted(report.selfish_gamma.items()):
            lines.append(f"  - {mid}: {g:.3f}")
    else:
        lines.append("  - none")
    if report.lowest_reputation:
        lines.append("Lowest reputation miners:")
        for mid, rep in report.lowest_reputation:
            lines.append(f"  - {mid}: {rep:+.2f}")
    return "\n".join(lines)


def format_snapshots(report: AgenticReport) -> str:
    if not report.snapshots:
        return (
            f"=== Process Snapshots (every {report.snapshot_interval_blocks} blocks) ===\n"
            "No snapshots captured. "
            f"Reason: mined blocks did not reach interval ({report.snapshot_interval_blocks})."
        )

    lines = [f"=== Process Snapshots (every {report.snapshot_interval_blocks} blocks) ==="]
    for snap in report.snapshots:
        lines.append(
            f"[step={snap.step}] mined={snap.mined_block_count}, "
            f"window_orphans={snap.window_orphan_count}/"
            f"{len(snap.window_block_ids)}, canon={snap.canonical_head_id}, heavy={getattr(snap, 'heaviest_head_id', 'N/A')}"
        )
        lines.append(
            f"  forum: posts={snap.forum_window_posts}, avg_tone={snap.forum_window_avg_tone:+.2f}, "
            f"hot_board={snap.forum_hot_board}, top_target={snap.forum_top_target}"
        )
        lines.append(
            f"  structure: max_fork_degree={snap.max_fork_degree}, longest_branch_len={snap.longest_branch_len}, "
            f"branch_count={snap.branch_count}, canonical_coverage={snap.canonical_coverage:.1%}"
        )
        for tree_line in snap.tree_lines:
            lines.append(f"  {tree_line}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_miner_details(report: AgenticReport) -> str:
    lines = ["=== Miner Detail Summary ==="]
    for d in report.miner_details:
        lines.append(
            f"- {d.miner_id} | strategy={d.strategy} | hp={d.hash_power:.4f} | "
            f"mined={d.mined_blocks} | canonical={d.canonical_blocks} | "
            f"orphans={d.orphan_blocks} ({d.orphan_ratio:.1%}) | "
            f"ratio(mined/hp)={d.mined_vs_hp_ratio:.2f} | ratio(canon/hp)={d.canonical_vs_hp_ratio:.2f}"
        )
        if d.top_actions:
            action_text = ", ".join(f"{a}:{c}" for a, c in d.top_actions)
            lines.append(f"  actions(effective): {action_text}")
        else:
            lines.append("  actions(effective): none")
        
        action_disp = d.last_effective_action
        if d.last_raw_action != d.last_effective_action:
            action_disp += f" (raw: {d.last_raw_action})"
            
        lines.append(f"  last_action: {action_disp}")
        lines.append(f"  last_reason: {_shorten(d.last_reason, 180)}")
        lines.append(f"  last_prompt: {_shorten(d.last_prompt, 220)}")
    return "\n".join(lines)


def _hottest_board(result: AgenticSimulationResult) -> str:
    if not result.forum_board_heat:
        return "mining"
    return max(result.forum_board_heat.items(), key=lambda kv: kv[1])[0]


def format_forum_panel(report: AgenticReport) -> str:
    if report.forum_post_count == 0 and not report.lowest_reputation:
        return "=== Tieba Opinion Panel ===\n(Forum module disabled or inactive)"
        
    lines = [
        "=== Tieba Opinion Panel ===",
        f"Total posts: {report.forum_post_count}",
        f"Hottest board: {report.forum_hottest_board}",
        "Most pressured miners (low reputation):",
    ]
    if report.lowest_reputation:
        for mid, rep in report.lowest_reputation:
            lines.append(f"  - {mid}: {rep:+.2f}")
    else:
        lines.append("  - none")

    lines.append("Opinion timeline by block-window:")
    if report.snapshots:
        for snap in report.snapshots:
            lines.append(
                f"  - step={snap.step}, mined={snap.mined_block_count}, posts={snap.forum_window_posts}, "
                f"tone={snap.forum_window_avg_tone:+.2f}, board={snap.forum_hot_board}, target={snap.forum_top_target}, "
                f"fork={snap.max_fork_degree}, longest={snap.longest_branch_len}, "
                f"branches={snap.branch_count}, canon={snap.canonical_coverage:.1%}"
            )
    else:
        lines.append("  - no snapshots")
    return "\n".join(lines)


def _build_miner_details(result: AgenticSimulationResult) -> List[MinerDetail]:
    canonical = _canonical_set(result)
    by_miner_mined: Dict[str, int] = {}
    by_miner_canonical: Dict[str, int] = {}
    for block in result.blocks.values():
        if block.miner_id == "genesis":
            continue
        by_miner_mined[block.miner_id] = by_miner_mined.get(block.miner_id, 0) + 1
        if block.block_id in canonical:
            by_miner_canonical[block.miner_id] = by_miner_canonical.get(block.miner_id, 0) + 1

    action_count: Dict[str, Dict[str, int]] = {}
    last_prompt: Dict[str, str] = {}
    last_raw_action: Dict[str, str] = {}
    last_effective_action: Dict[str, str] = {}
    last_reason: Dict[str, str] = {}
    for tr in result.prompt_traces:
        mid = str(tr.get("miner_id", "")).strip()
        if not mid:
            continue
        raw_decision = tr.get("decision", {})
        if not isinstance(raw_decision, dict):
            raw_decision = {}
        effective_decision = tr.get("effective_decision", raw_decision)
        if not isinstance(effective_decision, dict):
            effective_decision = {}
            
        raw_act = str(raw_decision.get("action", "")).strip() or "unknown"
        eff_act = str(effective_decision.get("action", "")).strip() or "unknown"
        reason = str(effective_decision.get("reason", "")).strip()
        up = str(tr.get("user_prompt", "")).strip()
        
        action_count.setdefault(mid, {})
        action_count[mid][eff_act] = action_count[mid].get(eff_act, 0) + 1
        last_prompt[mid] = up
        last_raw_action[mid] = raw_act
        last_effective_action[mid] = eff_act
        last_reason[mid] = reason

    details: List[MinerDetail] = []
    total_mined = sum(by_miner_mined.values()) or 1
    total_canonical = sum(by_miner_canonical.values()) or 1
    miner_ids = sorted([nid for nid, node in result.nodes.items() if node.is_miner], key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    for mid in miner_ids:
        node = result.nodes[mid]
        mined = by_miner_mined.get(mid, 0)
        canon = by_miner_canonical.get(mid, 0)
        orphan = max(0, mined - canon)
        ratio = (orphan / mined) if mined else 0.0
        mined_share = mined / total_mined
        canonical_share = canon / total_canonical
        mined_vs_hp_ratio = (mined_share / node.hash_power) if node.hash_power > 0 else 0.0
        canonical_vs_hp_ratio = (canonical_share / node.hash_power) if node.hash_power > 0 else 0.0
        actions = sorted(action_count.get(mid, {}).items(), key=lambda kv: kv[1], reverse=True)[:5]
        details.append(
            MinerDetail(
                miner_id=mid,
                strategy=node.strategy_name,
                hash_power=node.hash_power,
                mined_blocks=mined,
                canonical_blocks=canon,
                orphan_blocks=orphan,
                orphan_ratio=ratio,
                mined_share=mined_share,
                canonical_share=canonical_share,
                mined_vs_hp_ratio=mined_vs_hp_ratio,
                canonical_vs_hp_ratio=canonical_vs_hp_ratio,
                top_actions=actions,
                last_raw_action=last_raw_action.get(mid, "n/a"),
                last_effective_action=last_effective_action.get(mid, "n/a"),
                last_reason=last_reason.get(mid, ""),
                last_prompt=last_prompt.get(mid, ""),
            )
        )
    return details


def _canonical_set(result: AgenticSimulationResult) -> set[str]:
    out: set[str] = set()
    cur = result.canonical_head_id
    while cur is not None and cur in result.blocks:
        out.add(cur)
        cur = result.blocks[cur].parent_id
    return out


def _shorten(text: str, max_len: int) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return t[: max(0, max_len - 3)] + "..."


def _corr(xs: List[float], ys: List[float]) -> float:
    if not xs or len(xs) != len(ys):
        return 0.0
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return cov / math.sqrt(vx * vy)


def _mae(xs: List[float], ys: List[float]) -> float:
    if not xs or len(xs) != len(ys):
        return 0.0
    return sum(abs(xs[i] - ys[i]) for i in range(len(xs))) / len(xs)
