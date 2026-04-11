from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .entities import Block

@dataclass
class BlockSummary:
    """Lightweight summary of a block kept in memory after pruning."""
    block_id: str
    parent_id: Optional[str]
    height: int
    miner_id: str

import tempfile
import uuid
import shutil
import time

class BlockStorage:
    """
    Finality-aware storage manager for Blocks.
    Splits blocks into hot (memory, full Block objects) and cold (disk/summary, BlockSummary objects).
    """
    def __init__(self, data_dir: Optional[Path] = None):
        self.hot_blocks: Dict[str, Block] = {}
        self.summaries: Dict[str, BlockSummary] = {}
        self._closed = False
        
        # If no explicit data_dir is provided by persistence, create a temp dir path managed by us
        if not data_dir:
            cold_dir = os.getenv("SANDBOX_COLD_STORAGE_DIR", "").strip()
            if cold_dir:
                self._temp_dir_path = None
                data_dir = Path(cold_dir)
            else:
                self._temp_dir_path = Path(tempfile.mkdtemp(prefix="sandbox_cold_"))
                data_dir = self._temp_dir_path
        else:
            self._temp_dir_path = None
            
        # Simple JSONL archive stream
        self.archive_file: Path = data_dir / f"cold_archive_{uuid.uuid4().hex[:8]}.jsonl"
        self.archive_file.parent.mkdir(parents=True, exist_ok=True)
        self._archive_handle = open(self.archive_file, "w", encoding="utf-8")

    def cleanup(self) -> None:
        """Explicit cleanup method to handle resource teardown cleanly."""
        if self._closed:
            return

        if hasattr(self, '_archive_handle') and self._archive_handle and not self._archive_handle.closed:
            try:
                self._archive_handle.close()
            except Exception:
                pass
            finally:
                self._archive_handle = None

        if getattr(self, '_temp_dir_path', None):
            for _ in range(3):
                try:
                    shutil.rmtree(self._temp_dir_path, ignore_errors=True)
                    break
                except Exception:
                    time.sleep(0.1)
            self._temp_dir_path = None

        self._closed = True

    def __del__(self):
        self.cleanup()

    def add_block(self, block: Block) -> None:
        self.hot_blocks[block.block_id] = block
        self.summaries[block.block_id] = BlockSummary(
            block_id=block.block_id,
            parent_id=block.parent_id,
            height=block.height,
            miner_id=block.miner_id
        )

    def get_block(self, block_id: str) -> Optional[Block]:
        return self.hot_blocks.get(block_id)

    def get_summary(self, block_id: str) -> Optional[BlockSummary]:
        return self.summaries.get(block_id)

    def get_all_summaries(self) -> Dict[str, BlockSummary]:
        return self.summaries

    def __contains__(self, block_id: str) -> bool:
        return block_id in self.hot_blocks

    def __len__(self) -> int:
        return len(self.hot_blocks)

    def prune_frontier(self, active_heads: Set[str], max_depth: int) -> int:
        """
        Walks back from active_heads. Any block deeper than max_depth from all active heads
        is considered finalized and pruned from hot_blocks (written to cold storage).
        """
        reachable_hot: Set[str] = set()
        
        # Traverse backwards from each head, up to max_depth
        for head in active_heads:
            curr = head
            depth = 0
            while curr and depth <= max_depth:
                reachable_hot.add(curr)
                summary = self.summaries.get(curr)
                if not summary:
                    break
                curr = summary.parent_id
                depth += 1

        # Identify blocks to prune (in hot but not in reachable_hot)
        to_prune = set(self.hot_blocks.keys()) - reachable_hot
        
        if to_prune and self._archive_handle:
            for bid in to_prune:
                block = self.hot_blocks[bid]
                # Write full block to archive
                row = {
                    "block_id": block.block_id,
                    "parent_id": block.parent_id,
                    "height": block.height,
                    "miner_id": block.miner_id,
                    "created_at_step": block.created_at_step,
                }
                self._archive_handle.write(json.dumps(row) + "\n")
                
        # Remove from hot blocks
        for bid in to_prune:
            del self.hot_blocks[bid]

        return len(to_prune)
    
    def reconstruct_all_blocks(self) -> Dict[str, Block]:
        """
        Reconstructs the full block dictionary (hot + cold) for reporting/visualization.
        WARNING: This loads all cold blocks back into memory. Should only be called at simulation end.
        """
        all_blocks: Dict[str, Block] = dict(self.hot_blocks)
        
        if self._archive_handle:
            self._archive_handle.flush()
            
        if self.archive_file and self.archive_file.exists():
            with open(self.archive_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    data = json.loads(line)
                    if data["block_id"] not in all_blocks:
                        all_blocks[data["block_id"]] = Block(
                            block_id=data["block_id"],
                            parent_id=data["parent_id"],
                            height=data["height"],
                            miner_id=data["miner_id"],
                            created_at_step=data["created_at_step"]
                        )
        return all_blocks
