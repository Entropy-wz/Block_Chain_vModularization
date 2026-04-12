from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule


@dataclass
class UTXO:
    outpoint: str
    owner: str
    amount: float
    created_in_block: str
    spent: bool = False
    spent_by_tx: str = ""


@dataclass
class TxRecord:
    tx_id: str
    kind: str
    sender: str
    receiver: str
    amount: float
    state: str = "pending"  # pending/confirmed/reverted
    packed_block_id: str = ""
    packed_height: int = -1
    confirmations: int = 0


@dataclass
class DoubleSpendAttempt:
    attempt_id: int
    attacker_id: str
    merchant_id: str
    amount: float
    target_confirmations: int
    public_tx_id: str
    conflict_tx_id: str
    public_anchor_block_id: str
    public_anchor_height: int
    created_step: int
    confirmations_seen: int = 0
    public_confirmed: bool = False
    conflict_released: bool = False
    success_counted: bool = False
    reverted: bool = False
    free_shot_eligible: bool = False


class TokenomicsModule(ISimulationModule):
    """
    UTXO-minimal settlement/economy module with double-spend lifecycle.
    - Tracks pending/confirmed/reverted payment states.
    - Detects "merchant confirmed then reorg reverted" as double-spend success.
    """

    def __init__(
        self,
        initial_fiat_balance: float = 1000.0,
        base_token_price: float = 100.0,
        initial_token_balance: float = 20.0,
        mining_cost_per_step: float = 1.0,
        block_reward_tokens: float = 1.0,
        price_from_orphan: bool = True,
        price_model: str = "orphan_health",
        static_token_price: float = 100.0,
        orphan_penalty_k: float = 2.0,
        price_floor_factor: float = 0.1,
    ) -> None:
        self.initial_fiat_balance = float(initial_fiat_balance)
        self.base_token_price = float(base_token_price)
        self.initial_token_balance = float(initial_token_balance)
        self.mining_cost_per_step = float(mining_cost_per_step)
        self.block_reward_tokens = float(block_reward_tokens)
        self.price_from_orphan = bool(price_from_orphan)
        self.price_model = (price_model or "orphan_health").strip().lower()
        self.static_token_price = float(static_token_price)
        self.orphan_penalty_k = float(orphan_penalty_k)
        self.price_floor_factor = float(price_floor_factor)
        self.current_token_price = float(base_token_price)

        self.ctx: ISimulationContext = None
        self.balances: Dict[str, Dict[str, float]] = {}
        self.powered_off_miners: set[str] = set()

        self.utxos: Dict[str, UTXO] = {}
        self.transactions: Dict[str, TxRecord] = {}
        self.double_spend_attempts: List[DoubleSpendAttempt] = []

        self.ds_attempts = 0
        self.ds_success_count = 0
        self.ds_reorg_reverts = 0
        self.merchant_loss_total = 0.0
        self.attacker_net_profit = 0.0
        self.economy_enabled_effective = True

        self._last_canonical_set: Set[str] = set()
        self._last_canonical_head: str = ""
        self._tx_counter = 0
        self._last_attack_height = -10**9
        self._latest_context_per_attacker: Dict[str, Dict[str, Any]] = {}

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        for node in self.ctx.nodes.values():
            if not node.is_miner:
                continue
            self.balances[node.node_id] = {"fiat": self.initial_fiat_balance, "tokens": self.initial_token_balance}
            self._mint_utxo(node.node_id, self.initial_token_balance, "B0", prefix="genesis")

        canonical_head = self.ctx.get_canonical_head()
        self._last_canonical_head = canonical_head
        self._last_canonical_set = self._canonical_set()

        bus.subscribe(EventTypes.BLOCK_MINED, self._on_block_mined)
        bus.subscribe(EventTypes.AGENT_DECISION_MADE, self._on_agent_decision)
        bus.subscribe(EventTypes.PRIVATE_CHAIN_PUBLISHED, self._on_private_chain_published)

    def on_step_start(self, ctx: ISimulationContext) -> None:
        total_hash = sum(n.hash_power for n in self.ctx.nodes.values() if n.is_miner and n.node_id not in self.powered_off_miners)
        if total_hash > 0:
            for node in self.ctx.nodes.values():
                if not node.is_miner or node.node_id in self.powered_off_miners:
                    continue
                cost = (node.hash_power / total_hash) * max(0.0, self.mining_cost_per_step)
                self.balances[node.node_id]["fiat"] -= cost

        self._update_token_price()
        self._advance_transaction_states()
        self._maybe_create_double_spend_attempt()

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        balance = self.balances.get(miner_id, {"fiat": 0.0, "tokens": 0.0})
        net_worth = balance["fiat"] + (balance["tokens"] * self.current_token_price)
        obs = {
            "tokenomics_current_token_price": round(self.current_token_price, 4),
            "tokenomics_fiat_balance": round(balance["fiat"], 4),
            "tokenomics_token_balance": round(balance["tokens"], 4),
            "tokenomics_estimated_net_worth": round(net_worth, 4),
            "tokenomics_is_powered_off": miner_id in self.powered_off_miners,
            "ds_attempts": self.ds_attempts,
            "ds_success_count": self.ds_success_count,
        }
        obs.update(self.get_double_spend_context(miner_id))
        return obs

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        return (
            "Economic settlement is enabled. Payments can be pending, confirmed, and later reverted by reorg. "
            "Double-spend success is counted only when a merchant-confirmed payment is later reverted."
        )

    def expected_decision_keys(self) -> Dict[str, str]:
        return {"economic_action": "string (none, power_off, power_on)"}

    def get_double_spend_context(self, miner_id: str) -> Dict[str, Any]:
        base = {
            "ds_enabled": bool(getattr(self.ctx.config, "ds_enabled", False)),
            "ds_target_confirmations": int(getattr(self.ctx.config, "ds_target_confirmations", 2)),
            "confirmations_seen": 0,
            "free_shot_eligible": False,
        }
        if miner_id in self._latest_context_per_attacker:
            base.update(self._latest_context_per_attacker[miner_id])
        return base

    def get_summary_metrics(self) -> Dict[str, Any]:
        miner_net_worth: Dict[str, float] = {}
        miner_net_profit: Dict[str, float] = {}
        miner_initial_capital: Dict[str, float] = {}
        positive_profit_sum = 0.0
        baseline = self.initial_fiat_balance + self.initial_token_balance * self.base_token_price
        for node in self.ctx.nodes.values():
            if not node.is_miner:
                continue
            mid = node.node_id
            bal = self.balances.get(mid, {"fiat": 0.0, "tokens": 0.0})
            worth = float(bal.get("fiat", 0.0)) + float(bal.get("tokens", 0.0)) * float(self.current_token_price)
            profit = worth - baseline
            miner_net_worth[mid] = round(worth, 8)
            miner_net_profit[mid] = round(profit, 8)
            miner_initial_capital[mid] = round(baseline, 8)
            if profit > 0:
                positive_profit_sum += profit

        miner_economic_share: Dict[str, float] = {}
        if positive_profit_sum > 1e-12:
            for mid, profit in miner_net_profit.items():
                share = max(0.0, float(profit)) / positive_profit_sum
                miner_economic_share[mid] = round(share, 8)
        else:
            for mid in miner_net_profit.keys():
                miner_economic_share[mid] = 0.0

        ds_public_confirmed_count = 0
        ds_conflict_released_count = 0
        ds_confirmed_and_released_count = 0
        ds_reverts_on_released_count = 0
        for att in self.double_spend_attempts:
            if att.public_confirmed:
                ds_public_confirmed_count += 1
            if att.conflict_released:
                ds_conflict_released_count += 1
            if att.public_confirmed and att.conflict_released:
                ds_confirmed_and_released_count += 1
            if att.reverted and att.conflict_released:
                ds_reverts_on_released_count += 1

        return {
            "ds_attempts": self.ds_attempts,
            "ds_success_count": self.ds_success_count,
            "ds_reorg_reverts": self.ds_reorg_reverts,
            "merchant_loss_total": round(self.merchant_loss_total, 8),
            "attacker_net_profit": round(self.attacker_net_profit, 8),
            "economy_enabled_effective": self.economy_enabled_effective,
            "miner_net_worth": miner_net_worth,
            "miner_net_profit": miner_net_profit,
            "miner_initial_capital": miner_initial_capital,
            "miner_economic_share": miner_economic_share,
            "economic_share_pool_positive": round(positive_profit_sum, 8),
            "initial_capital_per_miner": round(baseline, 8),
            "ds_public_confirmed_count": ds_public_confirmed_count,
            "ds_conflict_released_count": ds_conflict_released_count,
            "ds_confirmed_and_released_count": ds_confirmed_and_released_count,
            "ds_reverts_on_released_count": ds_reverts_on_released_count,
        }

    def _on_block_mined(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        block = payload.get("block")
        if not miner_id or block is None or miner_id not in self.balances:
            return
        reward = max(0.0, self.block_reward_tokens)
        self.balances[miner_id]["tokens"] += reward
        self._mint_utxo(miner_id, reward, block.block_id, prefix="coinbase")

    def _on_private_chain_published(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        if not miner_id:
            return
        for att in reversed(self.double_spend_attempts):
            if att.attacker_id != miner_id:
                continue
            if att.public_confirmed and not att.conflict_released:
                att.conflict_released = True
                # Late release compensation path:
                # if revert happened before release, count success now.
                if att.reverted and not att.success_counted:
                    self._count_double_spend_success(att)
                break

    def _on_agent_decision(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        effective = payload.get("effective")
        if not miner_id or not effective:
            return
        action = (getattr(effective, "economic_action", "none") or "none").strip().lower()
        if action == "power_off":
            if miner_id not in self.powered_off_miners:
                self.powered_off_miners.add(miner_id)
                if miner_id in self.ctx.nodes:
                    self.ctx.nodes[miner_id].hash_power = 0.0
        elif action == "power_on":
            if miner_id in self.powered_off_miners:
                self.powered_off_miners.remove(miner_id)

    def _update_token_price(self) -> None:
        if not self.price_from_orphan:
            if self.price_model == "static":
                self.current_token_price = max(0.0, self.static_token_price)
            else:
                self.current_token_price = max(0.0, self.base_token_price)
            return

        if self.price_model == "static":
            self.current_token_price = max(0.0, self.static_token_price)
            return

        canonical_head = self.ctx.get_canonical_head()
        canonical_h = self.ctx.chain_heights.get(canonical_head, 0)
        storage = getattr(self.ctx, "block_storage", None)
        if storage is not None:
            total_blocks = max(0, len(storage.get_all_summaries()) - 1)
        else:
            total_blocks = max(0, len(self.ctx.blocks) - 1)
        orphan_ratio = 1.0 - (canonical_h / total_blocks) if total_blocks > 0 else 0.0
        k = max(0.0, self.orphan_penalty_k)
        floor = max(0.0, self.price_floor_factor)
        health_factor = max(floor, 1.0 - (orphan_ratio * k))
        self.current_token_price = self.base_token_price * health_factor

    def _advance_transaction_states(self) -> None:
        canonical_set = self._canonical_set()
        canonical_head = self.ctx.get_canonical_head()
        canonical_height = self.ctx.chain_heights.get(canonical_head, 0)

        for att in self.double_spend_attempts:
            pub_tx = self.transactions.get(att.public_tx_id)
            conf_tx = self.transactions.get(att.conflict_tx_id)
            if pub_tx is None or conf_tx is None:
                continue

            if att.public_anchor_block_id in canonical_set:
                att.confirmations_seen = max(0, canonical_height - att.public_anchor_height + 1)
                pub_tx.confirmations = att.confirmations_seen
                if att.confirmations_seen >= att.target_confirmations and not att.public_confirmed:
                    att.public_confirmed = True
                    pub_tx.state = "confirmed"
                    self.balances[att.merchant_id]["tokens"] += att.amount
            else:
                # Reorg knocked out the public payment anchor.
                if att.public_confirmed and not att.reverted:
                    pub_tx.state = "reverted"
                    att.reverted = True
                    self.ds_reorg_reverts += 1
                    self.balances[att.merchant_id]["tokens"] -= att.amount
                    self.merchant_loss_total += att.amount
                    if att.conflict_released and not att.success_counted:
                        self._count_double_spend_success(att)

        self._last_canonical_set = canonical_set
        self._last_canonical_head = canonical_head

    def _maybe_create_double_spend_attempt(self) -> None:
        if not bool(getattr(self.ctx.config, "ds_enabled", False)):
            return

        canonical_head = self.ctx.get_canonical_head()
        canonical_height = self.ctx.chain_heights.get(canonical_head, 0)
        interval = max(1, int(getattr(self.ctx.config, "ds_attack_interval_blocks", 30)))
        if canonical_height <= 0:
            return
        if canonical_height - self._last_attack_height < interval:
            return

        attacker = self._pick_attacker()
        merchant = self._pick_merchant(attacker)
        if not attacker or not merchant:
            return
        amount = float(getattr(self.ctx.config, "ds_payment_amount", 3.0))
        if self._available_tokens(attacker) < amount:
            return

        self._last_attack_height = canonical_height
        self.ds_attempts += 1
        attempt_id = self.ds_attempts
        public_tx_id = self._next_tx_id(prefix="ds_pub")
        conflict_tx_id = self._next_tx_id(prefix="ds_conf")
        target_conf = max(1, int(getattr(self.ctx.config, "ds_target_confirmations", 2)))
        free_shot_depth = max(0, int(getattr(self.ctx.config, "ds_free_shot_depth", 1)))
        private_lead = len(self.ctx.private_chains.get(attacker, []))

        self.transactions[public_tx_id] = TxRecord(
            tx_id=public_tx_id,
            kind="ds_public_payment",
            sender=attacker,
            receiver=merchant,
            amount=amount,
            state="pending",
            packed_block_id=canonical_head,
            packed_height=canonical_height,
        )
        self.transactions[conflict_tx_id] = TxRecord(
            tx_id=conflict_tx_id,
            kind="ds_conflict_payment",
            sender=attacker,
            receiver=attacker,
            amount=amount,
            state="pending",
            packed_block_id="",
            packed_height=-1,
        )
        self._reserve_utxo(attacker, amount, public_tx_id)

        attempt = DoubleSpendAttempt(
            attempt_id=attempt_id,
            attacker_id=attacker,
            merchant_id=merchant,
            amount=amount,
            target_confirmations=target_conf,
            public_tx_id=public_tx_id,
            conflict_tx_id=conflict_tx_id,
            public_anchor_block_id=canonical_head,
            public_anchor_height=canonical_height,
            created_step=self.ctx.current_step,
            free_shot_eligible=private_lead >= free_shot_depth,
        )
        self.double_spend_attempts.append(attempt)
        self._latest_context_per_attacker[attacker] = {
            "ds_enabled": True,
            "ds_target_confirmations": target_conf,
            "confirmations_seen": 0,
            "free_shot_eligible": attempt.free_shot_eligible,
        }

    def _pick_attacker(self) -> str:
        selfish_ids = [n.node_id for n in self.ctx.nodes.values() if n.is_miner and n.strategy_name == "selfish"]
        if not selfish_ids:
            return ""
        return max(selfish_ids, key=lambda mid: self.ctx.nodes[mid].hash_power)

    def _pick_merchant(self, attacker_id: str) -> str:
        forced = (getattr(self.ctx.config, "ds_merchant_id", "") or "").strip()
        if forced and forced in self.ctx.nodes and forced != attacker_id:
            return forced
        candidates = [
            n.node_id
            for n in self.ctx.nodes.values()
            if n.is_miner and n.node_id != attacker_id and n.strategy_name != "selfish"
        ]
        if not candidates:
            return ""
        return max(candidates, key=lambda mid: self.ctx.nodes[mid].hash_power)

    def _available_tokens(self, owner: str) -> float:
        total = 0.0
        for utxo in self.utxos.values():
            if utxo.owner == owner and not utxo.spent:
                total += utxo.amount
        return total

    def _reserve_utxo(self, owner: str, amount: float, spender_tx_id: str) -> None:
        need = float(amount)
        for utxo in self.utxos.values():
            if need <= 1e-12:
                break
            if utxo.owner != owner or utxo.spent:
                continue
            utxo.spent = True
            utxo.spent_by_tx = spender_tx_id
            need -= utxo.amount

    def _mint_utxo(self, owner: str, amount: float, block_id: str, prefix: str) -> None:
        self._tx_counter += 1
        outpoint = f"{prefix}_{self._tx_counter}:0"
        self.utxos[outpoint] = UTXO(outpoint=outpoint, owner=owner, amount=float(amount), created_in_block=block_id)

    def _next_tx_id(self, prefix: str) -> str:
        self._tx_counter += 1
        return f"{prefix}_{self._tx_counter}"

    def _canonical_set(self) -> Set[str]:
        out: Set[str] = set()
        cur = self.ctx.get_canonical_head()
        b = getattr(self.ctx, "block_storage", None)
        while cur is not None:
            if b:
                summary = b.get_summary(cur)
                if not summary:
                    break
                out.add(cur)
                cur = summary.parent_id
            else:
                if cur not in self.ctx.blocks:
                    break
                out.add(cur)
                cur = self.ctx.blocks[cur].parent_id
        return out

    def _count_double_spend_success(self, att: DoubleSpendAttempt) -> None:
        if att.success_counted:
            return
        att.success_counted = True
        conf_tx = self.transactions.get(att.conflict_tx_id)
        if conf_tx is not None:
            conf_tx.state = "confirmed"
        self.ds_success_count += 1
        self.attacker_net_profit += att.amount
        if att.attacker_id in self.balances:
            self.balances[att.attacker_id]["tokens"] += att.amount
