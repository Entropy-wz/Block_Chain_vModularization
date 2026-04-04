from __future__ import annotations

import csv
import heapq
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from random import Random
from typing import Dict, List, Optional, Tuple

from blockchain_sandbox.core.entities import Block, Node
from blockchain_sandbox.core.graph_model import DirectedGraph, Edge


@dataclass
class HonestNoLLMConfig:
    total_steps: int = 480
    random_seed: int = 11
    num_miners: int = 40
    num_full_nodes: int = 120
    edge_probability: float = 0.60
    min_latency: float = 0.15
    max_latency: float = 0.70
    min_reliability: float = 0.997
    max_reliability: float = 1.0
    block_discovery_chance: float = 0.02
    target_mined_blocks: int = 5000
    max_hops_for_propagation: int = 12
    progress_interval_steps: int = 20
    snapshot_interval_blocks: int = 20
    output_root: str = "outputs"


def main() -> None:
    cfg = HonestNoLLMConfig(
        total_steps=int(os.getenv("SANDBOX_TOTAL_STEPS", "480")),
        random_seed=int(os.getenv("SANDBOX_RANDOM_SEED", "11")),
        num_miners=int(os.getenv("SANDBOX_NUM_MINERS", "40")),
        num_full_nodes=int(os.getenv("SANDBOX_NUM_FULL_NODES", "120")),
        edge_probability=float(os.getenv("SANDBOX_EDGE_PROB", "0.60")),
        min_latency=float(os.getenv("SANDBOX_MIN_LATENCY", "0.15")),
        max_latency=float(os.getenv("SANDBOX_MAX_LATENCY", "0.70")),
        min_reliability=float(os.getenv("SANDBOX_MIN_RELIABILITY", "0.997")),
        max_reliability=float(os.getenv("SANDBOX_MAX_RELIABILITY", "1.0")),
        block_discovery_chance=float(os.getenv("SANDBOX_BLOCK_DISCOVERY_CHANCE", "0.02")),
        target_mined_blocks=int(os.getenv("SANDBOX_TARGET_MINED_BLOCKS", "5000")),
        max_hops_for_propagation=int(os.getenv("SANDBOX_MAX_HOPS", "12")),
        progress_interval_steps=int(os.getenv("SANDBOX_PROGRESS_INTERVAL_STEPS", "20")),
        snapshot_interval_blocks=int(os.getenv("SANDBOX_SNAPSHOT_INTERVAL_BLOCKS", "20")),
        output_root=os.getenv("SANDBOX_OUTPUT_ROOT", "outputs"),
    )

    rng = Random(cfg.random_seed)
    nodes: Dict[str, Node] = {}
    blocks: Dict[str, Block] = {}
    chain_heights: Dict[str, int] = {}
    mined_block_ids: List[str] = []
    block_wins_by_miner: Dict[str, int] = {}
    adopted_counts: Dict[str, int] = {}

    genesis_id = "B0"
    blocks[genesis_id] = Block(genesis_id, None, 0, "genesis", 0)
    chain_heights[genesis_id] = 0
    adopted_counts[genesis_id] = 0

    miner_ids = [f"M{i}" for i in range(cfg.num_miners)]
    full_ids = [f"N{i}" for i in range(cfg.num_full_nodes)]
    raw = [rng.random() for _ in miner_ids]
    total = sum(raw) or 1.0
    powers = [x / total for x in raw]

    for i, mid in enumerate(miner_ids):
        nodes[mid] = Node(
            node_id=mid,
            is_miner=True,
            hash_power=powers[i],
            strategy_name="honest",
            known_blocks={genesis_id},
            local_head_id=genesis_id,
        )
        block_wins_by_miner[mid] = 0

    for nid in full_ids:
        nodes[nid] = Node(
            node_id=nid,
            is_miner=False,
            hash_power=0.0,
            strategy_name="honest",
            known_blocks={genesis_id},
            local_head_id=genesis_id,
        )

    from blockchain_sandbox.core.topology_generator import TopologyGenerator
    node_weights = {n.node_id: n.hash_power for n in nodes.values()}
    graph = TopologyGenerator.generate(
        topology_type=os.getenv("SANDBOX_TOPOLOGY_TYPE", "random"),
        node_ids=list(nodes.keys()),
        rng=rng,
        edge_probability=cfg.edge_probability,
        min_latency=cfg.min_latency,
        max_latency=cfg.max_latency,
        min_reliability=cfg.min_reliability,
        max_reliability=cfg.max_reliability,
        ba_m=int(os.getenv("SANDBOX_TOPOLOGY_BA_M", "3")),
        ws_k=int(os.getenv("SANDBOX_TOPOLOGY_WS_K", "4")),
        ws_beta=float(os.getenv("SANDBOX_TOPOLOGY_WS_BETA", "0.1")),
        core_ratio=float(os.getenv("SANDBOX_TOPOLOGY_CORE_RATIO", "0.05")),
        core_edge_prob=float(os.getenv("SANDBOX_TOPOLOGY_CORE_EDGE_PROB", "0.8")),
        node_weights=node_weights
    )

    for node in nodes.values():
        node.observe_block(genesis_id, 0, chain_heights)
        adopted_counts[genesis_id] += 1

    # event: (time, seq, kind, arg1, arg2, hops)
    events: List[Tuple[float, int, str, str, str, int]] = []
    seq = 0
    fork_events = 0

    def now_ts() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def progress(msg: str) -> None:
        print(f"[{now_ts()}] [NO-LLM] {msg}", flush=True)

    def schedule_next_mine(now_time: float) -> int:
        nonlocal seq
        lam = max(1e-9, cfg.block_discovery_chance)
        delta = rng.expovariate(lam)
        seq += 1
        heapq.heappush(events, (now_time + delta, seq, "mine", "", "", 0))
        return seq

    def sample_winner() -> str:
        x = rng.random()
        c = 0.0
        for m in miner_ids:
            c += nodes[m].hash_power
            if x <= c:
                return m
        return miner_ids[-1]

    def canonical_head() -> str:
        votes: Dict[str, int] = {}
        for n in nodes.values():
            hid = n.local_head_id or genesis_id
            votes[hid] = votes.get(hid, 0) + 1
        if not votes:
            return genesis_id

        def key(bid: str) -> Tuple[int, int, int]:
            return (
                votes.get(bid, 0),
                chain_heights.get(bid, -1),
                blocks[bid].created_at_step if bid in blocks else -1,
            )

        return max(votes.keys(), key=key)

    def maybe_schedule_delivery(edge: Edge, block_id: str, now_time: float, hops: int) -> None:
        nonlocal seq
        if rng.random() > edge.reliability:
            return
        seq += 1
        heapq.heappush(events, (now_time + edge.latency, seq, "recv", edge.dst, block_id, hops))

    def propagate_from(src: str, block_id: str, now_time: float, hops: int) -> None:
        if hops >= cfg.max_hops_for_propagation:
            return
            
        # Batch scheduling for Hub nodes
        avg_degree = graph.edge_count() / max(1, len(list(graph.nodes())))
        outgoing = graph.neighbors(src)
        is_hub = len(outgoing) > max(20, avg_degree * 3)
        
        for i, edge in enumerate(outgoing):
            offset = (i // 20) * 1e-5 if is_hub else 0.0
            maybe_schedule_delivery(edge, block_id, now_time + offset, hops + 1)

    start = time.time()
    progress(
        f"start horizon={cfg.total_steps}, miners={cfg.num_miners}, full_nodes={cfg.num_full_nodes}, "
        f"lambda={cfg.block_discovery_chance}"
    )
    schedule_next_mine(0.0)
    next_mark = 0.0

    while events:
        t, _, kind, a, b, hops = heapq.heappop(events)
        if t > float(cfg.total_steps):
            break
        if len(mined_block_ids) >= max(1, cfg.target_mined_blocks):
            break
        if t >= next_mark:
            progress(f"t={t:.2f}/{cfg.total_steps} blocks={len(blocks)-1} queue={len(events)}")
            next_mark += float(cfg.progress_interval_steps)

        if kind == "mine":
            winner = sample_winner()
            parent = nodes[winner].local_head_id or genesis_id
            bid = f"B{len(blocks)}"
            h = chain_heights[parent] + 1
            step_int = int(round(t * 100.0))
            block = Block(bid, parent, h, winner, step_int)
            blocks[bid] = block
            chain_heights[bid] = h
            adopted_counts[bid] = 0
            mined_block_ids.append(bid)
            block_wins_by_miner[winner] += 1

            if nodes[winner].observe_block(bid, h, chain_heights):
                adopted_counts[bid] += 1
            propagate_from(winner, bid, t, 0)
            if len(mined_block_ids) < max(1, cfg.target_mined_blocks):
                schedule_next_mine(t)
        else:
            dst = a
            bid = b
            node = nodes[dst]
            block = blocks[bid]
            old_head = node.local_head_id
            changed = node.observe_block(bid, block.height, chain_heights)
            if changed:
                adopted_counts[bid] += 1
                if old_head and old_head != block.parent_id:
                    old_h = chain_heights.get(old_head, -1)
                    if old_h == block.height:
                        fork_events += 1
                propagate_from(dst, bid, t, hops)

    head = canonical_head()
    canon_set = set()
    cur: Optional[str] = head
    while cur is not None and cur in blocks:
        canon_set.add(cur)
        cur = blocks[cur].parent_id
    orphan_blocks = sum(1 for bid in blocks if bid not in canon_set)

    by_mined: Dict[str, int] = {}
    by_canon: Dict[str, int] = {}
    for b in blocks.values():
        if b.miner_id == "genesis":
            continue
        by_mined[b.miner_id] = by_mined.get(b.miner_id, 0) + 1
        if b.block_id in canon_set:
            by_canon[b.miner_id] = by_canon.get(b.miner_id, 0) + 1

    total_mined = sum(by_mined.values()) or 1
    total_canon = sum(by_canon.values()) or 1
    miner_rows = []
    for mid in miner_ids:
        hp = nodes[mid].hash_power
        mined = by_mined.get(mid, 0)
        canon = by_canon.get(mid, 0)
        orphan = max(0, mined - canon)
        mined_share = mined / total_mined
        canon_share = canon / total_canon
        miner_rows.append(
            {
                "miner_id": mid,
                "hash_power": hp,
                "mined_blocks": mined,
                "canonical_blocks": canon,
                "orphan_blocks": orphan,
                "orphan_ratio": (orphan / mined) if mined else 0.0,
                "mined_share": mined_share,
                "canonical_share": canon_share,
                "mined_vs_hp_ratio": (mined_share / hp) if hp > 0 else 0.0,
                "canonical_vs_hp_ratio": (canon_share / hp) if hp > 0 else 0.0,
            }
        )

    def corr(xs: List[float], ys: List[float]) -> float:
        n = len(xs)
        if n == 0:
            return 0.0
        mx = sum(xs) / n
        my = sum(ys) / n
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        if vx <= 0 or vy <= 0:
            return 0.0
        cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        return cov / ((vx * vy) ** 0.5)

    def mae(xs: List[float], ys: List[float]) -> float:
        if not xs:
            return 0.0
        return sum(abs(xs[i] - ys[i]) for i in range(len(xs))) / len(xs)

    hp_list = [r["hash_power"] for r in miner_rows]
    mined_share_list = [r["mined_share"] for r in miner_rows]
    canon_share_list = [r["canonical_share"] for r in miner_rows]

    elapsed = time.time() - start
    summary = {
        "mode": "honest_no_llm",
        "elapsed_seconds": elapsed,
        "config": cfg.__dict__,
        "total_blocks_including_genesis": len(blocks),
        "mined_blocks_excluding_genesis": len(blocks) - 1,
        "target_mined_blocks": cfg.target_mined_blocks,
        "canonical_height": blocks[head].height,
        "canonical_head_id": head,
        "orphan_blocks": orphan_blocks,
        "orphan_ratio": orphan_blocks / len(blocks) if blocks else 0.0,
        "fork_events": fork_events,
        "network_avg_shortest_latency": graph.avg_shortest_latency(),
        "corr_hashpower_mined_share": corr(hp_list, mined_share_list),
        "corr_hashpower_canonical_share": corr(hp_list, canon_share_list),
        "mae_hashpower_vs_mined_share": mae(hp_list, mined_share_list),
        "mae_hashpower_vs_canonical_share": mae(hp_list, canon_share_list),
    }

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(cfg.output_root) / f"run_no_llm_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out_dir / "miner_details.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(miner_rows[0].keys()) if miner_rows else [])
        if miner_rows:
            writer.writeheader()
            writer.writerows(miner_rows)

    ordered = sorted(
        blocks.values(),
        key=lambda b: int(b.block_id[1:]) if b.block_id.startswith("B") and b.block_id[1:].isdigit() else 0,
    )
    with (out_dir / "blocks.jsonl").open("w", encoding="utf-8", newline="") as f:
        for b in ordered:
            row = {
                "block_id": b.block_id,
                "parent_id": b.parent_id,
                "height": b.height,
                "miner_id": b.miner_id,
                "created_at_step": b.created_at_step,
                "is_canonical": b.block_id in canon_set,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    _generate_tree_pngs(
        out_dir=out_dir,
        blocks=blocks,
        mined_block_ids=mined_block_ids,
        snapshot_interval_blocks=cfg.snapshot_interval_blocks,
    )

    print("=" * 76, flush=True)
    print("Honest No-LLM Baseline Report", flush=True)
    print("=" * 76, flush=True)
    print(f"Mined blocks: {summary['mined_blocks_excluding_genesis']}", flush=True)
    print(f"Canonical height: {summary['canonical_height']}", flush=True)
    print(f"Orphan blocks: {summary['orphan_blocks']} ({summary['orphan_ratio']:.2%})", flush=True)
    print(f"corr(hash_power, canonical_share): {summary['corr_hashpower_canonical_share']:.3f}", flush=True)
    print(f"mae(hash_power vs canonical_share): {summary['mae_hashpower_vs_canonical_share']:.4f}", flush=True)
    print(f"Artifacts saved to: {out_dir}", flush=True)
    pngs = sorted(out_dir.glob("*.png"))
    if pngs:
        print("Generated tree PNG files:", flush=True)
        for p in pngs:
            print(f"  - {p}", flush=True)


def _generate_tree_pngs(
    out_dir: Path,
    blocks: Dict[str, Block],
    mined_block_ids: List[str],
    snapshot_interval_blocks: int,
) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    if not mined_block_ids:
        return

    def draw(subset: List[str], out_path: Path, title: str) -> None:
        subset_set = set(subset)
        children: Dict[str, List[str]] = {bid: [] for bid in subset}
        roots: List[str] = []

        for bid in subset:
            parent = blocks[bid].parent_id
            if parent in subset_set:
                children[parent].append(bid)
            else:
                roots.append(bid)

        def key(bid: str) -> Tuple[int, int]:
            b = blocks[bid]
            nid = int(bid[1:]) if bid.startswith("B") and bid[1:].isdigit() else 0
            return (b.height, nid)

        for k in children:
            children[k].sort(key=key)
        roots.sort(key=key)

        x_pos: Dict[str, float] = {}
        y_pos: Dict[str, float] = {}
        cur_x = 0.0

        # Non-recursive post-order traversal to avoid RecursionError
        # on long chains (e.g., thousands of blocks).
        for r in roots:
            stack: List[Tuple[str, bool]] = [(r, False)]
            while stack:
                node_id, visited = stack.pop()
                if not visited:
                    stack.append((node_id, True))
                    nxt = children.get(node_id, [])
                    for ch in reversed(nxt):
                        stack.append((ch, False))
                    continue

                nxt = children.get(node_id, [])
                if not nxt:
                    x = cur_x
                    cur_x += 1.0
                else:
                    x = sum(x_pos[ch] for ch in nxt) / len(nxt)
                x_pos[node_id] = x
                y_pos[node_id] = -float(blocks[node_id].height)

        fig_w = max(10, min(30, int(cur_x * 0.6) + 6))
        fig_h = 11 if len(subset) <= 60 else 14
        plt.figure(figsize=(fig_w, fig_h))

        for bid in subset:
            parent = blocks[bid].parent_id
            if parent in subset_set:
                plt.plot([x_pos[parent], x_pos[bid]], [y_pos[parent], y_pos[bid]], color="#7a7a7a", linewidth=1.2)

        for bid in subset:
            b = blocks[bid]
            plt.scatter([x_pos[bid]], [y_pos[bid]], s=60, color="#225ea8")
            plt.text(x_pos[bid], y_pos[bid] - 0.15, f"{bid}\n{b.miner_id}", fontsize=7, ha="center", va="top")

        plt.title(title)
        plt.axis("off")
        plt.tight_layout()
        plt.savefig(out_path, dpi=220)
        plt.close()

    draw(mined_block_ids, out_dir / "full_tree.png", f"Full Block Tree | blocks={len(mined_block_ids)}")
    interval = max(1, snapshot_interval_blocks)
    w = 0
    for i in range(0, len(mined_block_ids), interval):
        window = mined_block_ids[i : i + interval]
        if not window:
            continue
        w += 1
        draw(window, out_dir / f"window_{w:02d}_tree.png", f"Window {w} | blocks={len(window)}")


if __name__ == "__main__":
    main()
