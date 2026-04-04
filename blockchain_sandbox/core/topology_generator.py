from __future__ import annotations
from typing import Dict, List, Optional, Callable
from random import Random
from .graph_model import DirectedGraph, Edge


class TopologyGenerator:
    """
    Registry-based topology generator.
    Provides a central point to register and invoke different graph generation strategies.
    """
    _registry: Dict[str, Callable] = {}

    @classmethod
    def register(cls, topology_type: str, func: Callable) -> None:
        """Register a new topology generation function."""
        cls._registry[topology_type] = func

    @classmethod
    def generate(
        cls,
        topology_type: str,
        node_ids: List[str],
        rng: Random,
        edge_probability: float = 0.25,
        min_latency: float = 1.0,
        max_latency: float = 4.0,
        min_reliability: float = 0.9,
        max_reliability: float = 1.0,
        ba_m: int = 3,
        ws_k: int = 4,
        ws_beta: float = 0.1,
        core_ratio: float = 0.05,
        core_edge_prob: float = 0.8,
        node_weights: Optional[Dict[str, float]] = None
    ) -> DirectedGraph:
        """
        Generate a graph using the registered topology function.
        """
        if topology_type not in cls._registry:
            raise ValueError(f"Unknown topology type: {topology_type}. Available: {list(cls._registry.keys())}")
        
        generator_func = cls._registry[topology_type]
        
        # We pass all potentially needed parameters to the registered functions.
        # Functions should use **kwargs to absorb unused parameters.
        return generator_func(
            node_ids=node_ids,
            rng=rng,
            edge_probability=edge_probability,
            min_latency=min_latency,
            max_latency=max_latency,
            min_reliability=min_reliability,
            max_reliability=max_reliability,
            ba_m=ba_m,
            ws_k=ws_k,
            ws_beta=ws_beta,
            core_ratio=core_ratio,
            core_edge_prob=core_edge_prob,
            node_weights=node_weights
        )

# ==============================================================================
# Built-in Topology Functions
# ==============================================================================

def random_graph(
    node_ids: List[str],
    rng: Random,
    edge_probability: float,
    min_latency: float,
    max_latency: float,
    min_reliability: float,
    max_reliability: float,
    **kwargs
) -> DirectedGraph:
    """Basic Erdos-Renyi style random directed graph."""
    graph = DirectedGraph()
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


def barabasi_albert_graph(
    node_ids: List[str],
    rng: Random,
    ba_m: int,
    min_latency: float,
    max_latency: float,
    min_reliability: float,
    max_reliability: float,
    node_weights: Optional[Dict[str, float]] = None,
    **kwargs
) -> DirectedGraph:
    """Scale-free network using preferential attachment."""
    graph = DirectedGraph()
    n = len(node_ids)
    if n == 0:
        return graph
        
    core_size = min(ba_m, n)
    if core_size == 0: core_size = 1
    
    for nid in node_ids:
        graph.add_node(nid)
        
    degrees = {nid: 0 for nid in node_ids}
    
    # Fully connect the initial core
    for i in range(core_size):
        for j in range(i + 1, core_size):
            u, v = node_ids[i], node_ids[j]
            lat1 = min_latency + rng.random() * (max_latency - min_latency)
            rel1 = min_reliability + rng.random() * (max_reliability - min_reliability)
            graph.add_edge(Edge(u, v, lat1, rel1))
            
            lat2 = min_latency + rng.random() * (max_latency - min_latency)
            rel2 = min_reliability + rng.random() * (max_reliability - min_reliability)
            graph.add_edge(Edge(v, u, lat2, rel2))
            
            degrees[u] += 1
            degrees[v] += 1
            
    # Preferential attachment for the rest
    for i in range(core_size, n):
        u = node_ids[i]
        targets = set()
        available = list(node_ids[:i])
        edges_to_add = min(ba_m, len(available))
        
        while len(targets) < edges_to_add and available:
            weights = []
            for v in available:
                deg = degrees[v]
                bias = node_weights.get(v, 0.0) if node_weights else 0.0
                w = (deg + 1.0) * (1.0 + bias * 5.0) 
                weights.append(w)
                
            total_w = sum(weights)
            if total_w <= 0:
                probs = [1.0/len(available)] * len(available)
            else:
                probs = [w/total_w for w in weights]
                
            r = rng.random()
            cum = 0.0
            selected_v = available[-1]
            for idx, p in enumerate(probs):
                cum += p
                if r <= cum:
                    selected_v = available[idx]
                    break
                    
            targets.add(selected_v)
            available.remove(selected_v)
            
        for v in targets:
            lat1 = min_latency + rng.random() * (max_latency - min_latency)
            rel1 = min_reliability + rng.random() * (max_reliability - min_reliability)
            graph.add_edge(Edge(u, v, lat1, rel1))
            
            lat2 = min_latency + rng.random() * (max_latency - min_latency)
            rel2 = min_reliability + rng.random() * (max_reliability - min_reliability)
            graph.add_edge(Edge(v, u, lat2, rel2))
            
            degrees[u] += 1
            degrees[v] += 1

    return graph


def watts_strogatz_graph(
    node_ids: List[str],
    rng: Random,
    ws_k: int,
    ws_beta: float,
    min_latency: float,
    max_latency: float,
    min_reliability: float,
    max_reliability: float,
    **kwargs
) -> DirectedGraph:
    """Small-world network with local clustering and random shortcuts."""
    graph = DirectedGraph()
    n = len(node_ids)
    if n == 0:
        return graph

    for nid in node_ids:
        graph.add_node(nid)

    # Ensure k is even and less than n
    k = min(ws_k, n - 1)
    if k % 2 != 0:
        k -= 1
    if k < 2:
        k = 2

    # Step 1: Create a regular ring lattice
    edges_set = set()
    for i in range(n):
        for j in range(1, k // 2 + 1):
            target = (i + j) % n
            edges_set.add((i, target))
            edges_set.add((target, i)) # Bi-directional base ring

    # Step 2: Rewire edges with probability beta
    # In a directed graph, we rewire each directed edge independently
    rewired_edges = set()
    for u, v in list(edges_set):
        if rng.random() < ws_beta:
            # Find a new target w
            candidates = [idx for idx in range(n) if idx != u and (u, idx) not in edges_set and (u, idx) not in rewired_edges]
            if candidates:
                new_v = rng.choice(candidates)
                edges_set.remove((u, v))
                rewired_edges.add((u, new_v))
        else:
            rewired_edges.add((u, v))

    # Add edges to the graph
    for u_idx, v_idx in rewired_edges:
        lat = min_latency + rng.random() * (max_latency - min_latency)
        rel = min_reliability + rng.random() * (max_reliability - min_reliability)
        graph.add_edge(Edge(node_ids[u_idx], node_ids[v_idx], lat, rel))

    return graph


def core_periphery_graph(
    node_ids: List[str],
    rng: Random,
    core_ratio: float,
    core_edge_prob: float,
    min_latency: float,
    max_latency: float,
    min_reliability: float,
    max_reliability: float,
    node_weights: Optional[Dict[str, float]] = None,
    **kwargs
) -> DirectedGraph:
    """
    Core-periphery network structure.
    A densely connected core (simulating major mining pools / relay nodes),
    and a loosely connected periphery (simulating edge nodes / ordinary users)
    that mainly connect to the core.
    """
    graph = DirectedGraph()
    n = len(node_ids)
    if n == 0:
        return graph

    for nid in node_ids:
        graph.add_node(nid)

    # Determine core size based on ratio or weights
    core_size = max(1, int(n * core_ratio))
    
    # If weights provided, prefer high-weight nodes (miners) as core
    if node_weights:
        sorted_nodes = sorted(node_ids, key=lambda x: node_weights.get(x, 0.0), reverse=True)
    else:
        sorted_nodes = list(node_ids)
        rng.shuffle(sorted_nodes)

    core_nodes = sorted_nodes[:core_size]
    periphery_nodes = sorted_nodes[core_size:]

    # 1. Connect core nodes densely
    for i in range(len(core_nodes)):
        for j in range(len(core_nodes)):
            if i == j: continue
            if rng.random() <= core_edge_prob:
                lat = rng.uniform(min_latency, max_latency)
                rel = rng.uniform(min_reliability, max_reliability)
                graph.add_edge(Edge(core_nodes[i], core_nodes[j], lat, rel))

    # 2. Connect periphery nodes to the core (1-3 connections each)
    for p_node in periphery_nodes:
        # Number of connections to the core
        num_connections = rng.randint(1, min(3, len(core_nodes)))
        targets = rng.sample(core_nodes, num_connections)
        
        for c_node in targets:
            # Periphery -> Core
            lat1 = rng.uniform(min_latency, max_latency)
            rel1 = rng.uniform(min_reliability, max_reliability)
            graph.add_edge(Edge(p_node, c_node, lat1, rel1))
            
            # Core -> Periphery
            lat2 = rng.uniform(min_latency, max_latency)
            rel2 = rng.uniform(min_reliability, max_reliability)
            graph.add_edge(Edge(c_node, p_node, lat2, rel2))
            
    # 3. Add very sparse connections between periphery nodes (1% chance)
    for i in range(len(periphery_nodes)):
        for j in range(len(periphery_nodes)):
            if i == j: continue
            if rng.random() <= 0.01:
                lat = rng.uniform(min_latency, max_latency)
                rel = rng.uniform(min_reliability, max_reliability)
                graph.add_edge(Edge(periphery_nodes[i], periphery_nodes[j], lat, rel))

    return graph


# Register all built-in topologies
TopologyGenerator.register("random", random_graph)
TopologyGenerator.register("barabasi_albert", barabasi_albert_graph)
TopologyGenerator.register("watts_strogatz", watts_strogatz_graph)
TopologyGenerator.register("core_periphery", core_periphery_graph)