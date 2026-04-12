from types import SimpleNamespace

from blockchain_sandbox.reporting.agentic_metrics import _orphan_breakdown


def test_orphan_breakdown_adds_up():
    result = SimpleNamespace(
        blocks={
            "B0": SimpleNamespace(block_id="B0", miner_id="genesis"),
            "B1": SimpleNamespace(block_id="B1", miner_id="M3"),  # honest orphan
            "B2": SimpleNamespace(block_id="B2", miner_id="M0"),  # selfish orphan (published)
            "B3": SimpleNamespace(block_id="B3", miner_id="M0"),  # selfish orphan (unpublished)
            "B4": SimpleNamespace(block_id="B4", miner_id="M1"),  # canonical
        },
        nodes={
            "M0": SimpleNamespace(strategy_name="selfish"),
            "M1": SimpleNamespace(strategy_name="selfish"),
            "M3": SimpleNamespace(strategy_name="honest"),
        },
        private_chain_lengths={"M0": 1},
    )
    canonical_set = {"B0", "B4"}

    wasted_honest, unpublished_selfish, published_selfish = _orphan_breakdown(result, canonical_set)

    assert wasted_honest == 1
    assert unpublished_selfish == 1
    assert published_selfish == 1
