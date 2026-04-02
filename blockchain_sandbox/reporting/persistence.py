from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .agentic_metrics import AgenticReport
from ..engine.agentic_simulation import AgenticSimulationResult
from .tree_visualization import generate_tree_pngs


import os

def export_run_artifacts(
    result: AgenticSimulationResult,
    report: AgenticReport,
    output_root: str = "outputs",
    export_prompts: bool = True,
) -> Path:
    run_dir = _build_run_dir(output_root)
    
    # Create subdirectories for categorized output
    data_dir = run_dir / "data"
    reports_dir = run_dir / "reports"
    viz_dir = run_dir / "visualizations"
    
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    viz_dir.mkdir(parents=True, exist_ok=True)

    _write_summary_json(reports_dir / "summary.json", result, report)
    _write_blocks_jsonl(data_dir / "blocks.jsonl", result)
    _write_forum_posts_jsonl(data_dir / "forum_posts.jsonl", result)
    _write_snapshots_csv(reports_dir / "window_snapshots.csv", result)
    _write_miner_details_csv(reports_dir / "miner_details.csv", report)
    _write_private_events_jsonl(data_dir / "private_events.jsonl", result)
    generate_tree_pngs(result, viz_dir)
    if export_prompts:
        _write_prompt_traces_jsonl(data_dir / "prompt_traces.jsonl", result)

    return run_dir


def _build_run_dir(output_root: str) -> Path:
    group = os.getenv("SANDBOX_EXPERIMENT_GROUP", "default").strip()
    date_str = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%H%M%S")
    return Path(output_root) / group / date_str / f"run_{stamp}"


def _write_summary_json(path: Path, result: AgenticSimulationResult, report: AgenticReport) -> None:
    payload: Dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "config": asdict(result.config),
        "headline_metrics": {
            "total_blocks": report.total_blocks,
            "canonical_height": report.canonical_height,
            "canonical_head_id": result.canonical_head_id,
            "orphan_blocks": report.orphan_blocks,
            "orphan_ratio": report.orphan_ratio,
            "fork_events": report.fork_events,
            "jam_events": report.jam_events,
            "network_efficiency": report.network_efficiency,
            "forum_post_count": report.forum_post_count,
            "forum_hottest_board": report.forum_hottest_board,
        },
        "top_miners": [{"miner_id": mid, "discovered_blocks": c} for mid, c in report.top_miners],
        "selfish_gamma": result.gamma_estimates,
        "final_reputation": result.final_reputation,
        "miner_details": [
            {
                "miner_id": d.miner_id,
                "strategy": d.strategy,
                "hash_power": d.hash_power,
                "mined_blocks": d.mined_blocks,
                "canonical_blocks": d.canonical_blocks,
                "orphan_blocks": d.orphan_blocks,
                "orphan_ratio": d.orphan_ratio,
                "mined_share": d.mined_share,
                "canonical_share": d.canonical_share,
                "mined_vs_hp_ratio": d.mined_vs_hp_ratio,
                "canonical_vs_hp_ratio": d.canonical_vs_hp_ratio,
                "top_actions": d.top_actions,
                "last_raw_action": d.last_raw_action,
                "last_effective_action": d.last_effective_action,
                "last_reason": d.last_reason,
                "last_prompt": d.last_prompt,
            }
            for d in report.miner_details
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_blocks_jsonl(path: Path, result: AgenticSimulationResult) -> None:
    canonical = _canonical_set(result)
    ordered = sorted(result.blocks.values(), key=lambda b: int(b.block_id[1:]) if b.block_id.startswith("B") else b.created_at_step)
    with path.open("w", encoding="utf-8", newline="") as f:
        for b in ordered:
            row = {
                "block_id": b.block_id,
                "parent_id": b.parent_id,
                "height": b.height,
                "miner_id": b.miner_id,
                "created_at_step": b.created_at_step,
                "is_canonical": b.block_id in canonical,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_forum_posts_jsonl(path: Path, result: AgenticSimulationResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        for p in result.forum_posts:
            row = {
                "post_id": p.post_id,
                "step": p.step,
                "author_id": p.author_id,
                "board": p.board,
                "tone": p.tone,
                "target_id": p.target_id,
                "content": p.content,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_prompt_traces_jsonl(path: Path, result: AgenticSimulationResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        for item in result.prompt_traces:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _write_private_events_jsonl(path: Path, result: AgenticSimulationResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        for item in getattr(result, "private_chain_events", []):
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _write_snapshots_csv(path: Path, result: AgenticSimulationResult) -> None:
    fieldnames = [
        "step",
        "mined_block_count",
        "window_blocks",
        "window_orphan_count",
        "canonical_head_id",
        "canonical_coverage",
        "max_fork_degree",
        "longest_branch_len",
        "branch_count",
        "forum_window_posts",
        "forum_window_avg_tone",
        "forum_hot_board",
        "forum_top_target",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in result.snapshots:
            writer.writerow(
                {
                    "step": s.step,
                    "mined_block_count": s.mined_block_count,
                    "window_blocks": len(s.window_block_ids),
                    "window_orphan_count": s.window_orphan_count,
                    "canonical_head_id": s.canonical_head_id,
                    "canonical_coverage": f"{s.canonical_coverage:.6f}",
                    "max_fork_degree": s.max_fork_degree,
                    "longest_branch_len": s.longest_branch_len,
                    "branch_count": s.branch_count,
                    "forum_window_posts": s.forum_window_posts,
                    "forum_window_avg_tone": f"{s.forum_window_avg_tone:.6f}",
                    "forum_hot_board": s.forum_hot_board,
                    "forum_top_target": s.forum_top_target,
                }
            )


def _write_miner_details_csv(path: Path, report: AgenticReport) -> None:
    fieldnames = [
        "miner_id",
        "strategy",
        "hash_power",
        "mined_blocks",
        "canonical_blocks",
        "orphan_blocks",
        "orphan_ratio",
        "mined_share",
        "canonical_share",
        "mined_vs_hp_ratio",
        "canonical_vs_hp_ratio",
        "top_actions",
        "last_raw_action",
        "last_effective_action",
        "last_reason",
        "last_prompt",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for d in report.miner_details:
            writer.writerow(
                {
                    "miner_id": d.miner_id,
                    "strategy": d.strategy,
                    "hash_power": f"{d.hash_power:.8f}",
                    "mined_blocks": d.mined_blocks,
                    "canonical_blocks": d.canonical_blocks,
                    "orphan_blocks": d.orphan_blocks,
                    "orphan_ratio": f"{d.orphan_ratio:.8f}",
                    "mined_share": f"{d.mined_share:.8f}",
                    "canonical_share": f"{d.canonical_share:.8f}",
                    "mined_vs_hp_ratio": f"{d.mined_vs_hp_ratio:.8f}",
                    "canonical_vs_hp_ratio": f"{d.canonical_vs_hp_ratio:.8f}",
                    "top_actions": ";".join(f"{k}:{v}" for k, v in d.top_actions),
                    "last_raw_action": d.last_raw_action,
                    "last_effective_action": d.last_effective_action,
                    "last_reason": d.last_reason,
                    "last_prompt": d.last_prompt,
                }
            )


def _canonical_set(result: AgenticSimulationResult) -> set[str]:
    out: set[str] = set()
    cur = result.canonical_head_id
    while cur is not None and cur in result.blocks:
        out.add(cur)
        cur = result.blocks[cur].parent_id
    return out
