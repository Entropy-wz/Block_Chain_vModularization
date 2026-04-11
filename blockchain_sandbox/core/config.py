from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    total_steps: int = 400
    random_seed: int = 42

    num_miners: int = 12
    num_full_nodes: int = 8

    # Probability for directed edge creation in random graph.
    edge_probability: float = 0.25
    topology_type: str = "random"  # "random", "barabasi_albert", "watts_strogatz", "core_periphery"
    topology_ba_m: int = 3
    topology_ws_k: int = 4
    topology_ws_beta: float = 0.1
    topology_core_ratio: float = 0.05
    topology_core_edge_prob: float = 0.8
    min_latency: float = 1.0
    max_latency: float = 4.0
    min_reliability: float = 0.92
    max_reliability: float = 1.0

    # Mining parameters.
    base_mine_probability: float = 0.05
    target_block_interval_steps: int = 5

    # Controls protocol behavior.
    max_hops_for_propagation: int = 4
    
    # Prune parameters
    prune_interval_steps: int = 50
    prune_max_depth: int = 15


@dataclass(frozen=True)
class LLMConfig:
    # Uses an OpenAI-compatible API endpoint.
    backend: str = "compatible"
    model: str = "gpt-5.4-mini"
    temperature: float = 0.2
    max_output_tokens: int = 220
    timeout_seconds: int = 30
    seed: int = 1234
    api_key: str = ""
    base_url: str = ""
    use_chat_completions: bool = False
    max_concurrent_requests: int = 5
    decision_cooldown_steps: int = 10
    force_llm_on_fork: bool = True
    enable_cache: bool = True
    honest_use_llm: bool = False


@dataclass(frozen=True)
class AgenticSimulationConfig:
    total_steps: int = 300
    random_seed: int = 11

    num_miners: int = 10
    num_full_nodes: int = 20

    edge_probability: float = 0.22
    topology_type: str = "random"  # "random", "barabasi_albert", "watts_strogatz", "core_periphery"
    topology_ba_m: int = 3
    topology_ws_k: int = 4
    topology_ws_beta: float = 0.1
    topology_core_ratio: float = 0.05
    topology_core_edge_prob: float = 0.8
    min_latency: float = 1.0
    max_latency: float = 5.0
    min_reliability: float = 0.9
    max_reliability: float = 1.0

    # Markov-style block discovery:
    # 1) each step discovers a block with this probability
    # 2) winner miner is sampled by hash_power / total_hash_power
    # Lower chance implies longer block intervals, reducing simultaneous mining (orphans)
    # Set to 0.02 so expectation (1/0.02=50) >> max_latency (5.0), effectively eliminating natural orphans
    block_discovery_chance: float = 0.02

    # Reputation threshold below which a node is physically disconnected by peers
    ban_reputation_threshold: float = -10.0
    # Reputation threshold above which a banned node can be unbanned
    unban_reputation_threshold: float = -2.0

    # Modules
    enable_forum: bool = True
    selfish_strategy: str = "classic"
    
    # Attack switches
    enable_attack_jamming: bool = True
    # Placeholder for future attacks:
    # enable_attack_eclipse: bool = False
    
    active_modules: list[str] = None

    max_hops_for_propagation: int = 5
    default_private_release_threshold: int = 2
    max_steps_of_jam_effect: int = 6
    snapshot_interval_blocks: int = 10
    
    # Prune parameters
    prune_interval_steps: int = 50
    prune_max_depth: int = 15
