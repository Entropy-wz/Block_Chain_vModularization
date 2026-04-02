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
from blockchain_sandbox.llm.llm_backend import build_llm_backend
from blockchain_sandbox.reporting.agentic_metrics import (
    build_agentic_report,
    format_agentic_report,
    format_forum_panel,
    format_miner_details,
    format_snapshots,
)
from blockchain_sandbox.reporting.persistence import export_run_artifacts


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

    sim_cfg = AgenticSimulationConfig(
        total_steps=int(os.getenv("SANDBOX_TOTAL_STEPS", "320")),
        random_seed=int(os.getenv("SANDBOX_RANDOM_SEED", "11")),
        num_miners=int(os.getenv("SANDBOX_NUM_MINERS", "12")),
        num_full_nodes=int(os.getenv("SANDBOX_NUM_FULL_NODES", "24")),
        edge_probability=float(os.getenv("SANDBOX_EDGE_PROB", "0.24")),
        min_latency=float(os.getenv("SANDBOX_MIN_LATENCY", "1.0")),
        max_latency=float(os.getenv("SANDBOX_MAX_LATENCY", "5.0")),
        min_reliability=float(os.getenv("SANDBOX_MIN_RELIABILITY", "0.9")),
        max_reliability=float(os.getenv("SANDBOX_MAX_RELIABILITY", "1.0")),
        block_discovery_chance=float(os.getenv("SANDBOX_BLOCK_DISCOVERY_CHANCE", "0.02")),
        max_hops_for_propagation=int(os.getenv("SANDBOX_MAX_HOPS", "5")),
        snapshot_interval_blocks=int(os.getenv("SANDBOX_SNAPSHOT_INTERVAL_BLOCKS", "10")),
        enable_forum=os.getenv("SANDBOX_ENABLE_FORUM", "1").strip().lower() in {"1", "true"},
        enable_attack_jamming=os.getenv("SANDBOX_ENABLE_ATTACK_JAMMING", "1").strip().lower() in {"1", "true"},
    )
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
            ("Edge Probability", f"{sim_cfg.edge_probability:.3f}"),
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
