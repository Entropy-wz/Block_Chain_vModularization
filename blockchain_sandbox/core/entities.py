from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


@dataclass(frozen=True)
class Block:
    block_id: str
    parent_id: Optional[str]
    height: int
    miner_id: str
    created_at_step: int


@dataclass
class Node:
    node_id: str
    is_miner: bool
    hash_power: float = 0.0
    strategy_name: str = "honest"
    known_blocks: Set[str] = field(default_factory=set)
    local_head_id: Optional[str] = None
    is_banned: bool = False

    def observe_block(self, block_id: str, block_height: int, chain_heights: Dict[str, int]) -> bool:
        if block_id in self.known_blocks:
            return False
        self.known_blocks.add(block_id)

        if self.local_head_id is None:
            self.local_head_id = block_id
            return True

        current_height = chain_heights.get(self.local_head_id, -1)
        if block_height > current_height:
            self.local_head_id = block_id
            return True

        return False

