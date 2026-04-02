from __future__ import annotations

from dataclasses import dataclass
import heapq
from random import Random
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    latency: float
    reliability: float


class DirectedGraph:
    def __init__(self) -> None:
        self._adj: Dict[str, List[Edge]] = {}

    def add_node(self, node_id: str) -> None:
        self._adj.setdefault(node_id, [])

    def add_edge(self, edge: Edge) -> None:
        self._adj.setdefault(edge.src, []).append(edge)
        self._adj.setdefault(edge.dst, [])

    def neighbors(self, node_id: str) -> List[Edge]:
        return self._adj.get(node_id, [])

    def replace_neighbors(self, node_id: str, edges: List[Edge]) -> None:
        self._adj[node_id] = edges

    def nodes(self) -> Iterable[str]:
        return self._adj.keys()

    def edge_count(self) -> int:
        return sum(len(v) for v in self._adj.values())

    def out_degree(self, node_id: str) -> int:
        return len(self._adj.get(node_id, []))

    def shortest_path_latencies(self, source: str) -> Dict[str, float]:
        # Dijkstra on edge latency.
        dist: Dict[str, float] = {n: float("inf") for n in self._adj}
        if source not in dist:
            return dist
        dist[source] = 0.0
        heap: List[Tuple[float, str]] = [(0.0, source)]

        while heap:
            current, node = heapq.heappop(heap)
            if current > dist[node]:
                continue
            for edge in self._adj.get(node, []):
                nxt = current + edge.latency
                if nxt < dist[edge.dst]:
                    dist[edge.dst] = nxt
                    heapq.heappush(heap, (nxt, edge.dst))
        return dist

    def ban_node(self, node_id: str) -> None:
        """Physically disconnects a node by setting latency to infinity and reliability to 0."""
        for src, edges in self._adj.items():
            new_edges = []
            for e in edges:
                if e.dst == node_id or src == node_id:
                    new_edges.append(Edge(e.src, e.dst, float('inf'), 0.0))
                else:
                    new_edges.append(e)
            self._adj[src] = new_edges

    def apply_latency_multiplier(
        self,
        src_node: str,
        dst_node: Optional[str] = None,
        factor: float = 1.0,
    ) -> None:
        if factor <= 0:
            return
        edges = self._adj.get(src_node, [])
        replaced: List[Edge] = []
        for edge in edges:
            if dst_node is None or edge.dst == dst_node:
                replaced.append(
                    Edge(
                        src=edge.src,
                        dst=edge.dst,
                        latency=edge.latency * factor,
                        reliability=edge.reliability,
                    )
                )
            else:
                replaced.append(edge)
        self._adj[src_node] = replaced

    def avg_shortest_latency(self) -> float:
        all_nodes = list(self._adj.keys())
        if not all_nodes:
            return 0.0

        total = 0.0
        count = 0
        for src in all_nodes:
            dist = self.shortest_path_latencies(src)
            for dst, d in dist.items():
                if src == dst or d == float("inf"):
                    continue
                total += d
                count += 1
        return total / count if count else float("inf")

    @classmethod
    def random_graph(
        cls,
        node_ids: List[str],
        edge_probability: float,
        min_latency: float,
        max_latency: float,
        min_reliability: float,
        max_reliability: float,
        rng: Random,
    ) -> "DirectedGraph":
        graph = cls()
        for n in node_ids:
            graph.add_node(n)

        for src in node_ids:
            for dst in node_ids:
                if src == dst:
                    continue
                if rng.random() <= edge_probability:
                    edge = Edge(
                        src=src,
                        dst=dst,
                        latency=rng.uniform(min_latency, max_latency),
                        reliability=rng.uniform(min_reliability, max_reliability),
                    )
                    graph.add_edge(edge)
        return graph
