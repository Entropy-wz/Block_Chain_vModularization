from __future__ import annotations

import asyncio
import heapq
from dataclasses import dataclass
from pathlib import Path
from random import Random
import time
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.agent_profile import AgentProfileConfig, load_agent_profile_config
from ..core.config import AgenticSimulationConfig, LLMConfig
from ..core.entities import Block, Node
from ..core.graph_model import DirectedGraph, Edge
from ..core.storage import BlockStorage
from ..core.interfaces import EventTypes, ISimulationContext, ISimulationModule
from ..core.event_bus import SimpleEventBus
from ..core.persona import MinerPersona
from ..llm.agent import AgentObservation, MinerAgent
from ..llm.llm_backend import LLMDecision, build_llm_backend
from ..llm.router import DecisionRouter
from ..llm.scheduler import LLMScheduler, TaskPriority
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
    llm_scheduler_metrics: Dict[str, Any]
    economy_metrics: Dict[str, Any]
    config: AgenticSimulationConfig


@dataclass
class PendingDecision:
    request_id: int
    miner_id: str
    event_kind: str
    event_time: float
    trigger_block_id: str
    private_lead: int
    cache_key: Tuple[str, str, int, int]
    future: asyncio.Future
    source_block_id: str = ""


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
        # Hot/cold storage for blocks
        self.block_storage = BlockStorage(data_dir=None)
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
        self._llm_scheduler: Optional[LLMScheduler] = None
        self._decision_router: Optional[DecisionRouter] = None
        self._pending_decisions: Dict[int, PendingDecision] = {}
        self._pending_mine_context: Dict[int, Tuple[float, int, str, str]] = {}
        self._pending_receive_context: Dict[int, Tuple[float, str, str]] = {}
        self._next_request_id: int = 1
        self._decision_throughput_by_step: Dict[int, int] = {}
        
        self.genesis_id = "B0"
        genesis = Block(self.genesis_id, None, 0, "genesis", 0)
        self.block_storage.add_block(genesis)
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
        # For interfaces expecting dict: we return the hot blocks during simulation.
        # Reconstruct full set only for final report.
        return self.block_storage.hot_blocks

    @blocks.setter
    def blocks(self, value: Dict[str, Block]) -> None:
        pass # Disallowed, managed by block_storage

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
        selfish_flags = [
            self.agent_profile.is_selfish(mid, i, self.config.num_miners)
            for i, mid in enumerate(miner_ids)
        ]
        powers = self._sample_hash_powers(
            selfish_flags=selfish_flags,
            target_selfish_share=getattr(self.config, "selfish_hash_power_share", None),
        )
        llm = build_llm_backend(self.llm_config)

        for i, mid in enumerate(miner_ids):
            is_selfish = selfish_flags[i]
            strategy_name = "selfish" if is_selfish else "honest"
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
            allow_llm_override = os.getenv("SANDBOX_LLM_OFFLINE", "0").strip().lower() not in {"1", "true"}
                
            self.mining_strategies[mid] = build_mining_strategy(
                strategy_name,
                reputation_provider=get_rep,
                selfish_strategy_name=getattr(self.config, "selfish_strategy", "classic"),
                allow_llm_override=allow_llm_override,
                strategy_context_provider=lambda event_kind, private_lead, _mid=mid: self._build_strategy_context(
                    miner_id=_mid,
                    event_kind=event_kind,
                    private_lead=private_lead,
                ),
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

    def _sample_hash_powers(
        self,
        selfish_flags: List[bool],
        target_selfish_share: Optional[float],
    ) -> List[float]:
        raw = [self.rng.random() for _ in selfish_flags]
        total = sum(raw) or 1.0
        normalized = [r / total for r in raw]
        if target_selfish_share is None:
            return normalized
        return _rescale_hash_powers_by_group(
            normalized=normalized,
            selfish_flags=selfish_flags,
            target_selfish_share=target_selfish_share,
        )

    def _init_graph(self) -> DirectedGraph:
        from ..core.topology_generator import TopologyGenerator
        node_weights = {n.node_id: n.hash_power for n in self.nodes.values()}
        return TopologyGenerator.generate(
            topology_type=getattr(self.config, "topology_type", "random"),
            node_ids=list(self.nodes.keys()),
            rng=self.rng,
            edge_probability=self.config.edge_probability,
            min_latency=self.config.min_latency,
            max_latency=self.config.max_latency,
            min_reliability=self.config.min_reliability,
            max_reliability=self.config.max_reliability,
            ba_m=getattr(self.config, "topology_ba_m", 3),
            ws_k=getattr(self.config, "topology_ws_k", 4),
            ws_beta=getattr(self.config, "topology_ws_beta", 0.1),
            core_ratio=getattr(self.config, "topology_core_ratio", 0.05),
            core_edge_prob=getattr(self.config, "topology_core_edge_prob", 0.8),
            node_weights=node_weights
        )

    def _bootstrap_genesis(self) -> None:
        for node in self.nodes.values():
            node.observe_block(self.genesis_id, 0, self.chain_heights)
            self.adopted_counts[self.genesis_id] += 1

    def run(self) -> AgenticSimulationResult:
        import asyncio
        return asyncio.run(self.run_async())

    async def run_async(self) -> AgenticSimulationResult:
        import asyncio
        self.event_bus.publish(EventTypes.SIMULATION_START, self)
        
        self._progress(
            f"[SIM] 初始化完成，开始离散事件模拟：time_horizon={self.config.total_steps}, "
            f"miners={self.config.num_miners}, full_nodes={self.config.num_full_nodes}"
        )
        self._schedule_next_mining(0.0)
        
        # Setup semaphore for max concurrent requests
        max_concurrent = getattr(self.llm_config, "max_concurrent_requests", 5)
        self.llm_semaphore = asyncio.Semaphore(max_concurrent)

        self._current_time = 0.0
        next_progress_mark = 0.0
        
        # Start Scheduler
        self._llm_scheduler = LLMScheduler(
            max_concurrent=getattr(self.llm_config, "max_concurrent_requests", 5),
            default_timeout=getattr(self.llm_config, "timeout_seconds", 30),
            max_attempts=3
        )
        await self._llm_scheduler.start()
        
        # Start Router
        self._decision_router = DecisionRouter(
            simulation=self,
            cooldown_steps=getattr(self.llm_config, "decision_cooldown_steps", 10)
        )

        while self._events:
            event_time = self._events[0][0]
            if event_time > float(self.config.total_steps):
                break
                
            self._current_time = event_time
            self._current_step = self._event_step(event_time)

            if self._current_time >= next_progress_mark:
                self._progress(
                    f"[SIM] t={self._current_time:.2f}/{self.config.total_steps} | blocks={len(self.block_storage.get_all_summaries())-1} "
                    f"| queue={len(self._events)}"
                )
                next_progress_mark += float(self.progress_interval_steps)

            for module in self.modules:
                module.on_step_start(self)

            # Wait for all pending decisions to complete before processing new events
            # This implements the block sync semantic to keep DES valid
            await self._wait_for_pending_decisions()

            # Get all events that occur at exactly the same time step
            batch = []
            while self._events and abs(self._events[0][0] - event_time) < 1e-9:
                batch.append(heapq.heappop(self._events))
                
            for _, _, kind, a, b, hops in batch:
                if kind == "mine":
                    self._handle_mine_event(self._current_time)
                    self._schedule_next_mining(self._current_time)
                elif kind == "receive":
                    self._handle_receive_event(current_time=self._current_time, dst=a, block_id=b, hops=hops)

            # Finality-aware Prune
            prune_interval = getattr(self.config, "prune_interval_steps", 50)
            if self._current_step > 0 and self._current_step % prune_interval == 0:
                self._prune_blocks()

        # Wait for any lingering decisions before end
        await self._wait_for_pending_decisions()
        await self._llm_scheduler.stop()

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
        economy_metrics: Dict[str, Any] = {}
        for module in self.modules:
            getter = getattr(module, "get_summary_metrics", None)
            if callable(getter):
                try:
                    metrics = getter()
                    if isinstance(metrics, dict):
                        economy_metrics.update(metrics)
                except Exception:
                    pass
        
        self._progress(
            f"[SIM] 模拟结束：blocks={len(self.block_storage.get_all_summaries())-1}, orphans={orphan_blocks}, "
            f"jam_events={jam_count}, forum_posts={post_count}"
        )
        
        try:
            blocks_result = self.block_storage.reconstruct_all_blocks()
        finally:
            if hasattr(self.block_storage, 'cleanup'):
                self.block_storage.cleanup()

        return AgenticSimulationResult(
            blocks=blocks_result,
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
            llm_scheduler_metrics=self._llm_scheduler.get_metrics() if self._llm_scheduler else {},
            economy_metrics=economy_metrics,
            config=self.config,
        )

    def _build_strategy_context(self, miner_id: str, event_kind: str, private_lead: int) -> Dict[str, Any]:
        mined_blocks = max(0, len(self.block_storage.get_all_summaries()) - 1)
        epoch_blocks = max(1, int(getattr(self.config, "difficulty_epoch_blocks", 2016)))
        epoch_index = mined_blocks // epoch_blocks
        epoch_offset = mined_blocks % epoch_blocks
        progress = epoch_offset / float(epoch_blocks)
        if progress < 0.33:
            phase = "early"
        elif progress < 0.66:
            phase = "mid"
        else:
            phase = "late"
        difficulty_alpha = max(0.0, float(getattr(self.config, "difficulty_adjust_alpha", 0.25)))
        difficulty_level = max(0.1, 1.0 + epoch_index * difficulty_alpha)
        out: Dict[str, Any] = {
            "difficulty_epoch_index": int(epoch_index),
            "difficulty_epoch_progress": float(progress),
            "difficulty_phase": phase,
            "difficulty_level": float(difficulty_level),
            "intermittent_mode": str(getattr(self.config, "intermittent_mode", "post_adjust_burst")),
            "ds_enabled": bool(getattr(self.config, "ds_enabled", False)),
            "ds_target_confirmations": int(getattr(self.config, "ds_target_confirmations", 2)),
            "confirmations_seen": 0,
            "free_shot_eligible": False,
        }
        for module in self.modules:
            getter = getattr(module, "get_double_spend_context", None)
            if callable(getter):
                try:
                    extra = getter(miner_id)
                    if isinstance(extra, dict):
                        out.update(extra)
                except Exception:
                    pass
        return out

    def _on_agent_trace(self, payload: Dict[str, object]) -> None:
        self.prompt_traces.append(payload)

    def _event_step(self, current_time: float) -> int:
        return int(round(current_time * 100.0))

    async def _decide_for_event_async(
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

        import asyncio
        for attempt in range(1, max_attempts + 1):
            try:
                async with self.llm_semaphore:
                    decision = await agent.decide_async(obs)
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
                    await asyncio.sleep(wait_s)
                    continue

        # Try to use cache first before falling back to dumb algorithm
        if getattr(self.llm_config, "enable_cache", True) and cache_key in self._llm_decision_cache:
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
        if node.strategy_name == "honest" and not getattr(self.llm_config, "honest_use_llm", False):
            return LLMDecision(action="publish_if_win" if event_kind == "on_block_mined" else "rebroadcast", reason=reason)
        if event_kind == "on_block_mined":
            return LLMDecision(action="withhold_if_win", reason=reason)
        if private_lead > 0:
            return LLMDecision(action="publish_private", reason=reason, release_private_blocks=1)
        return LLMDecision(action="hold", reason=reason)

    def _normalize_decision(self, miner_id: str, decision: LLMDecision) -> LLMDecision:
        node = self.nodes.get(miner_id)
        if node is None:
            return decision
        
        # If honest nodes are not allowed to use LLM, forcefully restrict their actions
        if node.strategy_name == "honest" and not getattr(self.llm_config, "honest_use_llm", False):
            allowed_actions = {"publish_if_win", "rebroadcast", "hold"}
            action = decision.action if decision.action in allowed_actions else "publish_if_win"
            
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
            
        return decision
        
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
        self._dispatch_decision(
            miner_id=winner,
            event_time=current_time,
            event_kind="on_block_mined",
            trigger_block_id="",
            priority=TaskPriority.HIGH
        )

    def _handle_receive_event(self, current_time: float, dst: str, block_id: str, hops: int) -> None:
        node = self.nodes[dst]

        # Block may already be pruned from hot storage when propagation latency is high.
        # In that case, fall back to lightweight summary kept in memory.
        block = self.block_storage.get_block(block_id)
        if block is None:
            summary = self.block_storage.get_summary(block_id)
            if summary is None:
                # Unknown block id (or already fully unavailable) => skip safely.
                return
            block_height = summary.height
            block_parent_id = summary.parent_id
        else:
            block_height = block.height
            block_parent_id = block.parent_id

        old_head = node.local_head_id
        changed = node.observe_block(block_id, block_height, self.chain_heights)
        if changed:
            self.adopted_counts[block_id] += 1
            if old_head and old_head != block_parent_id:
                old_h = self.chain_heights.get(old_head, -1)
                if old_h == block_height:
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
        cooldown = getattr(self.llm_config, "decision_cooldown_steps", 10.0)
        time_since_last = current_time - self._last_llm_call_time.get(miner_id, -1000.0)
        
        is_significant = False
        priority = TaskPriority.LOW
        
        if private_lead > 0:
            is_significant = True
            priority = TaskPriority.MEDIUM
        elif time_since_last >= cooldown:
            is_significant = True
            priority = TaskPriority.LOW
        elif getattr(self.llm_config, "force_llm_on_fork", True):
            my_h = self.chain_heights.get(node.local_head_id or self.genesis_id, 0)
            public_h = self.chain_heights.get(self._canonical_head(), 0)
            if public_h >= my_h and block_id != self._canonical_head():
                 is_significant = True
                 priority = TaskPriority.HIGH
        
        if not is_significant:
            decision = self._fallback_decision(miner_id, "on_block_received", None, private_lead=private_lead)
            self._execute_receive_decision(miner_id, decision, current_time, block_id)
        else:
            self._last_llm_call_time[miner_id] = current_time
            self._dispatch_decision(
                miner_id=miner_id,
                event_time=current_time,
                event_kind="on_block_received",
                trigger_block_id=block_id,
                priority=priority
            )

    def _dispatch_decision(
        self,
        miner_id: str,
        event_time: float,
        event_kind: str,
        trigger_block_id: str,
        priority: int,
    ) -> None:
        public_h = self.chain_heights[self._canonical_head()]
        my_h = self.chain_heights.get(self.nodes[miner_id].local_head_id or self.genesis_id, 0)
        public_h_gap = max(0, public_h - my_h)
        private_lead = len(self.private_chains.get(miner_id, []))
        cache_key = (miner_id, event_kind, public_h_gap, private_lead)

        if getattr(self.llm_config, "enable_cache", True) and cache_key in self._llm_decision_cache:
            decision = self._llm_decision_cache[cache_key]
            if event_kind == "on_block_mined":
                self._execute_mine_decision(miner_id, decision, event_time)
            else:
                self._execute_receive_decision(miner_id, decision, event_time, trigger_block_id)
            return

        agent = self.agents[miner_id]
        mod_ctx: Dict[str, Any] = {}
        for module in self.modules:
            mod_ctx.update(module.augment_agent_observation(miner_id, self))

        obs = AgentObservation(
            step=self._event_step(event_time),
            miner_id=miner_id,
            is_selfish=agent.is_selfish,
            hash_power=agent.hash_power,
            local_public_height=public_h,
            private_lead=private_lead,
            rivalry_pressure=self._rivalry_pressure(miner_id, public_h),
            known_competitor_heads=self._miner_heads_except(miner_id),
            persona=self.personas[miner_id],
            modules_context=mod_ctx,
            event_kind=event_kind,
            trigger_block_id=trigger_block_id,
        )

        request_id = self._next_request_id
        self._next_request_id += 1

        if self._llm_scheduler is None:
            decision = self._fallback_decision(miner_id, event_kind, RuntimeError("scheduler-not-ready"), private_lead)
            if event_kind == "on_block_mined":
                self._execute_mine_decision(miner_id, decision, event_time)
            else:
                self._execute_receive_decision(miner_id, decision, event_time, trigger_block_id)
            return

        future = self._llm_scheduler.submit(
            agent=agent,
            obs=obs,
            priority=priority,
            timeout=float(getattr(self.llm_config, "timeout_seconds", 30)),
        )
        pending = PendingDecision(
            request_id=request_id,
            miner_id=miner_id,
            event_kind=event_kind,
            event_time=event_time,
            trigger_block_id=trigger_block_id,
            private_lead=private_lead,
            cache_key=cache_key,
            future=future,
            source_block_id=trigger_block_id,
        )
        self._pending_decisions[request_id] = pending
        if event_kind == "on_block_mined":
            self._pending_mine_context[request_id] = (event_time, self._event_step(event_time), miner_id, trigger_block_id)
        else:
            self._pending_receive_context[request_id] = (event_time, miner_id, trigger_block_id)

    async def _wait_for_pending_decisions(self) -> None:
        if not self._pending_decisions:
            return
        for request_id in sorted(list(self._pending_decisions.keys())):
            pending = self._pending_decisions.pop(request_id, None)
            if pending is None:
                continue

            decision: LLMDecision
            try:
                raw = await pending.future
                decision = self._normalize_decision(pending.miner_id, raw)
                self._patch_latest_trace(pending.miner_id, decision)
                self._llm_decision_cache[pending.cache_key] = decision
            except Exception as exc:
                if pending.cache_key in self._llm_decision_cache:
                    decision = self._llm_decision_cache[pending.cache_key]
                    self._progress(
                        f"[LLM-CACHE] Using cached decision for {pending.miner_id} {pending.event_kind} due to scheduler/API failure."
                    )
                else:
                    decision = self._fallback_decision(
                        miner_id=pending.miner_id,
                        event_kind=pending.event_kind,
                        error=exc,
                        private_lead=pending.private_lead,
                    )
                self.prompt_traces.append(
                    {
                        "step": self._event_step(pending.event_time),
                        "miner_id": pending.miner_id,
                        "system_prompt": "fallback-no-llm-response",
                        "user_prompt": f"event_kind={pending.event_kind};trigger_block_id={pending.trigger_block_id}",
                        "decision": {k: v for k, v in decision.__dict__.items()},
                        "effective_decision": {k: v for k, v in decision.__dict__.items()},
                        "fallback": True,
                        "fallback_error": str(exc),
                    }
                )

            self.event_bus.publish(EventTypes.AGENT_DECISION_MADE, {
                "miner_id": pending.miner_id,
                "decision": decision,
                "effective": decision,
            })

            if pending.event_kind == "on_block_mined":
                self._execute_mine_decision(pending.miner_id, decision, pending.event_time)
                self._pending_mine_context.pop(request_id, None)
            else:
                self._execute_receive_decision(pending.miner_id, decision, pending.event_time, pending.source_block_id)
                self._pending_receive_context.pop(request_id, None)

            step = self._event_step(pending.event_time)
            self._decision_throughput_by_step[step] = self._decision_throughput_by_step.get(step, 0) + 1

    def _execute_mine_decision(self, winner: str, decision: LLMDecision, current_time: float) -> None:
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
                "private_lead_after": len(self.private_chains[winner]),
            })
        else:
            self.nodes[winner].observe_block(block.block_id, block.height, self.chain_heights)
            self.adopted_counts[block.block_id] += 1
            self._propagate_from(winner, block.block_id, current_time, 0)

        if plan.rebroadcast_head:
            head = self.nodes[winner].local_head_id or self.genesis_id
            self._propagate_from(winner, head, current_time, 0)

    def _execute_receive_decision(self, miner_id: str, decision: LLMDecision, current_time: float, block_id: str) -> None:
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
        block_id = f"B{len(self.block_storage.get_all_summaries())}"
        block = Block(block_id, parent_id, parent_h + 1, miner_id, step)
        self.block_storage.add_block(block)
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
            block = self.block_storage.get_summary(bid)
            if block:
                self.nodes[miner_id].observe_block(bid, block.height, self.chain_heights)
                self.adopted_counts[bid] += 1
                self._propagate_from(miner_id, bid, now_time, 0)

    def _propagate_from(self, src: str, block_id: str, now_time: float, hops: int) -> None:
        if hops >= self.config.max_hops_for_propagation:
            return
            
        outgoing = self.graph.neighbors(src)
        # Batch scheduling for Hub nodes
        avg_degree = self.graph.edge_count() / max(1, len(self.nodes))
        is_hub = len(outgoing) > max(20, avg_degree * 3)
        
        for i, edge in enumerate(outgoing):
            offset = (i // 20) * 1e-5 if is_hub else 0.0
            self._maybe_schedule_delivery(edge, block_id, now_time + offset, hops + 1)

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
        for bid, block in self.block_storage.get_all_summaries().items():
            if block.height > best_h:
                best_h = block.height
                best_id = bid
            elif block.height == best_h:
                n_b = int(bid[1:]) if bid.startswith("B") and bid[1:].isdigit() else 0
                n_best = int(best_id[1:]) if best_id.startswith("B") and best_id[1:].isdigit() else 0
                if n_b < n_best:
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
            n_id = -int(block_id[1:]) if block_id.startswith("B") and block_id[1:].isdigit() else 0
            return (votes, height, n_id)

        return max(head_votes.keys(), key=rank_key)

    def _count_orphans(self, canonical_head: str) -> int:
        canonical = set()
        cursor: Optional[str] = canonical_head
        summaries = self.block_storage.get_all_summaries()
        while cursor is not None:
            canonical.add(cursor)
            cursor = summaries[cursor].parent_id if cursor in summaries else None
        return sum(1 for bid in summaries if bid not in canonical)

    def _prune_blocks(self) -> None:
        prune_depth = getattr(self.config, "prune_max_depth", 15)
        active_heads = set()
        active_heads.add(self._canonical_head())
        for node in self.nodes.values():
            if node.local_head_id:
                active_heads.add(node.local_head_id)
        # PROTECT PRIVATE CHAINS: Add the latest blocks of unpublished private chains
        for chain in self.private_chains.values():
            if chain:
                active_heads.add(chain[-1])
                
        pruned_count = self.block_storage.prune_frontier(active_heads, prune_depth)
        if pruned_count > 0:
            self._progress(f"[Prune] step={self._current_step} Moved {pruned_count} blocks to cold storage.")

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


def _rescale_hash_powers_by_group(
    normalized: List[float],
    selfish_flags: List[bool],
    target_selfish_share: float,
) -> List[float]:
    if len(normalized) != len(selfish_flags):
        raise ValueError("normalized and selfish_flags must have the same length")

    t = float(target_selfish_share)
    if not (0.0 <= t <= 1.0):
        raise ValueError("target_selfish_share must be between 0 and 1")

    selfish_idx = [i for i, is_selfish in enumerate(selfish_flags) if is_selfish]
    honest_idx = [i for i, is_selfish in enumerate(selfish_flags) if not is_selfish]
    if t > 0.0 and not selfish_idx:
        raise ValueError("target_selfish_share > 0 but no selfish miners are configured")
    if t < 1.0 and not honest_idx:
        raise ValueError("target_selfish_share < 1 but no honest miners are configured")

    selfish_sum = sum(normalized[i] for i in selfish_idx)
    honest_sum = sum(normalized[i] for i in honest_idx)

    # Degenerate safeguard: keep deterministic and valid even for pathological RNG outputs.
    if selfish_idx and selfish_sum <= 0:
        selfish_sum = float(len(selfish_idx))
        for i in selfish_idx:
            normalized[i] = 1.0
    if honest_idx and honest_sum <= 0:
        honest_sum = float(len(honest_idx))
        for i in honest_idx:
            normalized[i] = 1.0

    out = [0.0] * len(normalized)
    if selfish_idx:
        scale_selfish = t / selfish_sum if selfish_sum > 0 else 0.0
        for i in selfish_idx:
            out[i] = normalized[i] * scale_selfish
    if honest_idx:
        scale_honest = (1.0 - t) / honest_sum if honest_sum > 0 else 0.0
        for i in honest_idx:
            out[i] = normalized[i] * scale_honest

    total = sum(out)
    if total <= 0:
        # Fallback to equal split by role if everything collapses.
        if selfish_idx:
            each = t / len(selfish_idx)
            for i in selfish_idx:
                out[i] = each
        if honest_idx:
            each = (1.0 - t) / len(honest_idx)
            for i in honest_idx:
                out[i] = each
        total = sum(out)
    if total > 0 and abs(total - 1.0) > 1e-12:
        out = [v / total for v in out]
    return out
