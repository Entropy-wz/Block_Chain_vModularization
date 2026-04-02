from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule


class BlockWindowSnapshot:
    def __init__(
        self,
        step: int,
        mined_block_count: int,
        window_block_ids: List[str],
        tree_lines: List[str],
        window_orphan_count: int,
        canonical_head_id: str,
        heaviest_head_id: str,
        forum_window_posts: int,
        forum_window_avg_tone: float,
        forum_hot_board: str,
        forum_top_target: str,
        max_fork_degree: int,
        longest_branch_len: int,
        branch_count: int,
        canonical_coverage: float,
    ):
        self.step = step
        self.mined_block_count = mined_block_count
        self.window_block_ids = window_block_ids
        self.tree_lines = tree_lines
        self.window_orphan_count = window_orphan_count
        self.canonical_head_id = canonical_head_id
        self.heaviest_head_id = heaviest_head_id
        self.forum_window_posts = forum_window_posts
        self.forum_window_avg_tone = forum_window_avg_tone
        self.forum_hot_board = forum_hot_board
        self.forum_top_target = forum_top_target
        self.max_fork_degree = max_fork_degree
        self.longest_branch_len = longest_branch_len
        self.branch_count = branch_count
        self.canonical_coverage = canonical_coverage


class MetricsObserverModule(ISimulationModule):
    def __init__(
        self,
        snapshot_interval_blocks: int = 10,
        snapshot_callback: Optional[Callable[[BlockWindowSnapshot, Dict[str, int]], None]] = None,
    ):
        self.snapshot_interval_blocks = max(1, snapshot_interval_blocks)
        self.snapshot_callback = snapshot_callback
        
        self.ctx: ISimulationContext = None
        self.bus: IEventBus = None
        
        self.snapshots: List[BlockWindowSnapshot] = []
        self.mined_block_ids: List[str] = []
        self.gamma_estimates: Dict[str, float] = {}
        self.network_efficiency: float = 0.0
        self.orphan_blocks: int = 0
        
        self._last_snapshot_post_count = 0

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        self.bus = bus
        bus.subscribe(EventTypes.BLOCK_MINED, self._on_block_mined)
        bus.subscribe(EventTypes.SIMULATION_END, self._on_simulation_end)

    def on_step_start(self, ctx: ISimulationContext) -> None:
        pass

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        return {}

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        return ""

    def expected_decision_keys(self) -> Dict[str, str]:
        return {}
        
    def _on_block_mined(self, payload: Dict[str, Any]) -> None:
        block = payload.get("block")
        if block:
            self.mined_block_ids.append(block.block_id)
            self._maybe_capture_snapshot(self.ctx.current_time)

    def _on_simulation_end(self, payload: Any) -> None:
        # Compute final global metrics
        self.gamma_estimates = self._compute_all_gamma()
        self.network_efficiency = self.ctx.graph.avg_shortest_latency()
        canonical_head = self.ctx.get_canonical_head()
        self.orphan_blocks = self._count_orphans(canonical_head)

    def _maybe_capture_snapshot(self, now_time: float) -> None:
        mined = len(self.mined_block_ids)
        if mined == 0 or mined % self.snapshot_interval_blocks != 0:
            return
        if self.snapshots and self.snapshots[-1].mined_block_count == mined:
            return

        window = self.mined_block_ids[-self.snapshot_interval_blocks:]
        canonical_head = self.ctx.get_canonical_head()
        heaviest_head = self._heaviest_head()
        canonical_path = self._canonical_set(canonical_head)
        orphan_count = sum(1 for bid in window if bid not in canonical_path)
        tree_lines = self._build_window_tree_lines(window)
        max_fork_degree, longest_branch_len, branch_count = self._window_tree_metrics(window)
        canonical_coverage = (sum(1 for bid in window if bid in canonical_path) / len(window)) if window else 0.0

        forum = self._forum_state()
        new_posts = forum.posts[self._last_snapshot_post_count :] if forum else []
        self._last_snapshot_post_count = len(forum.posts) if forum else 0
        avg_tone = (sum(p.tone for p in new_posts) / len(new_posts)) if new_posts else 0.0
        
        board_count: Dict[str, int] = {}
        target_count: Dict[str, int] = {}
        for p in new_posts:
            board_count[p.board] = board_count.get(p.board, 0) + 1
            if p.target_id:
                target_count[p.target_id] = target_count.get(p.target_id, 0) + 1
        hot_board = max(board_count.items(), key=lambda kv: kv[1])[0] if board_count else "none"
        top_target = max(target_count.items(), key=lambda kv: kv[1])[0] if target_count else "none"

        snapshot = BlockWindowSnapshot(
            step=int(round(now_time * 100.0)),
            mined_block_count=mined,
            window_block_ids=window,
            tree_lines=tree_lines,
            window_orphan_count=orphan_count,
            canonical_head_id=canonical_head,
            heaviest_head_id=heaviest_head,
            forum_window_posts=len(new_posts),
            forum_window_avg_tone=avg_tone,
            forum_hot_board=hot_board,
            forum_top_target=top_target,
            max_fork_degree=max_fork_degree,
            longest_branch_len=longest_branch_len,
            branch_count=branch_count,
            canonical_coverage=canonical_coverage,
        )
        self.snapshots.append(snapshot)
        if self.snapshot_callback is not None:
            self.snapshot_callback(snapshot, self._window_miner_wins(window))

    def _forum_state(self) -> Any:
        # Attempt to dynamically discover forum state from other modules
        # This preserves decoupling while still allowing rich cross-module metrics
        for mod in getattr(self.ctx, "modules", []):
            if hasattr(mod, "forum"):
                return mod.forum
        return None

    def _canonical_set(self, head: str) -> set[str]:
        out: set[str] = set()
        cur: Optional[str] = head
        while cur is not None and cur in self.ctx.blocks:
            out.add(cur)
            cur = self.ctx.blocks[cur].parent_id
        return out

    def _heaviest_head(self) -> str:
        best_id = "B0"
        best_h = -1
        for bid, block in self.ctx.blocks.items():
            if block.height > best_h:
                best_h = block.height
                best_id = bid
            elif block.height == best_h and block.created_at_step < self.ctx.blocks[best_id].created_at_step:
                best_id = bid
        return best_id

    def _count_orphans(self, canonical_head: str) -> int:
        canonical = set()
        cursor: Optional[str] = canonical_head
        while cursor is not None:
            canonical.add(cursor)
            cursor = self.ctx.blocks[cursor].parent_id if cursor in self.ctx.blocks else None
        return sum(1 for bid in self.ctx.blocks if bid not in canonical)

    def _build_window_tree_lines(self, window_ids: List[str]) -> List[str]:
        window = set(window_ids)
        children: Dict[str, List[str]] = {bid: [] for bid in window_ids}
        roots: List[str] = []

        for bid in window_ids:
            parent = self.ctx.blocks[bid].parent_id
            if parent in window:
                children[parent].append(bid)
            else:
                roots.append(bid)

        for key in children:
            children[key].sort(key=lambda x: self.ctx.chain_heights.get(x, 0))
        roots.sort(key=lambda x: self.ctx.chain_heights.get(x, 0))

        lines: List[str] = []
        for root in roots:
            self._append_tree(lines, children, root, depth=0)
        return lines

    def _append_tree(self, lines: List[str], children: Dict[str, List[str]], bid: str, depth: int) -> None:
        block = self.ctx.blocks[bid]
        prefix = "  " * depth + ("- " if depth else "")
        parent = block.parent_id or "None"
        lines.append(f"{prefix}{bid}(h={block.height},miner={block.miner_id},parent={parent},t={block.created_at_step})")
        for child in children.get(bid, []):
            self._append_tree(lines, children, child, depth + 1)

    def _window_miner_wins(self, window_block_ids: List[str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for bid in window_block_ids:
            block = self.ctx.blocks[bid]
            out[block.miner_id] = out.get(block.miner_id, 0) + 1
        return out

    def _window_tree_metrics(self, window_ids: List[str]) -> Tuple[int, int, int]:
        if not window_ids:
            return (0, 0, 0)
        window = set(window_ids)
        children: Dict[str, List[str]] = {bid: [] for bid in window_ids}
        roots: List[str] = []
        for bid in window_ids:
            parent = self.ctx.blocks[bid].parent_id
            if parent in window:
                children[parent].append(bid)
            else:
                roots.append(bid)

        max_fork_degree = 0
        for bid in window_ids:
            max_fork_degree = max(max_fork_degree, len(children[bid]))

        branch_count = 0
        longest_branch_len = 0

        def dfs(node_id: str, depth: int) -> None:
            nonlocal branch_count, longest_branch_len
            longest_branch_len = max(longest_branch_len, depth)
            nxt = children.get(node_id, [])
            if not nxt:
                branch_count += 1
                return
            for child in nxt:
                dfs(child, depth + 1)

        for root in roots:
            dfs(root, 1)
        if not roots:
            branch_count = 1
            longest_branch_len = len(window_ids)

        return (max_fork_degree, longest_branch_len, branch_count)

    def _compute_all_gamma(self) -> Dict[str, float]:
        miner_ids = [n.node_id for n in self.ctx.nodes.values() if n.is_miner]
        honest_ids = [m for m in miner_ids if self.ctx.nodes[m].strategy_name == "honest"]
        full_nodes = [n.node_id for n in self.ctx.nodes.values() if not n.is_miner]
        out: Dict[str, float] = {}

        for attacker in miner_ids:
            if self.ctx.nodes[attacker].strategy_name not in ("selfish", "social_selfish"):
                continue
            rival = self._strongest_honest(honest_ids)
            if not rival:
                out[attacker] = 0.0
                continue
            dist_att = self.ctx.graph.shortest_path_latencies(attacker)
            dist_rival = self.ctx.graph.shortest_path_latencies(rival)
            wins = 0
            total = 0
            for node_id in full_nodes:
                da = dist_att.get(node_id, float("inf"))
                dr = dist_rival.get(node_id, float("inf"))
                if da == float("inf") and dr == float("inf"):
                    continue
                total += 1
                if da <= dr:
                    wins += 1
            out[attacker] = (wins / total) if total else 0.0
        return out

    def _strongest_honest(self, honest_ids: List[str]) -> str:
        if not honest_ids:
            return ""
        return max(honest_ids, key=lambda mid: self.ctx.nodes[mid].hash_power)
