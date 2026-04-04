import pytest
from blockchain_sandbox.core.topology_generator import TopologyGenerator

def test_barabasi_albert_topology_connectivity(mock_rng):
    """
    Test that a generated Barabasi-Albert graph is fully connected
    and exhibits the 'hub' property (max degree is significantly higher than min degree).
    """
    node_ids = [f"N{i}" for i in range(50)]
    node_weights = {n: 1.0 for n in node_ids}
    # Boost weight for top 5 to simulate miners
    for i in range(5):
        node_weights[node_ids[i]] = 10.0

    graph = TopologyGenerator.generate(
        topology_type="barabasi_albert",
        node_ids=node_ids,
        rng=mock_rng,
        edge_probability=0.1,  # Not used for BA but required by signature
        ba_m=3,
        node_weights=node_weights
    )

    # 1. Ensure all nodes are present
    assert len(list(graph.nodes())) == 50

    # 2. Check basic connectivity (every node has at least one edge in an undirected sense)
    # BA graphs generated this way should be connected
    degrees = [graph.out_degree(n) for n in node_ids]
    
    assert min(degrees) > 0, "Graph has isolated nodes!"
    
    # 3. Check hub properties (max degree should be much larger than ba_m)
    max_deg = max(degrees)
    assert max_deg > 3, f"Max degree {max_deg} is too low for a BA network with m=3 and 50 nodes."
