import asyncio
import os
import sys
import time
import argparse
import msvcrt

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from blockchain_sandbox.core.config import AgenticSimulationConfig
from blockchain_sandbox.engine.agentic_simulation import AgenticBlockchainSimulation
from blockchain_sandbox.modules.forum_module import ForumModule
from blockchain_sandbox.modules.governance_module import GovernanceModule
from blockchain_sandbox.modules.network_attack_module import NetworkAttackModule
from blockchain_sandbox.modules.dashboard_module import LiveDashboardModule
from blockchain_sandbox.modules.metrics_module import MetricsObserverModule
from blockchain_sandbox.modules.tokenomics_module import TokenomicsModule


def _wait_for_shutdown(keep_alive: int, exit_key: str) -> None:
    exit_key = (exit_key or "q")[:1]

    if keep_alive > 0:
        print(f"Keeping server alive for {keep_alive} seconds so the dashboard catches up...")
        print(f"Press [{exit_key}] to gracefully stop the server early, or wait for auto-exit...")
        deadline = time.time() + keep_alive
        while time.time() < deadline:
            if msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                if key == exit_key.lower():
                    print("Exiting early...")
                    return
            time.sleep(0.1)
        print("Keep-alive timeout reached. Exiting...")
        return

    print(f"Keeping server alive indefinitely. Open http://127.0.0.1:8000/ in your browser.")
    print(f"Press [{exit_key}] to gracefully stop the server and exit...")
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getwch().lower()
            if key == exit_key.lower():
                print("Exiting...")
                return
        time.sleep(0.1)


def _suppress_asyncio_windows_bug():
    """Suppress harmless WinError 10054 spam on Windows Proactor EventLoop when WebSocket closes."""
    if sys.platform == 'win32':
        import logging
        logging.getLogger("asyncio").setLevel(logging.CRITICAL)


def _check_websockets_dependency():
    """Ensure websockets library is installed. Otherwise Uvicorn downgrades ws to http and causes 404/Disconnected."""
    try:
        import websockets
    except ImportError:
        print("\n" + "!"*60)
        print(" [FATAL ERROR] 'websockets' library is missing in your Python environment!")
        print(" Uvicorn cannot serve WebSocket endpoints without it, causing the 'Disconnected' issue.")
        print("\n Please install it immediately using:")
        print("     python -m pip install websockets")
        print("\n Alternatively, install standard uvicorn:")
        print("     python -m pip install \"uvicorn[standard]\"")
        print("!"*60 + "\n")
        sys.exit(1)

def main():
    _suppress_asyncio_windows_bug()
    _check_websockets_dependency()
    
    print("="*60)
    print("   Starting Sandbox with Live Web Dashboard")
    print("="*60)

    parser = argparse.ArgumentParser(description="Run Sandbox with Live Web Dashboard")
    parser.add_argument("--keep-alive", type=int, default=0, help="Seconds to keep server alive after simulation. 0 means wait for a manual exit key.")
    parser.add_argument("--exit-key", type=str, default="q", help="Single key used to manually close after simulation when --keep-alive is 0.")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable the live dashboard module.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Dashboard host.")
    parser.add_argument("--port", type=int, default=8000, help="Dashboard port.")
    parser.add_argument("--auto-open", action="store_true", help="Automatically open the dashboard in the default web browser.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait before starting simulation (allows browser to connect). Default 2.0s.")
    parser.add_argument("--steps", type=int, default=100, help="Total steps for the simulation. Default 100.")
    parser.add_argument("--disable-events", type=str, default="BLOCK_RECEIVED", help="Comma-separated list of events to drop at backend. Use 'none' to enable all events.")
    parser.add_argument("--miners", type=int, default=10, help="Number of miners in the network.")
    parser.add_argument("--nodes", type=int, default=20, help="Number of full nodes (clients) in the network.")
    parser.add_argument("--block-chance", type=float, default=0.02, help="Probability of block discovery per step.")
    args = parser.parse_args()

    # 1. Configure the simulation
    config = AgenticSimulationConfig(
        num_miners=args.miners,
        num_full_nodes=args.nodes,
        topology_type="barabasi_albert",
        total_steps=args.steps,
        block_discovery_chance=args.block_chance
    )

    # 2. Add regular gameplay modules
    modules = []
    dashboard = None
    
    forum_mod = ForumModule()
    modules.append(forum_mod)
    modules.append(GovernanceModule(
        ban_reputation_threshold=-10.0,
        reputation_provider=forum_mod.forum.reputation_of
    ))
    
    # Add network attack module but disable jamming logic so we only rely on forum attacks/fud
    modules.append(NetworkAttackModule(max_steps_of_jam_effect=6, enable_jamming=False))
    modules.append(TokenomicsModule())
    modules.append(MetricsObserverModule(snapshot_interval_blocks=10))

    # 3. Add the new LiveDashboardModule if not disabled
    if not args.no_dashboard:
        dashboard = LiveDashboardModule(host=args.host, port=args.port)
        if args.disable_events:
            if args.disable_events.lower() == "none":
                dashboard.disabled_events = set()
            else:
                dashboard.disabled_events = set(e.strip() for e in args.disable_events.split(","))
        modules.append(dashboard)

    from blockchain_sandbox.cli.provider_config import load_llm_config_from_yaml
    cfg_path = os.getenv("SANDBOX_LLM_CONFIG_FILE", str(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'configs', 'llm_provider.yaml'))))
    llm_cfg = load_llm_config_from_yaml(cfg_path)

    # 4. Instantiate the core engine with modules injected
    sim = AgenticBlockchainSimulation(
        config=config,
        llm_config=llm_cfg,
        modules=modules
    )

    if not args.no_dashboard and dashboard and dashboard._server_started:
        dashboard_url = f"http://{dashboard.host}:{dashboard.port}/"
        print(f"\n[!] Dashboard will be available at {dashboard_url}")
        print(f"[!] Health API: http://{dashboard.host}:{dashboard.port}/api/health")
        
        if args.auto_open:
            import webbrowser
            print(f"[!] Auto-opening browser to {dashboard_url} ...")
            webbrowser.open(dashboard_url)
            
    elif not args.no_dashboard:
        print("\n[!] Dashboard was not started (port may already be in use).")
    else:
        print("\n[!] Dashboard module is disabled for this run.")
        
    print(f"[!] The simulation will start in {args.delay} seconds...\n")
    time.sleep(args.delay)

    # 5. Run the simulation
    try:
        sim.run()
    except KeyboardInterrupt:
        print("\n[!] Simulation interrupted by user (KeyboardInterrupt).")
    except asyncio.CancelledError:
        print("\n[!] Simulation tasks were cancelled during shutdown.")

    print("\n" + "="*60)
    print("   Simulation Complete / Stopped.")
    print("="*60)
    
    if not args.no_dashboard and dashboard and dashboard._server_started:
        _wait_for_shutdown(args.keep_alive, args.exit_key)

if __name__ == "__main__":
    main()
