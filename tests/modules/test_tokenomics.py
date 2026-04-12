from types import SimpleNamespace

from blockchain_sandbox.cli.run_llm_sandbox import resolve_economy_enabled
from blockchain_sandbox.core.entities import Block, Node
from blockchain_sandbox.core.event_bus import SimpleEventBus
from blockchain_sandbox.modules.tokenomics_module import TokenomicsModule


class DummyContext:
    def __init__(self):
        self._canonical_head = "B2"
        self._chain_heights = {"B0": 0, "B1": 1, "B2": 2}
        self._blocks = {
            "B0": Block("B0", None, 0, "genesis", 0),
            "B1": Block("B1", "B0", 1, "M1", 1),
            "B2": Block("B2", "B1", 2, "M3", 2),
        }
        self.nodes = {
            "M0": Node("M0", is_miner=True, hash_power=0.3, strategy_name="selfish"),
            "M1": Node("M1", is_miner=True, hash_power=0.3, strategy_name="selfish"),
            "M2": Node("M2", is_miner=True, hash_power=0.2, strategy_name="honest"),
            "M3": Node("M3", is_miner=True, hash_power=0.2, strategy_name="honest"),
        }
        self.private_chains = {"M0": [], "M1": ["P1"], "M2": [], "M3": []}
        self.current_step = 120
        self.config = SimpleNamespace(
            ds_enabled=True,
            ds_target_confirmations=2,
            ds_free_shot_depth=1,
            ds_payment_amount=2.0,
            ds_attack_interval_blocks=1,
            ds_merchant_id="M2",
        )

    def get_canonical_head(self):
        return self._canonical_head

    @property
    def chain_heights(self):
        return self._chain_heights

    @property
    def blocks(self):
        return self._blocks

    @property
    def block_storage(self):
        return None


def test_tokenomics_block_reward():
    module = TokenomicsModule(initial_fiat_balance=100.0, base_token_price=10.0)
    ctx = DummyContext()
    bus = SimpleEventBus()
    module.setup(ctx, bus)
    module._on_block_mined({"miner_id": "M1", "block": Block("B9", "B2", 3, "M1", 9)})
    assert module.balances["M1"]["tokens"] > 0


def test_transaction_confirm_then_revert_counted_once():
    module = TokenomicsModule(initial_fiat_balance=100.0, base_token_price=10.0, initial_token_balance=30.0)
    ctx = DummyContext()
    bus = SimpleEventBus()
    module.setup(ctx, bus)

    # step 1: create attack attempt and confirm public payment on canonical branch B1->B2
    module.on_step_start(ctx)
    assert module.ds_attempts == 1
    ctx._blocks["B3"] = Block("B3", "B2", 3, "M3", 3)
    ctx._chain_heights["B3"] = 3
    ctx._canonical_head = "B3"
    ctx.current_step += 1
    module.on_step_start(ctx)
    att = module.double_spend_attempts[0]
    assert att.public_confirmed is True

    # attacker releases private chain after merchant confirmation
    module._on_private_chain_published({"miner_id": att.attacker_id, "blocks": ["PX"]})

    # step 2: reorg to branch that excludes B1/B2 to trigger revert success
    ctx._blocks["R1"] = Block("R1", "B0", 1, "M1", 21)
    ctx._blocks["R2"] = Block("R2", "R1", 2, "M1", 22)
    ctx._blocks["R3"] = Block("R3", "R2", 3, "M1", 23)
    ctx._canonical_head = "R3"
    ctx._chain_heights.update({"R1": 1, "R2": 2, "R3": 3})
    ctx.current_step += 1
    module.on_step_start(ctx)

    assert module.ds_success_count == 1
    assert module.ds_reorg_reverts >= 1

    # step 3: run again, ensure no duplicate counting for the same reverted tx
    prev_success = module.ds_success_count
    prev_reverts = module.ds_reorg_reverts
    ctx.current_step += 1
    module.on_step_start(ctx)
    assert module.ds_success_count == prev_success
    assert module.ds_reorg_reverts == prev_reverts


def test_revert_before_release_still_counts_success_once():
    module = TokenomicsModule(initial_fiat_balance=100.0, base_token_price=10.0, initial_token_balance=30.0)
    ctx = DummyContext()
    bus = SimpleEventBus()
    module.setup(ctx, bus)

    # create attempt and confirm public payment
    module.on_step_start(ctx)
    assert module.ds_attempts == 1
    ctx._blocks["B3"] = Block("B3", "B2", 3, "M3", 3)
    ctx._chain_heights["B3"] = 3
    ctx._canonical_head = "B3"
    ctx.current_step += 1
    module.on_step_start(ctx)
    att = module.double_spend_attempts[0]
    assert att.public_confirmed is True

    # reorg first (before private release)
    ctx._blocks["R1"] = Block("R1", "B0", 1, "M1", 21)
    ctx._blocks["R2"] = Block("R2", "R1", 2, "M1", 22)
    ctx._blocks["R3"] = Block("R3", "R2", 3, "M1", 23)
    ctx._canonical_head = "R3"
    ctx._chain_heights.update({"R1": 1, "R2": 2, "R3": 3})
    ctx.current_step += 1
    module.on_step_start(ctx)
    assert module.ds_reorg_reverts >= 1
    assert module.ds_success_count == 0

    # private release arrives later -> should compensate success exactly once
    module._on_private_chain_published({"miner_id": att.attacker_id, "blocks": ["PX"]})
    assert module.ds_success_count == 1
    prev_success = module.ds_success_count
    module._on_private_chain_published({"miner_id": att.attacker_id, "blocks": ["PY"]})
    assert module.ds_success_count == prev_success


def test_double_spend_strategy_forces_economy_enabled():
    assert resolve_economy_enabled("stubborn_ds", "0") is True
    assert resolve_economy_enabled("classic", "0") is False
    assert resolve_economy_enabled("classic", "1") is True


