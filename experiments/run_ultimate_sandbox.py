import os
import sys
from pathlib import Path

# Add project root to python path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.run_live_dashboard import main

if __name__ == "__main__":
    # We will override sys.argv to pass the desired arguments to the dashboard runner
    sys.argv = [
        "experiments/run_live_dashboard.py",
        "--steps", "3000",           # 0.04 * 3000 ≈ 120 个区块
        "--miners", "15",            # 15 个矿工智能体
        "--nodes", "15",             # 保持网络规模适中
        "--block-chance", "0.04",    # 中等出块概率
        "--disable-events", "none",  # 保留所有事件广播
        "--auto-open",                 # 自动打开 Dashboard
        "--port", "8080"             # 防止端口被占用
    ]
    
    # 强制环境变量以防读取偏差
    os.environ["SANDBOX_ENABLE_FORUM"] = "1"
    os.environ["SANDBOX_VERBOSE_LLM_LOG"] = "1"
    os.environ["SANDBOX_AGENT_PROFILE_FILE"] = str(Path("configs") / "agent_profiles.toml")
    
    print("=================================================================")
    print("🚀 启动终极沙盘测试 (全开模式: LLM无缓存 + 诚实节点智能 + 论坛开启)")
    print("=================================================================")
    print("[!] LLM_Config: Cache disabled, Honest LLM enabled, max_concurrent_requests=3.")
    print("[!] Target: ~120 blocks, 15 Miners, 15 Nodes, 0.04 block chance over 3000 steps.")
    print("=================================================================")
    
    main()
