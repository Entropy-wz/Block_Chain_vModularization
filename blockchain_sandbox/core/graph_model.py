from __future__ import annotations

from dataclasses import dataclass
import heapq
from random import Random
from typing import Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .graph_analytics import GraphAnalyticsCache


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    latency: float
    reliability: float


class DirectedGraph:
    def __init__(self) -> None:
        self._adj: Dict[str, List[Edge]] = {}
        # Changed to smart analytic cache
        self._analytics_cache: Optional["GraphAnalyticsCache"] = None

    def _get_cache(self) -> "GraphAnalyticsCache":
        from .graph_analytics import GraphAnalyticsCache
        if self._analytics_cache is None:
            self._analytics_cache = GraphAnalyticsCache(self)
        return self._analytics_cache

    def add_node(self, node_id: str) -> None:
        self._adj.setdefault(node_id, [])

    def add_edge(self, edge: Edge) -> None:
        self._adj.setdefault(edge.src, []).append(edge)
        self._adj.setdefault(edge.dst, [])

    def neighbors(self, node_id: str) -> List[Edge]:
        return self._adj.get(node_id, [])

    def replace_neighbors(self, node_id: str, edges: List[Edge]) -> None:
        self._adj[node_id] = edges
        self.invalidate_cache_for(node_id)

    def invalidate_cache_for(self, node_id: str) -> None:
        if self._analytics_cache is not None:
            self._analytics_cache.invalidate_for_node(node_id)

    def clear_cache(self) -> None:
        if self._analytics_cache is not None:
            self._analytics_cache.clear_all()

    def nodes(self) -> Iterable[str]:
        return self._adj.keys()

    def edge_count(self) -> int:
        return sum(len(v) for v in self._adj.values())

    def out_degree(self, node_id: str) -> int:
        return len(self._adj.get(node_id, []))

    def shortest_path_latencies(self, source: str, use_cache: bool = True) -> Dict[str, float]:
        """
        Calculates shortest path latencies using intelligent caching strategies
        based on the size of the network.
        """
        if use_cache:
            return self._get_cache().shortest_path_latencies(source)
            
        # Uncached fallback
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
        self.clear_cache() # Broad impact, clear all

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
        self.invalidate_cache_for(src_node)

    def avg_shortest_latency(self) -> float:
        all_nodes = list(self._adj.keys())
        if not all_nodes:
            return 0.0

        total = 0.0
        count = 0
        
        # Scale strategy based on size
        n = len(all_nodes)
        sample_nodes = all_nodes
        if n > 500: # K-hop / approximation scale
            import random
            sample_nodes = random.sample(all_nodes, k=min(100, n))
            
        for src in sample_nodes:
            dist = self.shortest_path_latencies(src, use_cache=True)
            for dst, d in dist.items():
                if src == dst or d == float("inf"):
                    continue
                total += d
                count += 1
        return total / count if count else float("inf")

