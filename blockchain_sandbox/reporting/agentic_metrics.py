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
    economic_net_profit: float
    economic_roi: float
    economic_share: float
    economic_vs_hp_ratio: float
    top_actions: List[Tuple[str, int]]
    last_raw_action: str
    last_effective_action: str
    last_executed_action: str
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
    published_selfish_orphan_blocks: int
    ds_attempts: int
    ds_success_count: int
    ds_reorg_reverts: int
    ds_public_confirmed_count: int
    ds_conflict_released_count: int
    ds_confirmed_and_released_count: int
    ds_reverts_on_released_count: int
    merchant_loss_total: float
    attacker_net_profit: float
    economy_enabled_effective: bool
    selfish_hash_power_share: float
    selfish_economic_share: float
    selfish_ratio_economic: float
    selfish_net_profit_total: float
    network_net_profit_total: float
    selfish_initial_capital_total: float
    selfish_roi: float
    ratio_economic_signed: float
    strategy_constrained_rate: float
    persona_deviation_rate: float
    fallback_to_strategy_rate: float
    persona_deviation_impact_delta: float
    strategy_action_distribution: Dict[str, Dict[str, int]]
    raw_action_dist: Dict[str, int]
    effective_action_dist: Dict[str, int]
    executed_action_dist: Dict[str, int]
    audit_consistency: bool
    audit_mismatch_count: int


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
    
    canonical_set = _canonical_set(result)
    wasted_honest_blocks, unpublished_selfish_blocks, published_selfish_orphan_blocks = _orphan_breakdown(result, canonical_set)
            
    selfish_hash_power_share = _selfish_hash_power_share(result)
    selfish_economic_share = _selfish_economic_share(miner_details)
    selfish_ratio_economic = _safe_div(selfish_economic_share, selfish_hash_power_share)
    selfish_net_profit_total = _selfish_net_profit_total(miner_details)
    network_net_profit_total = _network_net_profit_total(miner_details)
    selfish_initial_capital_total = _selfish_initial_capital_total(result, miner_details)
    selfish_roi = _safe_div(selfish_net_profit_total, selfish_initial_capital_total)
    ratio_economic_signed = _signed_economic_ratio(selfish_net_profit_total, selfish_hash_power_share, network_net_profit_total)
    decision_audit = _decision_audit_summary(result, miner_details)

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
        published_selfish_orphan_blocks=published_selfish_orphan_blocks,
        ds_attempts=int(getattr(result, "economy_metrics", {}).get("ds_attempts", 0)),
        ds_success_count=int(getattr(result, "economy_metrics", {}).get("ds_success_count", 0)),
        ds_reorg_reverts=int(getattr(result, "economy_metrics", {}).get("ds_reorg_reverts", 0)),
        ds_public_confirmed_count=int(getattr(result, "economy_metrics", {}).get("ds_public_confirmed_count", 0)),
        ds_conflict_released_count=int(getattr(result, "economy_metrics", {}).get("ds_conflict_released_count", 0)),
        ds_confirmed_and_released_count=int(getattr(result, "economy_metrics", {}).get("ds_confirmed_and_released_count", 0)),
        ds_reverts_on_released_count=int(getattr(result, "economy_metrics", {}).get("ds_reverts_on_released_count", 0)),
        merchant_loss_total=float(getattr(result, "economy_metrics", {}).get("merchant_loss_total", 0.0)),
        attacker_net_profit=float(getattr(result, "economy_metrics", {}).get("attacker_net_profit", 0.0)),
        economy_enabled_effective=bool(getattr(result, "economy_metrics", {}).get("economy_enabled_effective", False)),
        selfish_hash_power_share=selfish_hash_power_share,
        selfish_economic_share=selfish_economic_share,
        selfish_ratio_economic=selfish_ratio_economic,
        selfish_net_profit_total=selfish_net_profit_total,
        network_net_profit_total=network_net_profit_total,
        selfish_initial_capital_total=selfish_initial_capital_total,
        selfish_roi=selfish_roi,
        ratio_economic_signed=ratio_economic_signed,
        strategy_constrained_rate=decision_audit["strategy_constrained_rate"],
        persona_deviation_rate=decision_audit["persona_deviation_rate"],
        fallback_to_strategy_rate=decision_audit["fallback_to_strategy_rate"],
        persona_deviation_impact_delta=decision_audit["persona_deviation_impact_delta"],
        strategy_action_distribution=decision_audit["strategy_action_distribution"],
        raw_action_dist=decision_audit["raw_action_dist"],
        effective_action_dist=decision_audit["effective_action_dist"],
        executed_action_dist=decision_audit["executed_action_dist"],
        audit_consistency=decision_audit["audit_consistency"],
        audit_mismatch_count=decision_audit["audit_mismatch_count"],
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
        f"  - Published Selfish Blocks (orphaned): {report.published_selfish_orphan_blocks}",
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
        "Double-Spend Settlement:",
        f"  - economy_enabled: {report.economy_enabled_effective}",
        f"  - ds_attempts: {report.ds_attempts}",
        f"  - ds_success_count: {report.ds_success_count}",
        f"  - ds_reorg_reverts: {report.ds_reorg_reverts}",
        f"  - ds_public_confirmed_count: {report.ds_public_confirmed_count}",
        f"  - ds_conflict_released_count: {report.ds_conflict_released_count}",
        f"  - ds_confirmed_and_released_count: {report.ds_confirmed_and_released_count}",
        f"  - ds_reverts_on_released_count: {report.ds_reverts_on_released_count}",
        f"  - merchant_loss_total: {report.merchant_loss_total:.4f}",
        f"  - attacker_net_profit: {report.attacker_net_profit:.4f}",
        "Economic Efficiency:",
        f"  - selfish_hash_power_share: {report.selfish_hash_power_share:.4f}",
        f"  - selfish_economic_share: {report.selfish_economic_share:.4f}",
        f"  - ratio_economic (econ_share/hash_power): {report.selfish_ratio_economic:.4f}",
        f"  - selfish_net_profit_total: {report.selfish_net_profit_total:.4f}",
        f"  - network_net_profit_total: {report.network_net_profit_total:.4f}",
        f"  - selfish_roi: {report.selfish_roi:.4f}",
        f"  - ratio_economic_signed: {report.ratio_economic_signed:.4f}",
        "Decision Audit:",
        f"  - strategy_constrained_rate: {report.strategy_constrained_rate:.2%}",
        f"  - persona_deviation_rate: {report.persona_deviation_rate:.2%}",
        f"  - fallback_to_strategy_rate: {report.fallback_to_strategy_rate:.2%}",
        f"  - persona_deviation_impact_delta: {report.persona_deviation_impact_delta:+.4f}",
        f"  - audit_consistency: {report.audit_consistency}",
        f"  - audit_mismatch_count: {report.audit_mismatch_count}",
        "Action Distribution (Raw):",
        "  - "
        + (
            ", ".join(
                f"{k}:{v}" for k, v in sorted(report.raw_action_dist.items(), key=lambda kv: kv[1], reverse=True)
            )
            if report.raw_action_dist
            else "none"
        ),
        "Action Distribution (Effective):",
        "  - "
        + (
            ", ".join(
                f"{k}:{v}" for k, v in sorted(report.effective_action_dist.items(), key=lambda kv: kv[1], reverse=True)
            )
            if report.effective_action_dist
            else "none"
        ),
        "Action Distribution (Executed):",
        "  - "
        + (
            ", ".join(
                f"{k}:{v}" for k, v in sorted(report.executed_action_dist.items(), key=lambda kv: kv[1], reverse=True)
            )
            if report.executed_action_dist
            else "none"
        ),
        "Strategy Action Distribution:",
    ])
    if report.strategy_action_distribution:
        for strategy_name, action_map in sorted(report.strategy_action_distribution.items()):
            parts = ", ".join(f"{k}:{v}" for k, v in sorted(action_map.items(), key=lambda kv: kv[1], reverse=True)[:8])
            lines.append(f"  - {strategy_name}: {parts if parts else 'none'}")
    else:
        lines.append("  - none")
    lines.append("Top miners by discovered blocks:")
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
            f"ratio(mined/hp)={d.mined_vs_hp_ratio:.2f} | ratio(canon/hp)={d.canonical_vs_hp_ratio:.2f} | "
            f"ratio(econ/hp)={d.economic_vs_hp_ratio:.2f}"
        )
        if d.top_actions:
            action_text = ", ".join(f"{a}:{c}" for a, c in d.top_actions)
            lines.append(f"  actions(executed): {action_text}")
        else:
            lines.append("  actions(executed): none")

        action_disp = d.last_executed_action
        if d.last_raw_action != d.last_effective_action:
            action_disp += f" (effective: {d.last_effective_action}; raw: {d.last_raw_action})"
            
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
    raw_action_count: Dict[str, int] = {}
    effective_action_count: Dict[str, int] = {}
    executed_action_count: Dict[str, int] = {}
    last_prompt: Dict[str, str] = {}
    last_raw_action: Dict[str, str] = {}
    last_effective_action: Dict[str, str] = {}
    last_executed_action: Dict[str, str] = {}
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
        exe_act = str(tr.get("executed_action", "")).strip() or eff_act
        reason = str(effective_decision.get("reason", "")).strip()
        up = str(tr.get("user_prompt", "")).strip()

        raw_action_count[raw_act] = raw_action_count.get(raw_act, 0) + 1
        effective_action_count[eff_act] = effective_action_count.get(eff_act, 0) + 1
        executed_action_count[exe_act] = executed_action_count.get(exe_act, 0) + 1
        action_count.setdefault(mid, {})
        action_count[mid][exe_act] = action_count[mid].get(exe_act, 0) + 1
        last_prompt[mid] = up
        last_raw_action[mid] = raw_act
        last_effective_action[mid] = eff_act
        last_executed_action[mid] = exe_act
        last_reason[mid] = reason

    details: List[MinerDetail] = []
    economy_metrics = getattr(result, "economy_metrics", {}) or {}
    econ_profit_map = economy_metrics.get("miner_net_profit", {}) if isinstance(economy_metrics, dict) else {}
    econ_initial_map = economy_metrics.get("miner_initial_capital", {}) if isinstance(economy_metrics, dict) else {}
    econ_share_map = economy_metrics.get("miner_economic_share", {}) if isinstance(economy_metrics, dict) else {}
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
        economic_net_profit = float(econ_profit_map.get(mid, 0.0)) if isinstance(econ_profit_map, dict) else 0.0
        economic_initial = float(econ_initial_map.get(mid, 0.0)) if isinstance(econ_initial_map, dict) else 0.0
        economic_roi = _safe_div(economic_net_profit, economic_initial)
        economic_share = float(econ_share_map.get(mid, 0.0)) if isinstance(econ_share_map, dict) else 0.0
        economic_vs_hp_ratio = (economic_share / node.hash_power) if node.hash_power > 0 else 0.0
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
                economic_net_profit=economic_net_profit,
                economic_roi=economic_roi,
                economic_share=economic_share,
                economic_vs_hp_ratio=economic_vs_hp_ratio,
                top_actions=actions,
                last_raw_action=last_raw_action.get(mid, "n/a"),
                last_effective_action=last_effective_action.get(mid, "n/a"),
                last_executed_action=last_executed_action.get(mid, last_effective_action.get(mid, "n/a")),
                last_reason=last_reason.get(mid, ""),
                last_prompt=last_prompt.get(mid, ""),
            )
        )
    return details


def _selfish_hash_power_share(result: AgenticSimulationResult) -> float:
    hp = 0.0
    for mid, node in result.nodes.items():
        if not node.is_miner:
            continue
        if node.strategy_name == "selfish":
            hp += node.hash_power
    return hp


def _selfish_economic_share(miner_details: List[MinerDetail]) -> float:
    share = 0.0
    for d in miner_details:
        if d.strategy == "selfish":
            share += d.economic_share
    return share


def _selfish_ratio_economic(result: AgenticSimulationResult, miner_details: List[MinerDetail]) -> float:
    hp_share = _selfish_hash_power_share(result)
    if hp_share <= 1e-12:
        return 0.0
    return _selfish_economic_share(miner_details) / hp_share


def _selfish_net_profit_total(miner_details: List[MinerDetail]) -> float:
    return sum(d.economic_net_profit for d in miner_details if d.strategy == "selfish")


def _network_net_profit_total(miner_details: List[MinerDetail]) -> float:
    return sum(d.economic_net_profit for d in miner_details)


def _selfish_initial_capital_total(result: AgenticSimulationResult, miner_details: List[MinerDetail]) -> float:
    eco = getattr(result, "economy_metrics", {}) or {}
    initial_map = eco.get("miner_initial_capital", {}) if isinstance(eco, dict) else {}
    if isinstance(initial_map, dict) and initial_map:
        total = 0.0
        for d in miner_details:
            if d.strategy != "selfish":
                continue
            total += float(initial_map.get(d.miner_id, 0.0))
        return total
    # Fallback for non-economy runs
    count = sum(1 for d in miner_details if d.strategy == "selfish")
    per = float(eco.get("initial_capital_per_miner", 0.0)) if isinstance(eco, dict) else 0.0
    return count * per


def _signed_economic_ratio(selfish_profit: float, selfish_hp_share: float, network_profit: float) -> float:
    if abs(selfish_hp_share) <= 1e-12 or abs(network_profit) <= 1e-12:
        return 0.0
    selfish_per_hp = selfish_profit / selfish_hp_share
    network_per_hp = network_profit  # total network hash-power share is 1
    return selfish_per_hp / network_per_hp


def _decision_audit_summary(result: AgenticSimulationResult, miner_details: List[MinerDetail]) -> Dict[str, object]:
    audited = 0
    constrained = 0
    deviated = 0
    fallback = 0
    by_strategy: Dict[str, Dict[str, int]] = {}
    raw_action_dist: Dict[str, int] = {}
    effective_action_dist: Dict[str, int] = {}
    executed_action_dist: Dict[str, int] = {}
    miner_detail_map = {d.miner_id: d for d in miner_details}
    dev_scores: List[float] = []
    base_scores: List[float] = []
    for tr in result.prompt_traces:
        raw_decision = tr.get("decision", {})
        if not isinstance(raw_decision, dict):
            raw_decision = {}
        effective_decision = tr.get("effective_decision", raw_decision)
        if not isinstance(effective_decision, dict):
            effective_decision = {}
        raw_action = str(raw_decision.get("action", "")).strip() or "unknown"
        effective_action = str(effective_decision.get("action", "")).strip() or raw_action
        executed_action = str(tr.get("executed_action", "")).strip() or effective_action
        raw_action_dist[raw_action] = raw_action_dist.get(raw_action, 0) + 1
        effective_action_dist[effective_action] = effective_action_dist.get(effective_action, 0) + 1
        executed_action_dist[executed_action] = executed_action_dist.get(executed_action, 0) + 1

        audit = tr.get("decision_audit", {})
        if not isinstance(audit, dict) or not audit:
            continue
        audited += 1
        if effective_action != executed_action:
            constrained += 1
        baseline_action = str(audit.get("baseline_action", "")).strip()
        deviation_reason = str(audit.get("deviation_reason", "")).strip().lower()
        if bool(audit.get("fallback_to_strategy", False)) or (baseline_action and executed_action == baseline_action and effective_action != baseline_action):
            fallback += 1
        is_persona_reason = deviation_reason.startswith("persona")
        if baseline_action and executed_action != baseline_action and is_persona_reason:
            deviated += 1
        strategy_name = str(audit.get("strategy_name", "unknown")).strip() or "unknown"
        action = executed_action
        by_strategy.setdefault(strategy_name, {})
        by_strategy[strategy_name][action] = by_strategy[strategy_name].get(action, 0) + 1
        miner_id = str(tr.get("miner_id", "")).strip()
        detail = miner_detail_map.get(miner_id)
        if detail is None:
            continue
        score = detail.canonical_vs_hp_ratio
        if bool(audit.get("persona_deviation", False)):
            dev_scores.append(score)
        else:
            base_scores.append(score)

    decision_calls = len(result.prompt_traces)
    executed_total = sum(executed_action_dist.values())
    mismatch_count = abs(executed_total - decision_calls)
    audit_consistency = mismatch_count == 0

    return {
        "strategy_constrained_rate": _safe_div(float(constrained), float(audited)),
        "persona_deviation_rate": _safe_div(float(deviated), float(audited)),
        "fallback_to_strategy_rate": _safe_div(float(fallback), float(audited)),
        "persona_deviation_impact_delta": (_avg(dev_scores) - _avg(base_scores)) if (dev_scores or base_scores) else 0.0,
        "strategy_action_distribution": by_strategy,
        "raw_action_dist": raw_action_dist,
        "effective_action_dist": effective_action_dist,
        "executed_action_dist": executed_action_dist,
        "audit_consistency": audit_consistency,
        "audit_mismatch_count": mismatch_count,
    }


def _avg(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _safe_div(a: float, b: float) -> float:
    if abs(b) <= 1e-12:
        return 0.0
    return a / b


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


def _orphan_breakdown(result: AgenticSimulationResult, canonical_set: set[str]) -> tuple[int, int, int]:
    wasted_honest = 0
    selfish_orphan_total = 0
    unpublished_selfish = 0

    for block in result.blocks.values():
        if block.miner_id == "genesis":
            continue
        if block.block_id in canonical_set:
            continue
        node = result.nodes.get(block.miner_id)
        if not node:
            continue
        if node.strategy_name == "honest":
            wasted_honest += 1
        elif node.strategy_name == "selfish":
            selfish_orphan_total += 1

    if hasattr(result, "private_chain_lengths") and result.private_chain_lengths:
        for count in result.private_chain_lengths.values():
            unpublished_selfish += int(count)

    published_selfish = max(0, selfish_orphan_total - unpublished_selfish)
    return wasted_honest, unpublished_selfish, published_selfish


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
