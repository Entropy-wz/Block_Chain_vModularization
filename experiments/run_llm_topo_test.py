from __future__ import annotations

import os
import sys

# 注入测试参数
os.environ["SANDBOX_TOTAL_STEPS"] = "30"
os.environ["SANDBOX_NUM_MINERS"] = "4"
os.environ["SANDBOX_NUM_FULL_NODES"] = "6"
os.environ["SANDBOX_BLOCK_DISCOVERY_CHANCE"] = "0.05"
os.environ["SANDBOX_ENABLE_FORUM"] = "0"
os.environ["SANDBOX_PREFLIGHT_STRICT"] = "0"
os.environ["SANDBOX_VERBOSE_LLM_LOG"] = "1"

def run_test(topo_type: str):
    print(f"\n==============================================")
    print(f"Testing LLM Sandbox with topology: {topo_type}")
    print(f"==============================================\n")
    
    os.environ["SANDBOX_TOPOLOGY_TYPE"] = topo_type
    
    # 我们调用底层的 run_llm_sandbox
    from blockchain_sandbox.cli.run_llm_sandbox import main
    try:
        main()
        print(f"✅ Success: {topo_type}")
    except Exception as e:
        print(f"❌ Failed: {topo_type}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        topologies = sys.argv[1:]
    else:
        topologies = ["watts_strogatz", "core_periphery"]
        
    for topo in topologies:
        run_test(topo)
