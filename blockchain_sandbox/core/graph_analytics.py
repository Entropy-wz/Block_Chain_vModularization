from typing import Dict, List, Optional, Tuple
import heapq

class GraphAnalyticsCache:
    """
    智能分层图计算缓存模块
    """
    def __init__(self, graph: "DirectedGraph"):
        self.graph = graph
        self.N = len(list(graph.nodes()))
        self.E = graph.edge_count()
        self.strategy = self.get_strategy(self.N, self.E)
        
        self._all_pairs_cache: Dict[str, Dict[str, float]] = {}
        self._lazy_cache: Dict[str, Dict[str, float]] = {}
        self._landmark_cache: Dict[str, Dict[str, float]] = {}
        self._landmarks: List[str] = []
        
        if self.strategy == "all_pairs":
            self._precompute_all_pairs()
        elif self.strategy == "landmark_approx":
            self._select_landmarks()

    def get_strategy(self, N: int, E: int) -> str:
        if N < 50:
            return "all_pairs"
        elif N < 500:
            return "lazy_source"
        else:
            return "landmark_approx"

    def shortest_path_latencies(self, source: str) -> Dict[str, float]:
        if self.strategy == "all_pairs":
            if source not in self._all_pairs_cache:
                self._all_pairs_cache[source] = self._dijkstra(source)
            return self._all_pairs_cache[source]
            
        elif self.strategy == "lazy_source":
            if source not in self._lazy_cache:
                self._lazy_cache[source] = self._dijkstra(source)
            return self._lazy_cache[source]
            
        elif self.strategy == "landmark_approx":
            # For massive networks, use landmark approximation
            return self._approximate_distances(source)
            
        return self._dijkstra(source)

    def invalidate_for_node(self, node_id: str) -> None:
        if self.strategy == "all_pairs":
            # Recompute all pairs involving node_id or invalidate the whole cache.
            # In small networks, just recomputing the specific affected node's cache or clearing all is fine.
            self._all_pairs_cache.pop(node_id, None)
            for src, dists in self._all_pairs_cache.items():
                if node_id in dists:
                    self._all_pairs_cache[src] = self._dijkstra(src)
        elif self.strategy == "lazy_source":
            # Just clear this node's source cache. 
            # In a full precise implementation we should clear any source that cached a path through this node.
            # Here we do a simple full invalidate for lazy cache to ensure correctness under Jam attacks.
            self._lazy_cache.clear()
        elif self.strategy == "landmark_approx":
            if node_id in self._landmarks:
                self._landmark_cache.pop(node_id, None)
                self._landmark_cache[node_id] = self._dijkstra(node_id)
            else:
                pass # Approximation holds fine for single node jams

    def clear_all(self) -> None:
        self._all_pairs_cache.clear()
        self._lazy_cache.clear()
        if self.strategy == "all_pairs":
            self._precompute_all_pairs()

    def _precompute_all_pairs(self):
        for node in self.graph.nodes():
            self._all_pairs_cache[node] = self._dijkstra(node)

    def _select_landmarks(self, k: int = 5):
        import random
        nodes = list(self.graph.nodes())
        if nodes:
            self._landmarks = random.sample(nodes, min(k, len(nodes)))
            for lm in self._landmarks:
                self._landmark_cache[lm] = self._dijkstra(lm)

    def _approximate_distances(self, source: str) -> Dict[str, float]:
        if source in self._landmark_cache:
            return self._landmark_cache[source]
            
        dist = {n: float("inf") for n in self.graph.nodes()}
        dist[source] = 0.0
        
        # 1-hop 
        for edge in self.graph.neighbors(source):
            dist[edge.dst] = edge.latency
            
        # Triangulation via landmarks
        for lm in self._landmarks:
            lm_dist = self._landmark_cache[lm]
            if source in lm_dist:
                dist_src_lm = lm_dist[source] # assuming undirected roughly
                for target, d in lm_dist.items():
                    if dist_src_lm + d < dist[target]:
                        dist[target] = dist_src_lm + d
        return dist

    def _dijkstra(self, source: str) -> Dict[str, float]:
        dist: Dict[str, float] = {n: float("inf") for n in self.graph.nodes()}
        if source not in dist:
            return dist
            
        dist[source] = 0.0
        heap: List[Tuple[float, str]] = [(0.0, source)]

        while heap:
            current, node = heapq.heappop(heap)
            if current > dist[node]:
                continue
            for edge in self.graph.neighbors(node):
                nxt = current + edge.latency
                if nxt < dist[edge.dst]:
                    dist[edge.dst] = nxt
                    heapq.heappush(heap, (nxt, edge.dst))
        return dist