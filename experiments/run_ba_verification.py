import os
import sys
from pathlib import Path

# Add project root to python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.run_honest_no_llm import main

if __name__ == "__main__":
    print("=== Running No-LLM Baseline with Random Topology ===")
    os.environ["SANDBOX_TOPOLOGY_TYPE"] = "random"
    os.environ["SANDBOX_NUM_MINERS"] = "20"
    os.environ["SANDBOX_NUM_FULL_NODES"] = "60"
    os.environ["SANDBOX_BLOCK_DISCOVERY_CHANCE"] = "0.05"  # Increase discovery chance to intentionally cause forks
    os.environ["SANDBOX_TOTAL_STEPS"] = "2000"
    os.environ["SANDBOX_TARGET_MINED_BLOCKS"] = "500"
    main()

    print("\n=== Running No-LLM Baseline with Barabasi-Albert Topology ===")
    os.environ["SANDBOX_TOPOLOGY_TYPE"] = "barabasi_albert"
    os.environ["SANDBOX_TOPOLOGY_BA_M"] = "3"
    main()
