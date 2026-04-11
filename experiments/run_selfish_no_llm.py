from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter

from blockchain_sandbox.engine.selfish_no_llm import (
    SelfishNoLLMConfig,
    SelfishNoLLMResult,
    simulate_selfish_no_llm,
)


def main() -> None:
    cfg = SelfishNoLLMConfig(
        alpha=float(os.getenv("SANDBOX_SELFISH_ALPHA", "0.35")),
        gamma=float(os.getenv("SANDBOX_SELFISH_GAMMA", "0.5")),
        target_blocks=int(os.getenv("SANDBOX_SELFISH_TARGET_BLOCKS", "5000")),
        random_seed=int(os.getenv("SANDBOX_SELFISH_RANDOM_SEED", os.getenv("SANDBOX_RANDOM_SEED", "11"))),
        strategy_name=os.getenv("SANDBOX_SELFISH_STRATEGY", "classic").strip().lower(),
    )
    theory_gap_threshold = float(os.getenv("SANDBOX_THEORY_GAP_THRESHOLD", "0.03"))
    output_root = os.getenv("SANDBOX_OUTPUT_ROOT", "outputs")

    started = perf_counter()
    result = simulate_selfish_no_llm(cfg, theory_gap_threshold=theory_gap_threshold)
    elapsed = perf_counter() - started

    run_dir = _build_run_dir(output_root)
    data_dir = run_dir / "data"
    reports_dir = run_dir / "reports"
    viz_dir = run_dir / "visualizations"
    data_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    viz_dir.mkdir(parents=True, exist_ok=True)

    _write_summary_json(reports_dir / "summary.json", result, elapsed, theory_gap_threshold)
    _write_miner_details_csv(reports_dir / "miner_details.csv", result)
    _write_steps_jsonl(data_dir / "steps.jsonl", result)
    _write_lead_histogram_csv(reports_dir / "lead_histogram.csv", result)
    _plot_cumulative_share(viz_dir / "selfish_share_curve.png", result)
    _plot_lead_distribution(viz_dir / "lead_distribution.png", result)

    print("=" * 76, flush=True)
    print("Selfish No-LLM (Eyal & Sirer Style) Report", flush=True)
    print("=" * 76, flush=True)
    print(f"Strategy: {result.config.strategy_name}", flush=True)
    print(f"Alpha(selfish hash power): {result.config.alpha:.4f}", flush=True)
    print(f"Gamma(tie advantage): {result.config.gamma:.4f}", flush=True)
    print("-" * 76, flush=True)
    print(f"Canonical blocks: {result.selfish_blocks + result.honest_blocks}", flush=True)
    print("", flush=True)
    selfish_ratio = result.simulated_selfish_share / max(1e-12, result.config.alpha)
    honest_share = 1.0 - result.simulated_selfish_share
    honest_power = 1.0 - result.config.alpha
    honest_ratio = honest_share / max(1e-12, honest_power)
    print("[Selfish Miner Group]", flush=True)
    print(f"  hash power share: {result.config.alpha:.4f}", flush=True)
    print(f"  canonical share:  {result.simulated_selfish_share:.4f}", flush=True)
    print(f"  ratio (share/power): {selfish_ratio:.4f}", flush=True)
    print(f"  canonical blocks: {result.selfish_blocks}", flush=True)
    print("", flush=True)
    print("[Honest Miner Group]", flush=True)
    print(f"  hash power share: {honest_power:.4f}", flush=True)
    print(f"  canonical share:  {honest_share:.4f}", flush=True)
    print(f"  ratio (share/power): {honest_ratio:.4f}", flush=True)
    print(f"  canonical blocks: {result.honest_blocks}", flush=True)
    print("-" * 76, flush=True)
    if result.theoretical_selfish_share is None:
        print("Theoretical selfish share: N/A (non-classic strategy)", flush=True)
        print("Theory gap abs: N/A", flush=True)
        print("Theory match: N/A", flush=True)
    else:
        print(f"Theoretical selfish share: {result.theoretical_selfish_share:.4f}", flush=True)
        print(f"Theory gap abs: {result.theory_gap_abs:.4f}", flush=True)
        print(f"Theory match (<= {theory_gap_threshold:.4f}): {result.theory_match}", flush=True)
    print(f"Artifacts saved to: {run_dir}", flush=True)


def _build_run_dir(output_root: str) -> Path:
    group = os.getenv("SANDBOX_EXPERIMENT_GROUP", "selfish_no_llm").strip() or "selfish_no_llm"
    date_str = datetime.now().strftime("%Y-%m-%d")
    stamp = datetime.now().strftime("%H%M%S")
    base = Path(output_root) / group / date_str / f"run_{stamp}"
    if not base.exists():
        return base
    i = 1
    while True:
        cand = Path(output_root) / group / date_str / f"run_{stamp}_{i:02d}"
        if not cand.exists():
            return cand
        i += 1


def _write_summary_json(path: Path, result: SelfishNoLLMResult, elapsed: float, theory_gap_threshold: float) -> None:
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "selfish_no_llm_eyal_sirer",
        "elapsed_seconds": elapsed,
        "config": asdict(result.config),
        "theory_gap_threshold": theory_gap_threshold,
        "selfish_alpha": result.config.alpha,
        "selfish_gamma": result.config.gamma,
        "selfish_strategy": result.config.strategy_name,
        "simulated_selfish_share": result.simulated_selfish_share,
        "theoretical_selfish_share": result.theoretical_selfish_share,
        "theory_gap_abs": result.theory_gap_abs,
        "theory_match": result.theory_match,
        "selfish_blocks": result.selfish_blocks,
        "honest_blocks": result.honest_blocks,
        "total_canonical_blocks": result.selfish_blocks + result.honest_blocks,
        "total_events": result.total_events,
        "race_entries": result.race_entries,
        "final_private_lead": result.final_private_lead,
        "lead_histogram": result.lead_histogram,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_miner_details_csv(path: Path, result: SelfishNoLLMResult) -> None:
    rows = [
        {
            "miner_group": "selfish_pool",
            "canonical_blocks": result.selfish_blocks,
            "canonical_share": result.simulated_selfish_share,
        },
        {
            "miner_group": "honest_network",
            "canonical_blocks": result.honest_blocks,
            "canonical_share": 1.0 - result.simulated_selfish_share,
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_steps_jsonl(path: Path, result: SelfishNoLLMResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        for rec in result.steps:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


def _write_lead_histogram_csv(path: Path, result: SelfishNoLLMResult) -> None:
    rows = [{"lead_state": k, "visits": v} for k, v in sorted(result.lead_histogram.items())]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["lead_state", "visits"])
        writer.writeheader()
        writer.writerows(rows)


def _plot_cumulative_share(path: Path, result: SelfishNoLLMResult) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    s = 0
    h = 0
    xs = []
    ys = []
    for rec in result.steps:
        s += rec.selfish_gain
        h += rec.honest_gain
        total = s + h
        if total <= 0:
            continue
        xs.append(rec.step)
        ys.append(s / total)

    if not xs:
        return

    plt.figure(figsize=(10, 4))
    plt.plot(xs, ys, label="Simulated selfish share", color="#1f77b4")
    if result.theoretical_selfish_share is not None:
        plt.axhline(result.theoretical_selfish_share, color="#d62728", linestyle="--", label="Theoretical share")
    plt.xlabel("Event step")
    plt.ylabel("Selfish share")
    plt.title("Selfish Mining Share Convergence")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()


def _plot_lead_distribution(path: Path, result: SelfishNoLLMResult) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    xs = sorted(result.lead_histogram.keys())
    ys = [result.lead_histogram[x] for x in xs]
    if not xs:
        return

    plt.figure(figsize=(8, 4))
    plt.bar([str(x) for x in xs], ys, color="#2ca02c")
    plt.xlabel("Private lead state")
    plt.ylabel("Visits")
    plt.title("Lead State Distribution")
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()


if __name__ == "__main__":
    main()
