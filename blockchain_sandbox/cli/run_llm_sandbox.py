import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from blockchain_sandbox.cli.provider_config import load_llm_config_from_yaml
from blockchain_sandbox.core.config import AgenticSimulationConfig
from blockchain_sandbox.engine.agentic_simulation import AgenticBlockchainSimulation
from blockchain_sandbox.modules.metrics_module import BlockWindowSnapshot
from blockchain_sandbox.modules.forum_module import ForumModule
from blockchain_sandbox.modules.network_attack_module import NetworkAttackModule
from blockchain_sandbox.modules.governance_module import GovernanceModule
from blockchain_sandbox.modules.metrics_module import MetricsObserverModule
from blockchain_sandbox.modules.tokenomics_module import TokenomicsModule
from blockchain_sandbox.llm.llm_backend import build_llm_backend
from blockchain_sandbox.reporting.agentic_metrics import (
    build_agentic_report,
    format_agentic_report,
    format_forum_panel,
    format_miner_details,
    format_snapshots,
)
from blockchain_sandbox.reporting.persistence import export_run_artifacts


def resolve_economy_enabled(selfish_strategy_name: str, economy_env_value: str) -> bool:
    ds_strategy_active = (selfish_strategy_name or "").strip().lower() in {"stubborn_ds"}
    economy_enabled = (economy_env_value or "0").strip().lower() in {"1", "true"}
    if ds_strategy_active:
        return True
    return economy_enabled


def main() -> None:
    run_started = time.time()

    def ts() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def line(ch: str = "=", n: int = 76) -> None:
        print(ch * n, flush=True)

    def log(stage: str, msg: str) -> None:
        print(f"[{ts()}] [{stage}] {msg}", flush=True)

    def panel(title: str) -> None:
        line("=")
        print(f"{title}", flush=True)
        line("=")

    def kv_table(rows: List[Tuple[str, str]], width: int = 76) -> None:
        key_w = 24
        for k, v in rows:
            print(f"{k:<{key_w}} : {v}", flush=True)
        line("-", width)

    def bar(label: str, value: int, max_value: int, width: int = 28) -> str:
        if max_value <= 0:
            fill = 0
        else:
            fill = int(round(width * (value / max_value)))
        fill = max(0, min(width, fill))
        return f"{label:<8} [{'#' * fill}{'.' * (width - fill)}] {value}"

    def on_progress(message: str) -> None:
        log("PROGRESS", message)

    def on_window_summary(snapshot: BlockWindowSnapshot, miner_wins: Dict[str, int]) -> None:
        panel(f"WINDOW #{snapshot.mined_block_count // max(1, len(snapshot.window_block_ids))} | step={snapshot.step}")
        kv_table(
            [
                ("Canonical Head", snapshot.canonical_head_id),
                ("Window Blocks", str(len(snapshot.window_block_ids))),
                ("Window Orphans", f"{snapshot.window_orphan_count}/{len(snapshot.window_block_ids)}"),
                ("Canonical Coverage", f"{snapshot.canonical_coverage:.1%}"),
                ("Longest Branch Len", str(snapshot.longest_branch_len)),
                ("Branch Count", str(snapshot.branch_count)),
                ("Max Fork Degree", str(snapshot.max_fork_degree)),
                ("Forum Posts", str(snapshot.forum_window_posts)),
                ("Forum Avg Tone", f"{snapshot.forum_window_avg_tone:+.2f}"),
                ("Forum Hot Board", snapshot.forum_hot_board),
                ("Forum Top Target", snapshot.forum_top_target),
            ]
        )
        if miner_wins:
            ranking = sorted(miner_wins.items(), key=lambda kv: kv[1], reverse=True)
            max_cnt = ranking[0][1]
            print("Miner Win Ranking", flush=True)
            for mid, cnt in ranking[:8]:
                print("  " + bar(mid, cnt, max_cnt), flush=True)
            line("-", 76)
        print("Block Tree", flush=True)
        for tree_line in snapshot.tree_lines:
            print(f"  {tree_line}", flush=True)
        line("-")

    panel("Blockchain Sandbox Console")
    log("BOOT", "system modules loading")

    cfg_path = os.getenv("SANDBOX_LLM_CONFIG_FILE", str(Path("configs") / "llm_provider.yaml"))
    agent_profile_path = os.getenv("SANDBOX_AGENT_PROFILE_FILE", str(Path("configs") / "agent_profiles.toml"))
    log("CONFIG", f"loading LLM config file: {cfg_path}")
    llm_cfg = load_llm_config_from_yaml(cfg_path)
    masked_key = (llm_cfg.api_key[:6] + "***") if llm_cfg.api_key else "(empty)"
    log(
        "CONFIG",
        f"LLM ready | model={llm_cfg.model} | base_url={llm_cfg.base_url} | "
        f"use_chat={llm_cfg.use_chat_completions} | key={masked_key}",
    )
    llm_max_workers = os.getenv("SANDBOX_LLM_MAX_WORKERS")
    if llm_max_workers:
        import dataclasses
        llm_cfg = dataclasses.replace(llm_cfg, max_concurrent_requests=int(llm_max_workers))

    log("CONFIG", f"loading agent profile file: {agent_profile_path}")

    do_preflight = os.getenv("SANDBOX_PREFLIGHT_LLM", "1").strip().lower() in {"1", "true"}
    preflight_strict = os.getenv("SANDBOX_PREFLIGHT_STRICT", "1").strip().lower() in {"1", "true"}
    if do_preflight:
        log("CHECK", "LLM connectivity preflight...")
        try:
            probe = build_llm_backend(llm_cfg)
            _ = probe.decide(
                "Return JSON with keys action and reason.",
                "step=0;miner_id=probe;is_selfish=false;action_probe=true",
            )
            log("CHECK", "preflight passed")
        except Exception as exc:
            log("CHECK", f"preflight failed: {exc}")
            if preflight_strict:
                raise
            log("CHECK", "continue with preflight failure ignored")

    selfish_strategy_name = os.getenv("SANDBOX_SELFISH_STRATEGY", "classic").strip().lower()
    ds_strategy_active = selfish_strategy_name in {"stubborn_ds"}
    economy_enabled_env = os.getenv("SANDBOX_ECONOMY_ENABLED", os.getenv("SANDBOX_ENABLE_TOKENOMICS", "0"))
    economy_enabled = resolve_economy_enabled(selfish_strategy_name, economy_enabled_env)
    if ds_strategy_active and economy_enabled_env.strip().lower() not in {"1", "true"}:
        log("CONFIG", "double-spend strategy detected, forcing economy system enabled")

    ds_target_confirmations = int(os.getenv("SANDBOX_DS_TARGET_CONFIRMATIONS", "2"))
    ds_payment_amount = float(os.getenv("SANDBOX_DS_PAYMENT_AMOUNT", "3.0"))
    ds_attack_interval_blocks = int(os.getenv("SANDBOX_DS_ATTACK_INTERVAL_BLOCKS", "30"))
    if ds_strategy_active:
        if ds_target_confirmations <= 0:
            raise ValueError("SANDBOX_DS_TARGET_CONFIRMATIONS must be > 0 for double-spend strategy")
        if ds_payment_amount <= 0:
            raise ValueError("SANDBOX_DS_PAYMENT_AMOUNT must be > 0 for double-spend strategy")
        if ds_attack_interval_blocks <= 0:
            raise ValueError("SANDBOX_DS_ATTACK_INTERVAL_BLOCKS must be > 0 for double-spend strategy")

    selfish_hash_power_share_env = os.getenv("SANDBOX_SELFISH_HASH_POWER_SHARE", "").strip()
    selfish_hash_power_share = None
    if selfish_hash_power_share_env:
        selfish_hash_power_share = float(selfish_hash_power_share_env)
        if not (0.0 <= selfish_hash_power_share <= 1.0):
            raise ValueError("SANDBOX_SELFISH_HASH_POWER_SHARE must be between 0 and 1")

    sim_cfg = AgenticSimulationConfig(
        total_steps=int(os.getenv("SANDBOX_TOTAL_STEPS", "320")),
        random_seed=int(os.getenv("SANDBOX_RANDOM_SEED", "11")),
        num_miners=int(os.getenv("SANDBOX_NUM_MINERS", "12")),
        num_full_nodes=int(os.getenv("SANDBOX_NUM_FULL_NODES", "24")),
        selfish_hash_power_share=selfish_hash_power_share,
        edge_probability=float(os.getenv("SANDBOX_EDGE_PROB", "0.24")),
        topology_type=os.getenv("SANDBOX_TOPOLOGY_TYPE", "random"),
        topology_ba_m=int(os.getenv("SANDBOX_TOPOLOGY_BA_M", "3")),
        topology_ws_k=int(os.getenv("SANDBOX_TOPOLOGY_WS_K", "4")),
        topology_ws_beta=float(os.getenv("SANDBOX_TOPOLOGY_WS_BETA", "0.1")),
        topology_core_ratio=float(os.getenv("SANDBOX_TOPOLOGY_CORE_RATIO", "0.05")),
        topology_core_edge_prob=float(os.getenv("SANDBOX_TOPOLOGY_CORE_EDGE_PROB", "0.8")),
        min_latency=float(os.getenv("SANDBOX_MIN_LATENCY", "1.0")),
        max_latency=float(os.getenv("SANDBOX_MAX_LATENCY", "5.0")),
        min_reliability=float(os.getenv("SANDBOX_MIN_RELIABILITY", "0.9")),
        max_reliability=float(os.getenv("SANDBOX_MAX_RELIABILITY", "1.0")),
        block_discovery_chance=float(os.getenv("SANDBOX_BLOCK_DISCOVERY_CHANCE", "0.02")),
        max_hops_for_propagation=int(os.getenv("SANDBOX_MAX_HOPS", "5")),
        snapshot_interval_blocks=int(os.getenv("SANDBOX_SNAPSHOT_INTERVAL_BLOCKS", "10")),
        enable_forum=os.getenv("SANDBOX_ENABLE_FORUM", "1").strip().lower() in {"1", "true"},
        enable_attack_jamming=os.getenv("SANDBOX_ENABLE_ATTACK_JAMMING", "1").strip().lower() in {"1", "true"},
        selfish_strategy=selfish_strategy_name,
        llm_decision_mode=os.getenv("SANDBOX_LLM_DECISION_MODE", "persona_first").strip().lower(),
        persona_deviation_level=os.getenv("SANDBOX_PERSONA_DEVIATION_LEVEL", "medium").strip().lower(),
        persona_action_set=os.getenv("SANDBOX_PERSONA_ACTION_SET", "extended").strip().lower(),
        strategy_constraint_strictness=os.getenv("SANDBOX_STRATEGY_CONSTRAINT_STRICTNESS", "safe").strip().lower(),
        economy_enabled=economy_enabled,
        ds_enabled=os.getenv("SANDBOX_DS_ENABLED", "0").strip().lower() in {"1", "true"} or ds_strategy_active,
        ds_target_confirmations=ds_target_confirmations,
        ds_free_shot_depth=int(os.getenv("SANDBOX_DS_FREE_SHOT_DEPTH", "1")),
        ds_payment_amount=ds_payment_amount,
        ds_attack_interval_blocks=ds_attack_interval_blocks,
        ds_merchant_id=os.getenv("SANDBOX_DS_MERCHANT_ID", "").strip(),
        difficulty_epoch_blocks=int(os.getenv("SANDBOX_DIFFICULTY_EPOCH_BLOCKS", "2016")),
        difficulty_adjust_alpha=float(os.getenv("SANDBOX_DIFFICULTY_ADJUST_ALPHA", "0.25")),
        intermittent_mode=os.getenv("SANDBOX_INTERMITTENT_MODE", "post_adjust_burst").strip().lower(),
        econ_initial_fiat=float(os.getenv("SANDBOX_ECON_INITIAL_FIAT", "1000")),
        econ_initial_tokens=float(os.getenv("SANDBOX_ECON_INITIAL_TOKENS", "20")),
        econ_base_token_price=float(os.getenv("SANDBOX_ECON_BASE_TOKEN_PRICE", "100")),
        econ_mining_cost_per_step=float(os.getenv("SANDBOX_ECON_MINING_COST_PER_STEP", "1.0")),
        econ_block_reward_tokens=float(os.getenv("SANDBOX_ECON_BLOCK_REWARD_TOKENS", "1.0")),
        econ_price_from_orphan=os.getenv("SANDBOX_ECON_PRICE_FROM_ORPHAN", "1").strip().lower() in {"1", "true"},
        econ_price_model=os.getenv("SANDBOX_ECON_PRICE_MODEL", "orphan_health").strip().lower(),
        econ_static_token_price=float(os.getenv("SANDBOX_ECON_STATIC_TOKEN_PRICE", "100")),
        econ_orphan_penalty_k=float(os.getenv("SANDBOX_ECON_ORPHAN_PENALTY_K", "2.0")),
        econ_price_floor_factor=float(os.getenv("SANDBOX_ECON_PRICE_FLOOR_FACTOR", "0.1")),
    )
    
    enable_tokenomics = sim_cfg.economy_enabled
    show_snapshots = os.getenv("SANDBOX_SHOW_SNAPSHOTS", "1").strip().lower() in {"1", "true"}
    progress_interval_steps = int(os.getenv("SANDBOX_PROGRESS_INTERVAL_STEPS", "20"))
    verbose_llm_log = os.getenv("SANDBOX_VERBOSE_LLM_LOG", "0").strip().lower() in {"1", "true"}
    live_window_summary = os.getenv("SANDBOX_LIVE_WINDOW_SUMMARY", "1").strip().lower() in {"1", "true"}
    save_artifacts = os.getenv("SANDBOX_SAVE_ARTIFACTS", "1").strip().lower() in {"1", "true"}
    export_prompts = os.getenv("SANDBOX_EXPORT_PROMPTS", "1").strip().lower() in {"1", "true"}
    output_root = os.getenv("SANDBOX_OUTPUT_ROOT", "outputs")

    panel("Simulation Overview")
    kv_table(
        [
            ("Started At", ts()),
            ("Time Horizon", str(sim_cfg.total_steps)),
            ("Miner Count", str(sim_cfg.num_miners)),
            ("Full Node Count", str(sim_cfg.num_full_nodes)),
            ("Forum Module", "Enabled" if sim_cfg.enable_forum else "Disabled"),
            ("Selfish Strategy", sim_cfg.selfish_strategy),
            ("LLM Decision Mode", sim_cfg.llm_decision_mode),
            ("Persona Deviation", sim_cfg.persona_deviation_level),
            ("Selfish HP Target", f"{sim_cfg.selfish_hash_power_share:.4f}" if sim_cfg.selfish_hash_power_share is not None else "random-normalized"),
            ("Tokenomics Module", "Enabled" if enable_tokenomics else "Disabled"),
            ("DS Mode", "Enabled" if sim_cfg.ds_enabled else "Disabled"),
            ("DS Confirm Target", str(sim_cfg.ds_target_confirmations)),
            ("Topology", f"{sim_cfg.topology_type} (BA m={sim_cfg.topology_ba_m})" if sim_cfg.topology_type == "barabasi_albert" else f"{sim_cfg.topology_type} (k={getattr(sim_cfg, 'topology_ws_k', 4)}, beta={getattr(sim_cfg, 'topology_ws_beta', 0.1)})" if sim_cfg.topology_type == "watts_strogatz" else f"{sim_cfg.topology_type} (core_ratio={getattr(sim_cfg, 'topology_core_ratio', 0.05)})" if sim_cfg.topology_type == "core_periphery" else f"random (p={sim_cfg.edge_probability:.3f})"),
            ("Latency Range", f"{sim_cfg.min_latency:.2f}~{sim_cfg.max_latency:.2f}"),
            ("Reliability", f"{sim_cfg.min_reliability:.2f}~{sim_cfg.max_reliability:.2f}"),
            ("Block Discovery P", f"{sim_cfg.block_discovery_chance:.3f}"),
            ("Snapshot Every", f"{sim_cfg.snapshot_interval_blocks} blocks"),
            ("Progress Interval", f"{progress_interval_steps} steps"),
        ]
    )
    log("BOOT", "building simulation engine")

    modules = []
    forum_mod = None
    
    # Optional forum instantiation
    if sim_cfg.enable_forum:
        forum_mod = ForumModule()
        modules.append(forum_mod)
        # Governance relies on reputation if enabled
        modules.append(GovernanceModule(
            ban_reputation_threshold=sim_cfg.ban_reputation_threshold,
            reputation_provider=forum_mod.forum.reputation_of
        ))
        
    # Attack module
    modules.append(NetworkAttackModule(
        max_steps_of_jam_effect=sim_cfg.max_steps_of_jam_effect,
        enable_jamming=sim_cfg.enable_attack_jamming
    ))
    
    # Tokenomics module
    if enable_tokenomics:
        modules.append(
            TokenomicsModule(
                initial_fiat_balance=sim_cfg.econ_initial_fiat,
                base_token_price=sim_cfg.econ_base_token_price,
                initial_token_balance=sim_cfg.econ_initial_tokens,
                mining_cost_per_step=sim_cfg.econ_mining_cost_per_step,
                block_reward_tokens=sim_cfg.econ_block_reward_tokens,
                price_from_orphan=sim_cfg.econ_price_from_orphan,
                price_model=sim_cfg.econ_price_model,
                static_token_price=sim_cfg.econ_static_token_price,
                orphan_penalty_k=sim_cfg.econ_orphan_penalty_k,
                price_floor_factor=sim_cfg.econ_price_floor_factor,
            )
        )
    
    # Metrics Module 
    metrics_mod = MetricsObserverModule(
        snapshot_interval_blocks=sim_cfg.snapshot_interval_blocks,
        snapshot_callback=on_window_summary if live_window_summary else None
    )
    modules.append(metrics_mod)

    sim = AgenticBlockchainSimulation(
        config=sim_cfg,
        llm_config=llm_cfg,
        agent_profile_path=agent_profile_path,
        progress_callback=on_progress,
        snapshot_callback=None, # Moved to Metrics Module
        progress_interval_steps=progress_interval_steps,
        verbose_llm_log=verbose_llm_log,
        modules=modules
    )

    log("RUN", "simulation started")
    result = sim.run()
    elapsed = time.time() - run_started
    log("RUN", f"simulation finished in {elapsed:.1f}s")

    panel("Final Report")
    report = build_agentic_report(result)
    print(format_agentic_report(report), flush=True)
    print("", flush=True)
    print(format_miner_details(report), flush=True)
    print("", flush=True)
    print(format_forum_panel(report), flush=True)
    if show_snapshots:
        print("", flush=True)
        print(format_snapshots(report), flush=True)
    if save_artifacts:
        out_dir = export_run_artifacts(
            result=result,
            report=report,
            output_root=output_root,
            export_prompts=export_prompts,
        )
        print("", flush=True)
        print(f"Artifacts saved to: {out_dir}", flush=True)
        png_files = sorted(Path(out_dir).glob("*.png"))
        if png_files:
            print("Generated tree PNG files:", flush=True)
            for p in png_files:
                print(f"  - {p}", flush=True)
    line("=")
    log("DONE", "Blockchain Sandbox run completed")


if __name__ == "__main__":
    main()
