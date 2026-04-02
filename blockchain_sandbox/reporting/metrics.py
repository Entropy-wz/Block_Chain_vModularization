from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..engine.simulation import SimulationResult


@dataclass(frozen=True)
class Report:
    total_blocks: int
    canonical_height: int
    orphan_blocks: int
    orphan_ratio: float
    fork_events: int
    avg_out_degree: float
    top_miners: List[Tuple[str, int]]
    strategy_distribution: Dict[str, int]


def build_report(result: SimulationResult) -> Report:
    canonical_head = result.canonical_head_id
    canonical_height = result.blocks[canonical_head].height
    total_blocks = len(result.blocks)
    orphan_blocks = result.orphan_blocks
    orphan_ratio = orphan_blocks / total_blocks if total_blocks else 0.0

    out_degrees = [result.graph.out_degree(nid) for nid in result.nodes]
    avg_out_degree = sum(out_degrees) / len(out_degrees) if out_degrees else 0.0

    top_miners = sorted(
        result.block_wins_by_miner.items(),
        key=lambda kv: kv[1],
        reverse=True,
    )[:5]

    strategy_distribution: Dict[str, int] = {}
    for node in result.nodes.values():
        if node.is_miner:
            strategy_distribution[node.strategy_name] = strategy_distribution.get(node.strategy_name, 0) + 1

    return Report(
        total_blocks=total_blocks,
        canonical_height=canonical_height,
        orphan_blocks=orphan_blocks,
        orphan_ratio=orphan_ratio,
        fork_events=result.fork_events,
        avg_out_degree=avg_out_degree,
        top_miners=top_miners,
        strategy_distribution=strategy_distribution,
    )


def format_report(report: Report) -> str:
    lines = [
        "=== Blockchain Graph Sandbox Report ===",
        f"Total blocks: {report.total_blocks}",
        f"Canonical chain height: {report.canonical_height}",
        f"Orphan blocks: {report.orphan_blocks} ({report.orphan_ratio:.2%})",
        f"Fork events: {report.fork_events}",
        f"Average out-degree: {report.avg_out_degree:.2f}",
        "Top miners by produced blocks:",
    ]
    for miner_id, wins in report.top_miners:
        lines.append(f"  - {miner_id}: {wins}")

    lines.append("Miner strategy distribution:")
    for name, count in sorted(report.strategy_distribution.items()):
        lines.append(f"  - {name}: {count}")
    return "\n".join(lines)
