from __future__ import annotations

import os
import time
from random import Random
from blockchain_sandbox.core.topology_generator import TopologyGenerator

def verify_topology(topology_type: str, num_nodes: int = 50):
    print(f"\n{'='*50}")
    print(f"Verifying Topology: {topology_type} (Nodes: {num_nodes})")
    print(f"{'='*50}")
    
    rng = Random(42)
    node_ids = [f"N{i}" for i in range(num_nodes)]
    
    # Give some nodes higher weights to simulate miners
    node_weights = {nid: 1.0 for nid in node_ids}
    for i in range(min(5, num_nodes)):
        node_weights[node_ids[i]] = 10.0
        
    start_time = time.time()
    
    try:
        graph = TopologyGenerator.generate(
            topology_type=topology_type,
            node_ids=node_ids,
            rng=rng,
            edge_probability=0.1,
            min_latency=1.0,
            max_latency=5.0,
            min_reliability=0.9,
            max_reliability=1.0,
            ba_m=3,
            ws_k=4,
            ws_beta=0.1,
            core_ratio=0.1,
            core_edge_prob=0.8,
            node_weights=node_weights
        )
        
        elapsed = time.time() - start_time
        
        node_count = len(list(graph.nodes()))
        edge_count = graph.edge_count()
        avg_degree = edge_count / max(1, node_count)
        
        # Calculate max and min degrees
        out_degrees = [len(graph.neighbors(nid)) for nid in node_ids]
        max_deg = max(out_degrees) if out_degrees else 0
        min_deg = min(out_degrees) if out_degrees else 0
        
        print(f"✓ Generation Successful ({elapsed:.4f}s)")
        print(f"  - Nodes: {node_count}")
        print(f"  - Edges: {edge_count}")
        print(f"  - Avg Degree: {avg_degree:.2f}")
        print(f"  - Degree Range: {min_deg} ~ {max_deg}")
        
        # Specific checks based on topology
        if topology_type == "core_periphery":
            core_size = max(1, int(num_nodes * 0.1))
            print(f"  - Expected Core Size: {core_size}")
            # The top weighted nodes should have highest degrees
            top_weighted = sorted(node_ids, key=lambda x: node_weights[x], reverse=True)[:core_size]
            for i, n in enumerate(top_weighted):
                deg = len(graph.neighbors(n))
                print(f"    Core Node {n} degree: {deg} (Expected high)")
                
        elif topology_type == "barabasi_albert":
            print("  - BA usually exhibits 'rich get richer' (hub nodes)")
            sorted_degs = sorted(out_degrees, reverse=True)
            print(f"    Top 5 degrees: {sorted_degs[:5]}")
            
    except Exception as e:
        print(f"❌ Verification Failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    topologies = ["random", "barabasi_albert", "watts_strogatz", "core_periphery"]
    
    print("Testing Topology Generator Registry...")
    print(f"Registered Types: {list(TopologyGenerator._registry.keys())}")
    
    for topo in topologies:
        verify_topology(topo)
        
    print("\nAll verifications completed!")

if __name__ == "__main__":
    main()
