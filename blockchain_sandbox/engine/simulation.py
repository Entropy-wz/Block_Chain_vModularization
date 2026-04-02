from __future__ import annotations

import heapq
from dataclasses import dataclass
from random import Random
from typing import Dict, List, Optional, Tuple

from ..core.config import SimulationConfig
from ..core.entities import Block, Node
from ..core.graph_model import DirectedGraph, Edge
from .strategies import build_strategy


@dataclass
class SimulationResult:
    blocks: Dict[str, Block]
    nodes: Dict[str, Node]
    adopted_counts: Dict[str, int]
    canonical_head_id: str
    heaviest_head_id: str
    fork_events: int
    orphan_blocks: int
    block_wins_by_miner: Dict[str, int]
    graph: DirectedGraph
    config: SimulationConfig


class BlockchainSimulation:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.rng = Random(config.random_seed)

        self.nodes: Dict[str, Node] = {}
        self.blocks: Dict[str, Block] = {}
        self.chain_heights: Dict[str, int] = {}
        self.adopted_counts: Dict[str, int] = {}
        self.block_wins_by_miner: Dict[str, int] = {}

        self._events: List[Tuple[float, int, str, str, int]] = []
        self._seq = 0
        self.fork_events = 0
        self._scheduled_deliveries: set[Tuple[str, str]] = set()

        self.genesis_id = "B0"
        genesis = Block(
            block_id=self.genesis_id,
            parent_id=None,
            height=0,
            miner_id="genesis",
            created_at_step=0,
        )
        self.blocks[self.genesis_id] = genesis
        self.chain_heights[self.genesis_id] = 0
        self.adopted_counts[self.genesis_id] = 0

        self._init_nodes()
        self.graph = self._init_graph()
        self._bootstrap_genesis()

    def _init_nodes(self) -> None:
        miner_ids = [f"M{i}" for i in range(self.config.num_miners)]
        full_ids = [f"N{i}" for i in range(self.config.num_full_nodes)]

        raw = [self.rng.random() for _ in miner_ids]
        total = sum(raw) or 1.0
        normalized = [r / total for r in raw]

        for i, miner_id in enumerate(miner_ids):
            strategy_name = "honest"
            if i % 7 == 0:
                strategy_name = "selfish_like"
            elif i % 3 == 0:
                strategy_name = "degree_biased"

            self.nodes[miner_id] = Node(
                node_id=miner_id,
                is_miner=True,
                hash_power=normalized[i],
                strategy_name=strategy_name,
                known_blocks={self.genesis_id},
                local_head_id=self.genesis_id,
            )
            self.block_wins_by_miner[miner_id] = 0

        for node_id in full_ids:
            self.nodes[node_id] = Node(
                node_id=node_id,
                is_miner=False,
                hash_power=0.0,
                strategy_name="honest",
                known_blocks={self.genesis_id},
                local_head_id=self.genesis_id,
            )

    def _init_graph(self) -> DirectedGraph:
        return DirectedGraph.random_graph(
            node_ids=list(self.nodes.keys()),
            edge_probability=self.config.edge_probability,
            min_latency=self.config.min_latency,
            max_latency=self.config.max_latency,
            min_reliability=self.config.min_reliability,
            max_reliability=self.config.max_reliability,
            rng=self.rng,
        )

    def _bootstrap_genesis(self) -> None:
        for node in self.nodes.values():
            node.observe_block(self.genesis_id, 0, self.chain_heights)
            self.adopted_counts[self.genesis_id] += 1

    def run(self) -> SimulationResult:
        for step in range(1, self.config.total_steps + 1):
            self._mine_step(step)
            self._flush_events(step)

        canonical_head = self._canonical_head()
        heaviest_head = self._heaviest_head()
        orphan_blocks = self._count_orphans(canonical_head)

        return SimulationResult(
            blocks=self.blocks,
            nodes=self.nodes,
            adopted_counts=self.adopted_counts,
            canonical_head_id=canonical_head,
            heaviest_head_id=heaviest_head,
            fork_events=self.fork_events,
            orphan_blocks=orphan_blocks,
            block_wins_by_miner=self.block_wins_by_miner,
            graph=self.graph,
            config=self.config,
        )

    def _mine_step(self, step: int) -> None:
        for node in self.nodes.values():
            if not node.is_miner:
                continue

            strategy = build_strategy(node.strategy_name)
            mine_prob = (
                self.config.base_mine_probability
                * self.config.target_block_interval_steps
                * node.hash_power
                * strategy.mining_multiplier()
            )

            if self.rng.random() <= mine_prob:
                parent_id = node.local_head_id or self.genesis_id
                parent_h = self.chain_heights[parent_id]
                block_id = f"B{len(self.blocks)}"

                block = Block(
                    block_id=block_id,
                    parent_id=parent_id,
                    height=parent_h + 1,
                    miner_id=node.node_id,
                    created_at_step=step,
                )
                self.blocks[block_id] = block
                self.chain_heights[block_id] = block.height
                self.adopted_counts[block_id] = 0
                self.block_wins_by_miner[node.node_id] += 1

                # Local node sees its own block immediately.
                if node.observe_block(block_id, block.height, self.chain_heights):
                    self.adopted_counts[block_id] += 1

                self._propagate_from(node.node_id, block_id, step, 0)

    def _propagate_from(self, src: str, block_id: str, now_step: float, hops: int) -> None:
        if hops >= self.config.max_hops_for_propagation:
            return

        block = self.blocks[block_id]
        src_node = self.nodes[src]
        strategy = build_strategy(src_node.strategy_name)
        outgoing = self.graph.neighbors(src)
        decision = strategy.select_propagation_edges(outgoing)

        for edge in decision.forward_edges:
            self._maybe_schedule_delivery(edge, block.block_id, now_step, hops + 1)

    def _maybe_schedule_delivery(self, edge: Edge, block_id: str, now_step: float, hops: int) -> None:
        if block_id in self.nodes[edge.dst].known_blocks:
            return
        if (edge.dst, block_id) in self._scheduled_deliveries:
            return
        if self.rng.random() > edge.reliability:
            return
        self._scheduled_deliveries.add((edge.dst, block_id))
        arrival_step = now_step + edge.latency
        self._seq += 1
        heapq.heappush(self._events, (arrival_step, self._seq, edge.dst, block_id, hops))

    def _flush_events(self, current_step: int) -> None:
        while self._events and self._events[0][0] <= current_step:
            _, _, dst, block_id, hops = heapq.heappop(self._events)
            node = self.nodes[dst]
            block = self.blocks[block_id]

            old_head = node.local_head_id
            changed = node.observe_block(block_id, block.height, self.chain_heights)
            if changed:
                self.adopted_counts[block_id] += 1

                if old_head and old_head != block.parent_id:
                    old_h = self.chain_heights.get(old_head, -1)
                    if old_h == block.height:
                        self.fork_events += 1

            if changed:
                self._propagate_from(dst, block_id, current_step, hops)

    def _heaviest_head(self) -> str:
        best_id = self.genesis_id
        best_h = -1
        for bid, block in self.blocks.items():
            if block.height > best_h:
                best_h = block.height
                best_id = bid
            elif block.height == best_h and block.created_at_step < self.blocks[best_id].created_at_step:
                best_id = bid
        return best_id

    def _canonical_head(self) -> str:
        # Consensus approximation: block with max global adoption, tie by height.
        best_id: Optional[str] = None
        best_adopt = -1
        best_height = -1
        for block_id, adopts in self.adopted_counts.items():
            h = self.chain_heights[block_id]
            if adopts > best_adopt or (adopts == best_adopt and h > best_height):
                best_id = block_id
                best_adopt = adopts
                best_height = h
        return best_id or self.genesis_id

    def _count_orphans(self, canonical_head: str) -> int:
        canonical_set = set()
        cursor: Optional[str] = canonical_head
        while cursor is not None:
            canonical_set.add(cursor)
            cursor = self.blocks[cursor].parent_id if cursor in self.blocks else None
        return sum(1 for b in self.blocks if b not in canonical_set)
