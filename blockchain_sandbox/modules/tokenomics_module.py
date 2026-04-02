import os
from typing import Any, Dict

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule


class TokenomicsModule(ISimulationModule):
    """
    Simulates the economic incentives of a blockchain network.
    
    Miners spend 'funds' to mine (hash power cost) and earn 'tokens' (Coinbase reward) 
    when their blocks are added to the canonical chain.
    The fiat price of the token fluctuates based on network health (orphan rate).
    Miners can decide to 'power_off' if mining becomes unprofitable.
    """
    
    def __init__(self, initial_fiat_balance: float = 1000.0, base_token_price: float = 100.0):
        self.initial_fiat_balance = initial_fiat_balance
        self.base_token_price = base_token_price
        
        self.current_token_price = base_token_price
        
        # Miner balances: miner_id -> {'fiat': float, 'tokens': float}
        self.balances: Dict[str, Dict[str, float]] = {}
        
        # Track powered off miners
        self.powered_off_miners: set[str] = set()
        
        self.ctx: ISimulationContext = None

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        
        # Initialize balances for all miners
        for node in self.ctx.nodes.values():
            if node.is_miner:
                self.balances[node.node_id] = {
                    "fiat": self.initial_fiat_balance,
                    "tokens": 0.0
                }
                
        bus.subscribe(EventTypes.BLOCK_MINED, self._on_block_mined)
        bus.subscribe(EventTypes.AGENT_DECISION_MADE, self._on_agent_decision)

    def on_step_start(self, ctx: ISimulationContext) -> None:
        # Deduct step costs for hashing
        # The cost is proportional to hash_power
        total_hash = sum(n.hash_power for n in self.ctx.nodes.values() if n.is_miner)
        if total_hash <= 0:
            return
            
        for node in self.ctx.nodes.values():
            if node.is_miner and node.node_id not in self.powered_off_miners:
                # E.g., cost per step for 100% hash power is 1.0 fiat
                cost = (node.hash_power / total_hash) * 1.0
                self.balances[node.node_id]["fiat"] -= cost

    def _on_block_mined(self, payload: Dict[str, Any]) -> None:
        # Simplification: Reward the miner immediately upon finding the block
        # In a real blockchain, rewards mature after 100 blocks or so and only on canonical chain.
        # But for sandbox LLM dynamics, immediate token reward helps them feel "rich"
        miner_id = payload.get("miner_id")
        block = payload.get("block")
        if miner_id and miner_id in self.balances:
            self.balances[miner_id]["tokens"] += 1.0
            
        # Update Token Price roughly based on orphan rate
        # To keep it simple, if network is messy, price drops
        canonical_head = self.ctx.get_canonical_head()
        if canonical_head != "B0":
            canonical_h = self.ctx.chain_heights.get(canonical_head, 0)
            total_blocks = len(self.ctx.blocks) - 1 # excluding genesis
            
            # Orphan ratio 
            orphan_ratio = 1.0 - (canonical_h / total_blocks) if total_blocks > 0 else 0.0
            
            # If orphan ratio is high, price plummets. 
            health_factor = max(0.1, 1.0 - (orphan_ratio * 2.0))
            self.current_token_price = self.base_token_price * health_factor

    def _on_agent_decision(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        effective = payload.get("effective")
        if not miner_id or not effective:
            return

        # Handle power_off action
        action = (getattr(effective, "economic_action", "none") or "none").strip().lower()
        if action == "power_off":
            if miner_id not in self.powered_off_miners:
                self.powered_off_miners.add(miner_id)
                # Set their hash power to 0
                if miner_id in self.ctx.nodes:
                    self.ctx.nodes[miner_id].hash_power = 0.0
        elif action == "power_on":
            if miner_id in self.powered_off_miners:
                self.powered_off_miners.remove(miner_id)
                # Restoring hash power requires saving original hash power, but for simplicity
                # we assume they just want to turn back on (we will need a mechanism to remember original hash)

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        balance = self.balances.get(miner_id, {"fiat": 0.0, "tokens": 0.0})
        net_worth = balance["fiat"] + (balance["tokens"] * self.current_token_price)
        
        return {
            "tokenomics_current_token_price": round(self.current_token_price, 2),
            "tokenomics_fiat_balance": round(balance["fiat"], 2),
            "tokenomics_token_balance": round(balance["tokens"], 2),
            "tokenomics_estimated_net_worth": round(net_worth, 2),
            "tokenomics_is_powered_off": miner_id in self.powered_off_miners
        }

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        return (
            "Tokenomics guidance: Mining costs 'fiat' money every step based on your hash power. "
            "You earn 'tokens' for mining blocks. The fiat value of tokens fluctuates. "
            "If you are losing too much fiat and token price is low, you can output economic_action='power_off' "
            "to stop mining and save fiat. You can output economic_action='none' to keep mining."
        )

    def expected_decision_keys(self) -> Dict[str, str]:
        return {
            "economic_action": "string (none, power_off)"
        }
