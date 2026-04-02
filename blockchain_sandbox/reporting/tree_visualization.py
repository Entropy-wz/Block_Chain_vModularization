from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

from ..engine.agentic_simulation import AgenticSimulationResult


def generate_tree_pngs(result: AgenticSimulationResult, run_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    blocks = result.blocks
    raw_mined = getattr(result, "mined_block_ids", None)
    if isinstance(raw_mined, list):
        mined_ids = [bid for bid in raw_mined if bid in blocks]
    else:
        # Fallback for compatibility with older result payloads.
        mined_ids = sorted(
            [bid for bid in blocks.keys() if bid != "B0"],
            key=lambda x: int(x[1:]) if x.startswith("B") and x[1:].isdigit() else 0,
        )
    if not mined_ids:
        return

    # Full tree.
    _draw_tree_png(
        blocks=blocks,
        subset=set(mined_ids),
        out_path=run_dir / "full_tree.png",
        title=f"Full Block Tree | blocks={len(mined_ids)}",
        plt=plt,
    )

    # Window trees aligned with snapshot windows.
    for i, snap in enumerate(result.snapshots, start=1):
        subset = set(snap.window_block_ids)
        if not subset:
            continue
        _draw_tree_png(
            blocks=blocks,
            subset=subset,
            out_path=run_dir / f"window_{i:02d}_tree.png",
            title=f"Window {i} Block Tree | step={snap.step} | blocks={len(subset)}",
            plt=plt,
        )


def _draw_tree_png(
    blocks: Dict[str, object],
    subset: Set[str],
    out_path: Path,
    title: str,
    plt,
) -> None:
    children: Dict[str, List[str]] = {bid: [] for bid in subset}
    roots: List[str] = []

    for bid in subset:
        b = blocks[bid]
        parent = getattr(b, "parent_id", None)
        if parent in subset:
            children[parent].append(bid)
        else:
            roots.append(bid)

    def sort_key(x: str) -> tuple[int, int]:
        h = getattr(blocks[x], "height", 0)
        n = int(x[1:]) if x.startswith("B") and x[1:].isdigit() else 0
        return (h, n)

    for k in children:
        children[k].sort(key=sort_key)
    roots.sort(key=sort_key)

    x_pos: Dict[str, float] = {}
    y_pos: Dict[str, float] = {}
    cur_x = 0.0

    def dfs(node_id: str) -> float:
        nonlocal cur_x
        nxt = children.get(node_id, [])
        if not nxt:
            x = cur_x
            cur_x += 1.0
        else:
            child_x = [dfs(ch) for ch in nxt]
            x = sum(child_x) / len(child_x)
        x_pos[node_id] = x
        y_pos[node_id] = -float(getattr(blocks[node_id], "height", 0))
        return x

    for r in roots:
        dfs(r)

    fig_w = max(10, min(30, int(cur_x * 0.6) + 6))
    fig_h = 11 if len(subset) <= 60 else 14
    plt.figure(figsize=(fig_w, fig_h))

    for bid in subset:
        b = blocks[bid]
        parent = getattr(b, "parent_id", None)
        if parent in subset:
            plt.plot(
                [x_pos[parent], x_pos[bid]],
                [y_pos[parent], y_pos[bid]],
                color="#7a7a7a",
                linewidth=1.2,
            )

    for bid in subset:
        b = blocks[bid]
        plt.scatter([x_pos[bid]], [y_pos[bid]], s=60, color="#225ea8")
        label = f"{bid}\\n{getattr(b, 'miner_id', '?')}"
        plt.text(x_pos[bid], y_pos[bid] - 0.15, label, fontsize=7, ha="center", va="top")

    plt.title(title)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(out_path, dpi=220)
    plt.close()
