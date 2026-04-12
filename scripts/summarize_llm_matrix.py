from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple


KNOWN_MODES = ("strategy_first", "persona_first", "high_persona")


def find_latest_summary(base: Path) -> Path | None:
    if not base.exists():
        return None
    candidates = sorted(base.glob("*/**/run_*/reports/summary.json"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        return None
    return candidates[-1]


def parse_name(output_root: str, prefix: str) -> Tuple[str, str]:
    tail = output_root
    if tail.startswith(prefix + "_"):
        tail = tail[len(prefix) + 1 :]
    if tail.endswith("_a035"):
        tail = tail[:-5]
    for mode in KNOWN_MODES:
        suffix = "_" + mode
        if tail.endswith(suffix):
            strategy = tail[: -len(suffix)]
            return strategy, mode
    parts = tail.split("_")
    if len(parts) < 2:
        return tail, "unknown"
    return "_".join(parts[:-1]), parts[-1]


def flatten_metrics(summary: Dict) -> Dict:
    h = summary.get("headline_metrics", {})
    row = {
        "output_root": "",
        "strategy": "",
        "decision_mode": "",
        "total_blocks": h.get("total_blocks", 0),
        "canonical_height": h.get("canonical_height", 0),
        "orphan_ratio": h.get("orphan_ratio", 0.0),
        "selfish_hash_power_share": h.get("selfish_hash_power_share", 0.0),
        "selfish_ratio_economic": h.get("selfish_ratio_economic", 0.0),
        "ratio_economic_signed": h.get("ratio_economic_signed", 0.0),
        "strategy_constrained_rate": h.get("strategy_constrained_rate", summary.get("strategy_constrained_rate", 0.0)),
        "persona_deviation_rate": h.get("persona_deviation_rate", summary.get("persona_deviation_rate", 0.0)),
        "fallback_to_strategy_rate": h.get("fallback_to_strategy_rate", summary.get("fallback_to_strategy_rate", 0.0)),
        "ds_attempts": h.get("ds_attempts", 0),
        "ds_success_count": h.get("ds_success_count", 0),
        "attacker_net_profit": h.get("attacker_net_profit", 0.0),
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="outputs/exp_matrix", help="Output root prefix used in run script")
    parser.add_argument("--group", default="default", help="Experiment group name")
    parser.add_argument("--out", default="outputs/exp_matrix_summary.csv", help="CSV output path")
    args = parser.parse_args()

    prefix_path = Path(args.prefix)
    root = prefix_path.parent if prefix_path.parent != Path("") else Path(".")
    stem = prefix_path.name

    dirs = sorted([p for p in root.glob(f"{stem}_*_a035") if p.is_dir()])
    if not dirs:
        raise SystemExit(f"No experiment directories matched: {root / (stem + '_*_a035')}")

    rows: List[Dict] = []
    for d in dirs:
        group_dir = d / args.group
        summary_path = find_latest_summary(group_dir)
        if summary_path is None:
            continue
        with summary_path.open("r", encoding="utf-8") as f:
            summary = json.load(f)
        row = flatten_metrics(summary)
        strategy, mode = parse_name(d.name, stem)
        row["output_root"] = d.as_posix()
        row["strategy"] = strategy
        row["decision_mode"] = mode
        rows.append(row)

    if not rows:
        raise SystemExit("No summary.json found under matched directories.")

    rows.sort(key=lambda r: (r["strategy"], r["decision_mode"]))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {out_path}")
    print("\nQuick view:")
    for r in rows:
        print(
            f"{r['strategy']:<18} {r['decision_mode']:<14} "
            f"canon={r['canonical_height']:<4} orphan={float(r['orphan_ratio']):.2%} "
            f"dev={float(r['persona_deviation_rate']):.2%} constr={float(r['strategy_constrained_rate']):.2%} "
            f"ds={r['ds_success_count']}/{r['ds_attempts']}"
        )


if __name__ == "__main__":
    main()
