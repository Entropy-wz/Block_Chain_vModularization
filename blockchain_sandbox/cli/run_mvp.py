from blockchain_sandbox.core.config import SimulationConfig
from blockchain_sandbox.reporting.metrics import build_report, format_report
from blockchain_sandbox.engine.simulation import BlockchainSimulation


def main() -> None:
    config = SimulationConfig(
        total_steps=500,
        random_seed=7,
        num_miners=14,
        num_full_nodes=10,
        edge_probability=0.24,
        base_mine_probability=0.05,
        target_block_interval_steps=6,
    )
    sim = BlockchainSimulation(config)
    result = sim.run()
    report = build_report(result)
    print(format_report(report))


if __name__ == "__main__":
    main()
