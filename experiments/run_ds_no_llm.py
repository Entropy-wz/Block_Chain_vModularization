from __future__ import annotations

import os

from blockchain_sandbox.cli.run_llm_sandbox import main


def _set_default_env() -> None:
    defaults = {
        # Core runtime profile
        "SANDBOX_TOTAL_STEPS": "4000",
        "SANDBOX_RANDOM_SEED": "11",
        "SANDBOX_NUM_MINERS": "8",
        "SANDBOX_NUM_FULL_NODES": "12",
        # Network profile (low concurrency + medium latency)
        "SANDBOX_TOPOLOGY_TYPE": "random",
        "SANDBOX_EDGE_PROB": "0.24",
        "SANDBOX_MIN_LATENCY": "2.0",
        "SANDBOX_MAX_LATENCY": "5.0",
        "SANDBOX_MIN_RELIABILITY": "0.96",
        "SANDBOX_MAX_RELIABILITY": "1.0",
        "SANDBOX_BLOCK_DISCOVERY_CHANCE": "0.05",
        "SANDBOX_MAX_HOPS": "5",
        # Strategy + DS
        "SANDBOX_SELFISH_STRATEGY": "stubborn_ds",
        "SANDBOX_DS_TARGET_CONFIRMATIONS": "2",
        "SANDBOX_DS_PAYMENT_AMOUNT": "3.0",
        "SANDBOX_DS_ATTACK_INTERVAL_BLOCKS": "30",
        # Disable unrelated modules
        "SANDBOX_ENABLE_FORUM": "0",
        "SANDBOX_ENABLE_ATTACK_JAMMING": "0",
        # Keep economy input off; DS strategy will force it on effectively.
        "SANDBOX_ENABLE_TOKENOMICS": "0",
        "SANDBOX_ECONOMY_ENABLED": "0",
        # Output and logs
        "SANDBOX_SNAPSHOT_INTERVAL_BLOCKS": "20",
        "SANDBOX_PROGRESS_INTERVAL_STEPS": "200",
        "SANDBOX_SHOW_SNAPSHOTS": "0",
        "SANDBOX_LIVE_WINDOW_SUMMARY": "0",
        "SANDBOX_SAVE_ARTIFACTS": "1",
        "SANDBOX_EXPORT_PROMPTS": "0",
        "SANDBOX_OUTPUT_ROOT": "outputs/exp_ds_no_llm",
        # No-LLM mode
        "SANDBOX_LLM_OFFLINE": "1",
        "SANDBOX_PREFLIGHT_LLM": "1",
        "SANDBOX_PREFLIGHT_STRICT": "1",
        "SANDBOX_LLM_MAX_WORKERS": "1",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


if __name__ == "__main__":
    _set_default_env()
    print("[DS no-LLM] starting run on shared engine (offline decision backend)...", flush=True)
    print("[DS no-LLM] strategy=stubborn_ds, economy auto-enforced by strategy", flush=True)
    main()
