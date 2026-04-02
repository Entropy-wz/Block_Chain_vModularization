from __future__ import annotations

import heapq
from dataclasses import dataclass
from pathlib import Path
from random import Random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.agent_profile import AgentProfileConfig, load_agent_profile_config
from ..core.config import AgenticSimulationConfig, LLMConfig
from ..core.entities import Block, Node
from ..core.graph_model import DirectedGraph, Edge
from ..core.interfaces import EventTypes, ISimulationContext, ISimulationModule
from ..core.event_bus import SimpleEventBus
from ..core.persona import MinerPersona
from ..llm.agent import AgentObservation, MinerAgent
from ..llm.llm_backend import LLMDecision, build_llm_backend
from ..social.forum import ForumPost, ForumState
from .mining_strategy import StrategyHookContext, build_mining_strategy
from ..modules.metrics_module import BlockWindowSnapshot


@dataclass
class AgenticSimulationResult:
    blocks: Dict[str, Block]
    nodes: Dict[str, Node]
    graph: DirectedGraph
    canonical_head_id: str
    heaviest_head_id: str
    orphan_blocks: int
    fork_events: int
    block_wins_by_miner: Dict[str, int]
    gamma_estimates: Dict[str, float]
    network_efficiency: float
    jam_events: int
    snapshots: List[BlockWindowSnapshot]
    forum_post_count: int
    forum_board_heat: Dict[str, float]
    final_reputation: Dict[str, float]
    forum_posts: List[ForumPost]
    prompt_traces: List[Dict[str, object]]
    mined_block_ids: List[str]
    private_chain_events: List[Dict[str, Any]]
    private_chain_lengths: Dict[str, int]
    config: AgenticSimulationConfig


class AgenticBlockchainSimulation(ISimulationContext):
    def __init__(
        self,
        config: AgenticSimulationConfig,
        llm_config: Optional[LLMConfig] = None,
        agent_profile_path: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
        snapshot_callback: Optional[Callable[[BlockWindowSnapshot, Dict[str, int]], None]] = None,
        progress_interval_steps: int = 10,
        verbose_llm_log: bool = False,
        modules: Optional[List[ISimulationModule]] = None,
    ) -> None:
        self.config = config
        self.llm_config = llm_config or LLMConfig()
        self.rng = Random(config.random_seed)
        self.progress_callback = progress_callback
        self.snapshot_callback = snapshot_callback
        self.progress_interval_steps = max(1, progress_interval_steps)
        self.verbose_llm_log = verbose_llm_log
        self.agent_profile_path = agent_profile_path or str(Path("configs") / "agent_profiles.toml")
        self.agent_profile: AgentProfileConfig = load_agent_profile_config(self.agent_profile_path)
        
        # Current Context State (ISimulationContext impls)
        self._current_time = 0.0
        self._current_step = 0

        self.nodes: Dict[str, Node] = {}
        self.blocks: Dict[str, Block] = {}
        self.chain_heights: Dict[str, int] = {}
        self.adopted_counts: Dict[str, int] = {}
        self.block_wins_by_miner: Dict[str, int] = {}
        self.private_chains: Dict[str, List[str]] = {}
        self.mining_strategies: Dict[str, object] = {}
        self.agents: Dict[str, MinerAgent] = {}
        self.personas: Dict[str, MinerPersona] = {}
        self.prompt_traces: List[Dict[str, object]] = []

        # Core Event Bus & Modules
        self.event_bus = SimpleEventBus()
        self.modules = modules or []

        # event tuple: (time, seq, kind, arg1, arg2, hops)
        self._events: List[Tuple[float, int, str, str, str, int]] = []
        self._seq = 0
        self.fork_events = 0
        self._scheduled_deliveries: set[Tuple[str, str]] = set()
        self._last_llm_call_time: Dict[str, float] = {}
        # Cache format: (miner_id, event_kind, public_h_gap, private_lead) -> LLMDecision
        self._llm_decision_cache: Dict[Tuple[str, str, int, int], LLMDecision] = {}
        self.private_chain_events: List[Dict[str, Any]] = []
        
        self.genesis_id = "B0"
        genesis = Block(self.genesis_id, None, 0, "genesis", 0)
        self.blocks[self.genesis_id] = genesis
        self.chain_heights[self.genesis_id] = 0
        self.adopted_counts[self.genesis_id] = 0

        self._init_nodes_and_agents()
        self.graph = self._init_graph()
        self._bootstrap_genesis()
        
        # Setup Modules
        for module in self.modules:
            module.setup(self, self.event_bus)
            
            # Pass module info into all agents
            for agent in self.agents.values():
                sys_prompt = module.augment_system_prompt(agent.miner_id, self)
                if sys_prompt:
                    agent.modules_system_prompts.append(sys_prompt)
                agent.modules_decision_keys.update(module.expected_decision_keys())

    # ISimulationContext Property Implementations
    @property
    def current_time(self) -> float:
        return self._current_time

    @property
    def current_step(self) -> int:
        return self._current_step

    @property
    def nodes(self) -> Dict[str, Node]:
        return self._nodes

    @nodes.setter
    def nodes(self, value: Dict[str, Node]) -> None:
        self._nodes = value

    @property
    def blocks(self) -> Dict[str, Block]:
        return self._blocks

    @blocks.setter
    def blocks(self, value: Dict[str, Block]) -> None:
        self._blocks = value

    @property
    def graph(self) -> DirectedGraph:
        return self._graph

    @graph.setter
    def graph(self, value: DirectedGraph) -> None:
        self._graph = value

    @property
    def chain_heights(self) -> Dict[str, int]:
        return self._chain_heights

    @chain_heights.setter
    def chain_heights(self, value: Dict[str, int]) -> None:
        self._chain_heights = value

    @property
    def private_chains(self) -> Dict[str, List[str]]:
        return self._private_chains

    @private_chains.setter
    def private_chains(self, value: Dict[str, List[str]]) -> None:
        self._private_chains = value

    def get_canonical_head(self) -> str:
        return self._canonical_head()

    def schedule_event(self, delay: float, kind: str, a: str, b: str, hops: int = 0) -> None:
        self._seq += 1
        heapq.heappush(self._events, (self._current_time + delay, self._seq, kind, a, b, hops))

    def _forum_state(self) -> Optional[ForumState]:
        for module in self.modules:
            if hasattr(module, "forum"):
                return module.forum
        return None

    def _jam_event_count(self) -> int:
        for module in self.modules:
            if hasattr(module, "jam_events"):
                return int(module.jam_events)
        return 0

    def _init_nodes_and_agents(self) -> None:
        miner_ids = [f"M{i}" for i in range(self.config.num_miners)]
        full_ids = [f"N{i}" for i in range(self.config.num_full_nodes)]
        raw = [self.rng.random() for _ in miner_ids]
        total = sum(raw) or 1.0
        powers = [r / total for r in raw]
        llm = build_llm_backend(self.llm_config)

        for i, mid in enumerate(miner_ids):
            is_selfish = self.agent_profile.is_selfish(mid, i, self.config.num_miners)
            strategy_name = "social_selfish" if is_selfish else "honest"
            self.personas[mid] = self.agent_profile.build_persona(mid, is_selfish, self.rng)
            self.nodes[mid] = Node(
                node_id=mid,
                is_miner=True,
                hash_power=powers[i],
                strategy_name=strategy_name,
                known_blocks={self.genesis_id},
                local_head_id=self.genesis_id,
            )
            self.block_wins_by_miner[mid] = 0
            self.private_chains[mid] = []
            
            # Reputation lookup is now soft decoupled - if forum module isn't loaded it defaults to 0.0
            def get_rep(m: str = mid) -> float:
                for mod in self.modules:
                    if hasattr(mod, "forum"):
                        return mod.forum.reputation_of(m)
                return 0.0
                
            self.mining_strategies[mid] = build_mining_strategy(
                strategy_name,
                reputation_provider=get_rep
            )
            self.agents[mid] = MinerAgent(
                miner_id=mid,
                is_selfish=is_selfish,
                hash_power=powers[i],
                llm=llm,
                trace_callback=self._on_agent_trace,
            )

        for nid in full_ids:
            self.nodes[nid] = Node(
                node_id=nid,
                is_miner=False,
                hash_power=0.0,
                strategy_name="honest",
                known_blocks={self.genesis_id},
                local_head_id=self.genesis_id,
            )

    def _init_graph(self) -> DirectedGraph:
        return DirectedGraph.random_graph(
            node_ids=list(self.nodes.keys()),
            edge_probability=self.config.edge_probability,
            min_latency=self.config.min_latency,
            max_latency=self.config.max_latency,
            min_reliability=self.config.min_reliability,
            max_reliability=self.config.max_reliability,
            rng=self.rng,
        )

    def _bootstrap_genesis(self) -> None:
        for node in self.nodes.values():
            node.observe_block(self.genesis_id, 0, self.chain_heights)
            self.adopted_counts[self.genesis_id] += 1

    def run(self) -> AgenticSimulationResult:
        self.event_bus.publish(EventTypes.SIMULATION_START, self)
        
        self._progress(
            f"[SIM] 初始化完成，开始离散事件模拟：time_horizon={self.config.total_steps}, "
            f"miners={self.config.num_miners}, full_nodes={self.config.num_full_nodes}"
        )
        self._schedule_next_mining(0.0)

        self._current_time = 0.0
        next_progress_mark = 0.0
        while self._events:
            event_time, _, kind, a, b, hops = heapq.heappop(self._events)
            if event_time > float(self.config.total_steps):
                break
            self._current_time = event_time
            self._current_step = self._event_step(event_time)

            if self._current_time >= next_progress_mark:
                self._progress(
                    f"[SIM] t={self._current_time:.2f}/{self.config.total_steps} | blocks={len(self.blocks)-1} "
                    f"| queue={len(self._events)}"
                )
                next_progress_mark += float(self.progress_interval_steps)

            for module in self.modules:
                module.on_step_start(self)

            if kind == "mine":
                self._handle_mine_event(self._current_time)
                self._schedule_next_mining(self._current_time)
            elif kind == "receive":
                self._handle_receive_event(current_time=self._current_time, dst=a, block_id=b, hops=hops)

        self.event_bus.publish(EventTypes.SIMULATION_END, self)

        # Retrieve metrics from modules
        metrics_mod = next((m for m in self.modules if hasattr(m, "gamma_estimates")), None)
        snapshots = metrics_mod.snapshots if metrics_mod else []
        mined_block_ids = metrics_mod.mined_block_ids if metrics_mod else []
        gamma_estimates = metrics_mod.gamma_estimates if metrics_mod else {}
        efficiency = metrics_mod.network_efficiency if metrics_mod else 0.0
        orphan_blocks = metrics_mod.orphan_blocks if metrics_mod else 0
        
        canonical_head = self._canonical_head()
        heaviest_head = self._heaviest_head()
        
        jam_count = self._jam_event_count()
        forum = self._forum_state()
        post_count = len(forum.posts) if forum else 0
        
        self._progress(
            f"[SIM] 模拟结束：blocks={len(self.blocks)-1}, orphans={orphan_blocks}, "
            f"jam_events={jam_count}, forum_posts={post_count}"
        )
        
        return AgenticSimulationResult(
            blocks=self.blocks,
            nodes=self.nodes,
            graph=self.graph,
            canonical_head_id=canonical_head,
            heaviest_head_id=heaviest_head,
            orphan_blocks=orphan_blocks,
            fork_events=self.fork_events,
            block_wins_by_miner=self.block_wins_by_miner,
            gamma_estimates=gamma_estimates,
            network_efficiency=efficiency,
            jam_events=jam_count,
            snapshots=snapshots,
            forum_post_count=post_count,
            forum_board_heat=dict(forum.board_heat) if forum else {},
            final_reputation=dict(forum.reputation) if forum else {},
            forum_posts=list(forum.posts) if forum else [],
            prompt_traces=list(self.prompt_traces),
            mined_block_ids=mined_block_ids,
            private_chain_events=list(self.private_chain_events),
            private_chain_lengths={mid: len(chain) for mid, chain in self.private_chains.items()},
            config=self.config,
        )

    def _on_agent_trace(self, payload: Dict[str, object]) -> None:
        self.prompt_traces.append(payload)

    def _event_step(self, current_time: float) -> int:
        return int(round(current_time * 100.0))

    def _decide_for_event(
        self,
        miner_id: str,
        current_time: float,
        event_kind: str,
        trigger_block_id: str = "",
    ) -> LLMDecision:
        agent = self.agents[miner_id]
        public_h = self.chain_heights[self._canonical_head()]
        
        # Build Context for Modules
        mod_ctx = {}
        for module in self.modules:
            mod_ctx.update(module.augment_agent_observation(miner_id, self))
            
        obs = AgentObservation(
            step=self._event_step(current_time),
            miner_id=miner_id,
            is_selfish=agent.is_selfish,
            hash_power=agent.hash_power,
            local_public_height=public_h,
            private_lead=len(self.private_chains[miner_id]),
            rivalry_pressure=self._rivalry_pressure(miner_id, public_h),
            known_competitor_heads=self._miner_heads_except(miner_id),
            persona=self.personas[miner_id],
            modules_context=mod_ctx,
            event_kind=event_kind,
            trigger_block_id=trigger_block_id,
        )
        if self.verbose_llm_log:
            self._progress(f"[LLM] t={current_time:.2f} miner={miner_id} event={event_kind}")
        last_exc: Optional[Exception] = None
        max_attempts = 3
        
        my_h = self.chain_heights.get(self.nodes[miner_id].local_head_id or self.genesis_id, 0)
        public_h_gap = max(0, public_h - my_h)
        private_lead = len(self.private_chains.get(miner_id, []))
        cache_key = (miner_id, event_kind, public_h_gap, private_lead)

        for attempt in range(1, max_attempts + 1):
            try:
                decision = agent.decide(obs)
                effective = self._normalize_decision(miner_id, decision)
                self._patch_latest_trace(miner_id, effective)
                
                # Broadcast decision explicitly to bus so modules can act
                self.event_bus.publish(EventTypes.AGENT_DECISION_MADE, {
                    "miner_id": miner_id,
                    "decision": decision,
                    "effective": effective
                })
                
                # Save to cache on success
                self._llm_decision_cache[cache_key] = effective
                return effective
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts:
                    wait_s = 0.8 * attempt
                    self._progress(
                        f"[LLM-WARN] t={current_time:.2f} miner={miner_id} event={event_kind} "
                        f"attempt={attempt}/{max_attempts} failed: {exc}; retry in {wait_s:.1f}s"
                    )
                    time.sleep(wait_s)
                    continue

        # Try to use cache first before falling back to dumb algorithm
        if cache_key in self._llm_decision_cache:
            fb = self._llm_decision_cache[cache_key]
            self._progress(f"[LLM-CACHE] Using cached decision for {miner_id} {event_kind} due to API failure.")
        else:
            fb = self._fallback_decision(miner_id=miner_id, event_kind=event_kind, error=last_exc, private_lead=private_lead)
        self.prompt_traces.append(
            {
                "step": self._event_step(current_time),
                "miner_id": miner_id,
                "system_prompt": "fallback-no-llm-response",
                "user_prompt": f"event_kind={event_kind};trigger_block_id={trigger_block_id}",
                "decision": {
                    "action": fb.action,
                    "reason": fb.reason,
                    "target_miner": fb.target_miner,
                    "release_private_blocks": fb.release_private_blocks,
                    "jam_steps": fb.jam_steps,
                    "social_action": fb.social_action,
                    "social_target": fb.social_target,
                    "social_board": fb.social_board,
                    "social_tone": fb.social_tone,
                    "social_content": fb.social_content,
                },
                "effective_decision": {
                    "action": fb.action,
                    "reason": fb.reason,
                    "target_miner": fb.target_miner,
                    "release_private_blocks": fb.release_private_blocks,
                    "jam_steps": fb.jam_steps,
                    "social_action": fb.social_action,
                    "social_target": fb.social_target,
                    "social_board": fb.social_board,
                    "social_tone": fb.social_tone,
                    "social_content": fb.social_content,
                },
                "fallback": True,
                "fallback_error": str(last_exc) if last_exc is not None else "",
            }
        )
        self._patch_latest_trace(miner_id, fb)
        self.event_bus.publish(EventTypes.AGENT_DECISION_MADE, {
            "miner_id": miner_id,
            "decision": fb,
            "effective": fb,
        })
        return fb

    def _fallback_decision(self, miner_id: str, event_kind: str, error: Optional[Exception], private_lead: int = 0) -> LLMDecision:
        node = self.nodes.get(miner_id)
        if node is None:
            return LLMDecision(action="hold", reason="fallback: missing node")
        reason = f"fallback[{type(error).__name__ if error else 'cooldown'}]"
        if node.strategy_name == "honest":
            return LLMDecision(action="publish_if_win" if event_kind == "on_block_mined" else "rebroadcast", reason=reason)
        if event_kind == "on_block_mined":
            return LLMDecision(action="withhold_if_win", reason=reason)
        if private_lead > 0:
            return LLMDecision(action="publish_private", reason=reason, release_private_blocks=1)
        return LLMDecision(action="hold", reason=reason)

    def _normalize_decision(self, miner_id: str, decision: LLMDecision) -> LLMDecision:
        node = self.nodes.get(miner_id)
        if node is None or node.strategy_name != "honest":
            return decision
        allowed_actions = {"publish_if_win", "rebroadcast", "hold"}
        action = decision.action if decision.action in allowed_actions else "publish_if_win"
        
        # We preserve any extra attributes attached by LLM that modules might need
        norm = LLMDecision(
            action=action,
            reason=decision.reason,
            target_miner="",
            release_private_blocks=0,
        )
        for k, v in decision.__dict__.items():
            if k not in ["action", "reason", "target_miner", "release_private_blocks"]:
                setattr(norm, k, v)
        return norm

    def _patch_latest_trace(self, miner_id: str, effective: LLMDecision) -> None:
        for i in range(len(self.prompt_traces) - 1, -1, -1):
            item = self.prompt_traces[i]
            if str(item.get("miner_id", "")) != miner_id:
                continue
            item["effective_decision"] = {k: v for k, v in effective.__dict__.items()}
            
            # Make sure we also update the raw decision so it prints correctly in the output metrics
            if isinstance(item.get("decision"), dict):
                for key in ["jam_steps", "social_action", "social_target", "social_board", "social_tone", "social_content"]:
                    if hasattr(effective, key) and key not in item["decision"]:
                        item["decision"][key] = getattr(effective, key)
            return

    def _schedule_next_mining(self, now_time: float) -> None:
        lam = max(1e-9, float(self.config.block_discovery_chance))
        delta = self.rng.expovariate(lam)
        self._seq += 1
        heapq.heappush(self._events, (now_time + delta, self._seq, "mine", "", "", 0))

    def _handle_mine_event(self, current_time: float) -> None:
        winner = self._sample_winner_by_hash_power()
        decision = self._decide_for_event(winner, current_time, "on_block_mined", "")
        # Modules now handle aux actions automatically via EventBus

        parent_id = self._winner_parent_id(winner)
        block = self._create_block(self._event_step(current_time), winner, parent_id)
        self.block_wins_by_miner[winner] += 1
        self.event_bus.publish(EventTypes.BLOCK_MINED, {"miner_id": winner, "block": block})

        strategy = self.mining_strategies[winner]
        plan = strategy.on_block_mined(
            StrategyHookContext(
                miner_id=winner,
                private_lead=len(self.private_chains[winner]),
                decision=decision,
            )
        )
        if plan.publish_private_blocks > 0:
            self._publish_private_chain(winner, current_time, plan.publish_private_blocks)

        if not plan.publish_new_block:
            self.private_chains[winner].append(block.block_id)
            self.private_chain_events.append({
                "step": self._event_step(current_time),
                "time": current_time,
                "miner_id": winner,
                "event_type": "withhold_mined",
                "block_id": block.block_id,
                "private_lead_after": len(self.private_chains[winner])
            })
        else:
            self.nodes[winner].observe_block(block.block_id, block.height, self.chain_heights)
            self.adopted_counts[block.block_id] += 1
            self._propagate_from(winner, block.block_id, current_time, 0)

        if plan.rebroadcast_head:
            head = self.nodes[winner].local_head_id or self.genesis_id
            self._propagate_from(winner, head, current_time, 0)

    def _handle_receive_event(self, current_time: float, dst: str, block_id: str, hops: int) -> None:
        node = self.nodes[dst]
        block = self.blocks[block_id]
        old_head = node.local_head_id
        changed = node.observe_block(block_id, block.height, self.chain_heights)
        if changed:
            self.adopted_counts[block_id] += 1
            if old_head and old_head != block.parent_id:
                old_h = self.chain_heights.get(old_head, -1)
                if old_h == block.height:
                    self.fork_events += 1
            self._propagate_from(dst, block_id, current_time, hops)

        self.event_bus.publish(EventTypes.BLOCK_RECEIVED, {
            "node_id": dst,
            "block_id": block_id,
            "hops": hops,
            "changed_head": changed
        })

        if not changed or not node.is_miner:
            return
        miner_id = dst
        
        private_lead = len(self.private_chains[miner_id])
        time_since_last = current_time - self._last_llm_call_time.get(miner_id, -1000.0)
        cooldown = 10.0
        
        is_significant = (private_lead > 0) or (time_since_last >= cooldown)
        
        if not is_significant:
            decision = self._fallback_decision(miner_id, "on_block_received", None, private_lead=private_lead)
            self.event_bus.publish(EventTypes.AGENT_DECISION_MADE, {
                "miner_id": miner_id,
                "decision": decision,
                "effective": decision,
            })
        else:
            self._last_llm_call_time[miner_id] = current_time
            decision = self._decide_for_event(miner_id, current_time, "on_block_received", block_id)

        # Modules handle aux actions automatically via EventBus
        strategy = self.mining_strategies[miner_id]
        plan = strategy.on_block_received(
            StrategyHookContext(
                miner_id=miner_id,
                private_lead=len(self.private_chains[miner_id]),
                decision=decision,
                received_block_id=block_id,
            )
        )
        if plan.publish_private_blocks > 0:
            self._publish_private_chain(miner_id, current_time, plan.publish_private_blocks)
        elif not plan.publish_new_block and block_id not in self.private_chains[miner_id]:
            # This handles if a strategy tells us to withhold a received block (less common but possible)
            pass
        if plan.rebroadcast_head:
            head = self.nodes[miner_id].local_head_id or self.genesis_id
            self._propagate_from(miner_id, head, current_time, 0)

    def _sample_winner_by_hash_power(self) -> str:
        miners = [n for n in self.nodes.values() if n.is_miner]
        total = sum(m.hash_power for m in miners) or 1.0
        x = self.rng.random()
        c = 0.0
        for miner in miners:
            c += miner.hash_power / total
            if x <= c:
                return miner.node_id
        return miners[-1].node_id

    def _winner_parent_id(self, winner: str) -> str:
        private = self.private_chains[winner]
        if private:
            return private[-1]
        return self.nodes[winner].local_head_id or self.genesis_id

    def _create_block(self, step: int, miner_id: str, parent_id: str) -> Block:
        parent_h = self.chain_heights[parent_id]
        block_id = f"B{len(self.blocks)}"
        block = Block(block_id, parent_id, parent_h + 1, miner_id, step)
        self.blocks[block_id] = block
        self.chain_heights[block_id] = block.height
        self.adopted_counts[block_id] = 0
        return block

    def _publish_private_chain(self, miner_id: str, now_time: float, release_count: int) -> None:
        private = self.private_chains[miner_id]
        if not private:
            return
        k = len(private) if release_count <= 0 else min(release_count, len(private))
        to_release = private[:k]
        self.private_chains[miner_id] = private[k:]
        self.private_chain_events.append({
            "step": self._event_step(now_time),
            "time": now_time,
            "miner_id": miner_id,
            "event_type": "release_private",
            "released_blocks": to_release,
            "private_lead_after": len(self.private_chains[miner_id])
        })
        self.event_bus.publish(EventTypes.PRIVATE_CHAIN_PUBLISHED, {"miner_id": miner_id, "blocks": list(to_release)})
        for bid in to_release:
            block = self.blocks[bid]
            self.nodes[miner_id].observe_block(bid, block.height, self.chain_heights)
            self.adopted_counts[bid] += 1
            self._propagate_from(miner_id, bid, now_time, 0)

    def _propagate_from(self, src: str, block_id: str, now_time: float, hops: int) -> None:
        if hops >= self.config.max_hops_for_propagation:
            return
        for edge in self.graph.neighbors(src):
            self._maybe_schedule_delivery(edge, block_id, now_time, hops + 1)

    def _maybe_schedule_delivery(self, edge: Edge, block_id: str, now_time: float, hops: int) -> None:
        if block_id in self.nodes[edge.dst].known_blocks:
            return
        if (edge.dst, block_id) in self._scheduled_deliveries:
            return
        if self.rng.random() > edge.reliability:
            return
        self._scheduled_deliveries.add((edge.dst, block_id))
        self._seq += 1
        arrival = now_time + edge.latency
        heapq.heappush(self._events, (arrival, self._seq, "receive", edge.dst, block_id, hops))

    def _heaviest_head(self) -> str:
        best_id = self.genesis_id
        best_h = -1
        for bid, block in self.blocks.items():
            if block.height > best_h:
                best_h = block.height
                best_id = bid
            elif block.height == best_h and block.created_at_step < self.blocks[best_id].created_at_step:
                best_id = bid
        return best_id

    def _canonical_head(self) -> str:
        head_votes: Dict[str, int] = {}
        for node in self.nodes.values():
            hid = node.local_head_id or self.genesis_id
            head_votes[hid] = head_votes.get(hid, 0) + 1
        if not head_votes:
            return self.genesis_id

        def rank_key(block_id: str) -> Tuple[int, int, int]:
            votes = head_votes.get(block_id, 0)
            height = self.chain_heights.get(block_id, -1)
            created = self.blocks[block_id].created_at_step if block_id in self.blocks else -1
            return (votes, height, created)

        return max(head_votes.keys(), key=rank_key)

    def _count_orphans(self, canonical_head: str) -> int:
        canonical = set()
        cursor: Optional[str] = canonical_head
        while cursor is not None:
            canonical.add(cursor)
            cursor = self.blocks[cursor].parent_id if cursor in self.blocks else None
        return sum(1 for bid in self.blocks if bid not in canonical)

    def _rivalry_pressure(self, miner_id: str, public_h: int) -> float:
        my_h = self.chain_heights.get(self.nodes[miner_id].local_head_id or self.genesis_id, 0)
        gap = max(0, public_h - my_h)
        return min(1.0, gap / 6.0)

    def _miner_heads_except(self, miner_id: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for n in self.nodes.values():
            if not n.is_miner or n.node_id == miner_id:
                continue
            head = n.local_head_id or self.genesis_id
            out[n.node_id] = self.chain_heights.get(head, 0)
        return out

    def _progress(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)
