import os
import sys
from pathlib import Path

# Add project root to python path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from blockchain_sandbox.cli.run_llm_sandbox import main

if __name__ == "__main__":
    # Configure specifically for a forum-heavy "social warfare" run
    os.environ["SANDBOX_TOTAL_STEPS"] = "200"
    os.environ["SANDBOX_NUM_MINERS"] = "12" 
    os.environ["SANDBOX_NUM_FULL_NODES"] = "30"
    
    # Enable forum explicitly
    os.environ["SANDBOX_ENABLE_FORUM"] = "1"
    
    # Configure LLM to be highly verbose for easier debugging
    os.environ["SANDBOX_VERBOSE_LLM_LOG"] = "1"
    
    # Use our aggressive agent profile which promotes usage of social action
    os.environ["SANDBOX_AGENT_PROFILE_FILE"] = str(Path("configs") / "agent_profiles.toml")
    
    # Keep output folder separate
    os.environ["SANDBOX_OUTPUT_ROOT"] = "outputs/social_warfare"
    
    print("Starting Social Warfare Experiment (LLM+Forum Enabled)...")
    main()
