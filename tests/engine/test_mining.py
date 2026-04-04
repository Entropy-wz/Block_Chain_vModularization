import pytest
from blockchain_sandbox.engine.agentic_simulation import AgenticBlockchainSimulation
from blockchain_sandbox.core.config import AgenticSimulationConfig
from blockchain_sandbox.core.config import LLMConfig
from blockchain_sandbox.core.topology_generator import TopologyGenerator

def test_hash_power_distribution(mock_rng):
    """
    Test that _sample_winner_by_hash_power selects winners 
    roughly proportional to their assigned hash power.
    """
    # Pass a valid LLMConfig instance. Pydantic might not expect "provider" here
    # depending on what LLMConfig actually accepts, or maybe it expects "config_file"
    # Wait, let's just supply an empty one or a minimal required one
    # If we look at core/config.py LLMConfig has provider_config as dict
    config = AgenticSimulationConfig(
        num_miners=5,
        num_full_nodes=0, # purely test miners
        total_steps=10,
        topology_type="random"
    )
    llm_config = LLMConfig(
        backend="dummy", 
        api_key="dummy_key", # Bypass backend check
        base_url="http://dummy"
    )
    
    # We patch the random instance of the simulation to be deterministic
    sim = AgenticBlockchainSimulation(config, llm_config=llm_config)
    sim.rng = mock_rng
    
    # Set explicit hash powers
    # Total hash power = 100 + 50 + 50 + 10 + 10 = 220
    for node_id in sim.nodes:
        if node_id == "M0": sim.nodes[node_id].hash_power = 100
        elif node_id == "M1": sim.nodes[node_id].hash_power = 50
        elif node_id == "M2": sim.nodes[node_id].hash_power = 50
        elif node_id == "M3": sim.nodes[node_id].hash_power = 10
        elif node_id == "M4": sim.nodes[node_id].hash_power = 10
    
    # Simulate 1000 winner samples
    # We must construct miner_hash_power just as _sample_winner_by_hash_power expects
    win_counts = {m: 0 for m in ["M0", "M1", "M2", "M3", "M4"]}
    num_samples = 1000
    
    for _ in range(num_samples):
        winner = sim._sample_winner_by_hash_power()
        win_counts[winner] += 1
        
    # Check assertions with a margin of error (e.g. +/- 5% absolute)
    assert 400 < win_counts["M0"] < 510, f"M0 wins {win_counts['M0']} out of bounds"
    assert 180 < win_counts["M1"] < 280, f"M1 wins {win_counts['M1']} out of bounds"
    assert 180 < win_counts["M2"] < 280, f"M2 wins {win_counts['M2']} out of bounds"
    assert 10 < win_counts["M3"] < 90, f"M3 wins {win_counts['M3']} out of bounds"
    assert 10 < win_counts["M4"] < 90, f"M4 wins {win_counts['M4']} out of bounds"

    sim.block_storage.cleanup()
