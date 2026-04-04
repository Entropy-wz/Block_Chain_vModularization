import pytest
from blockchain_sandbox.modules.tokenomics_module import TokenomicsModule
from blockchain_sandbox.core.entities import Block
from blockchain_sandbox.core.event_bus import SimpleEventBus

# We create a dummy ISimulationContext for the test
from blockchain_sandbox.core.entities import Node

class DummyContext:
    def __init__(self):
        self._canonical_head = "genesis"
        self._chain_heights = {"genesis": 0}
        self._blocks = {
            "genesis": Block("genesis", None, 0, "genesis", 0)
        }
        self.nodes = {
            "M1": Node("M1", is_miner=True, hash_power=0.5),
            "M2": Node("M2", is_miner=True, hash_power=0.5)
        }
    def get_canonical_head(self):
        return self._canonical_head
    
    @property
    def chain_heights(self):
        return self._chain_heights
        
    @property
    def blocks(self):
        return self._blocks

def test_tokenomics_block_reward():
    """
    Test that when a block is mined, the miner's balance increases.
    """
    module = TokenomicsModule(initial_fiat_balance=100.0, base_token_price=10.0)
    ctx = DummyContext()
    bus = SimpleEventBus()
    module.setup(ctx, bus)
    
    # Manually trigger block mined
    # Simulate M1 mined B1
    payload = {
        "miner_id": "M1",
        "block_id": "B1",
        "parent_id": "genesis",
        "is_private": False
    }
    
    # First we need to manually init the balances normally done in setup()
    # Or just rely on defaultdict doing it. defaultdict will default to 0, 
    # but initial_fiat_balance logic won't be applied. Let's just test token logic.
    
    module._on_block_mined(payload)
    
    # M1 should receive block reward + base token price
    assert module.balances["M1"]["tokens"] > 0


