from __future__ import annotations

import os

from blockchain_sandbox.cli.run_llm_sandbox import main


def _set_default_env() -> None:
    # Focus: correctness check under low LLM concurrency + medium network latency.
    # This preset is tuned to get roughly ~80 discovered blocks in common runs.
    defaults = {
        "SANDBOX_TOTAL_STEPS": "900",
        "SANDBOX_NUM_MINERS": "8",
        "SANDBOX_NUM_FULL_NODES": "12",
        "SANDBOX_BLOCK_DISCOVERY_CHANCE": "0.05",
        "SANDBOX_RANDOM_SEED": "11",
        "SANDBOX_TOPOLOGY_TYPE": "barabasi_albert",
        "SANDBOX_TOPOLOGY_BA_M": "3",
        "SANDBOX_MIN_LATENCY": "2.0",
        "SANDBOX_MAX_LATENCY": "5.0",
        "SANDBOX_MIN_RELIABILITY": "0.96",
        "SANDBOX_MAX_RELIABILITY": "1.0",
        "SANDBOX_MAX_HOPS": "5",
        "SANDBOX_SNAPSHOT_INTERVAL_BLOCKS": "20",
        "SANDBOX_PROGRESS_INTERVAL_STEPS": "100",
        "SANDBOX_ENABLE_FORUM": "0",
        "SANDBOX_ENABLE_ATTACK_JAMMING": "0",
        "SANDBOX_ENABLE_TOKENOMICS": "0",
        "SANDBOX_SHOW_SNAPSHOTS": "0",
        "SANDBOX_LIVE_WINDOW_SUMMARY": "0",
        "SANDBOX_VERBOSE_LLM_LOG": "0",
        "SANDBOX_PREFLIGHT_LLM": "1",
        "SANDBOX_PREFLIGHT_STRICT": "1",
        "SANDBOX_LLM_MAX_WORKERS": "1",
        "SANDBOX_SELFISH_STRATEGY": "classic",
        "SANDBOX_OUTPUT_ROOT": "outputs/llm_smoke_80",
        "SANDBOX_SAVE_ARTIFACTS": "0",
        "SANDBOX_EXPORT_PROMPTS": "0",
    }
    for key, value in defaults.items():
        os.environ[key] = value


if __name__ == "__main__":
    _set_default_env()
    print("[LLM Smoke 80] starting correctness run...", flush=True)
    print(
        "[LLM Smoke 80] profile: low concurrency, medium latency, selfish-strategy only",
        flush=True,
    )
    print(
        "[LLM Smoke 80] target block zone: around 80 (depends on randomness/network race)",
        flush=True,
    )
    main()
