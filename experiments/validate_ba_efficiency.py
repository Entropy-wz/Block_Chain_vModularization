import json
import glob
from pathlib import Path
import os
import statistics

def analyze_topology_impact():
    print("=== Analyzing Topology Impact (Random vs Barabasi-Albert) ===")
    
    random_orphans = []
    ba_orphans = []
    
    random_efficiency = []
    ba_efficiency = []
    
    for summary_file in glob.glob("outputs/**/summary.json", recursive=True):
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            config = data.get("config", {})
            metrics = data.get("metrics", {})
            
            topo = config.get("topology_type")
            orphan_ratio = metrics.get("orphan_ratio")
            net_eff = metrics.get("network_efficiency")  # Typically 1.0 / avg shortest path
            
            if topo is not None:
                # Some runs might not have top-level orphan_ratio but have orphan_blocks and canonical head info
                if orphan_ratio is None and "orphan_blocks" in metrics:
                    # Approximation if total blocks isn't easily available
                    pass
                if orphan_ratio is not None:
                    if topo == "random":
                        random_orphans.append(orphan_ratio)
                        if net_eff is not None:
                            random_efficiency.append(net_eff)
                    elif topo == "barabasi_albert":
                        ba_orphans.append(orphan_ratio)
                        if net_eff is not None:
                            ba_efficiency.append(net_eff)
        except Exception as e:
            pass

    print(f"\n[Random Topology] Sample Size: {len(random_orphans)}")
    if random_orphans:
        print(f"  Avg Orphan Ratio : {statistics.mean(random_orphans):.4f}")
        print(f"  Max Orphan Ratio : {max(random_orphans):.4f}")
    if random_efficiency:
        print(f"  Avg Network Eff  : {statistics.mean(random_efficiency):.4f}")

    print(f"\n[Barabasi-Albert Topology] Sample Size: {len(ba_orphans)}")
    if ba_orphans:
        print(f"  Avg Orphan Ratio : {statistics.mean(ba_orphans):.4f}")
        print(f"  Max Orphan Ratio : {max(ba_orphans):.4f}")
    if ba_efficiency:
        print(f"  Avg Network Eff  : {statistics.mean(ba_efficiency):.4f}")
        
    print("\n[Conclusion]")
    if ba_orphans and random_orphans:
        if statistics.mean(ba_orphans) < statistics.mean(random_orphans):
            print("  => BA networks show a REDUCED orphan ratio compared to Random networks (Significant feature!).")
            print("     This implies hub nodes facilitate faster propagation and less consensus fragmentation.")
        else:
            print("  => BA networks did not show a reduced orphan ratio in this sample set.")

def analyze_performance():
    print("\n=== Analyzing LLM Simulation Performance ===")
    
    llm_runs = []
    
    for summary_file in glob.glob("outputs/**/summary.json", recursive=True):
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if it was an LLM run by checking metrics for prompt traces or decision calls
            metrics = data.get("metrics", {})
            config = data.get("config", {})
            
            # Use 'total_steps' as an indicator of work done
            steps = config.get("total_steps", 0)
            elapsed = data.get("elapsed_seconds")
            mode = data.get("mode", "")
            
            # LLM Runs might just have an elapsed time and prompt traces
            has_traces = len(data.get("prompt_traces", [])) > 0
            
            if elapsed and elapsed > 5.0 and (has_traces or "no_llm" not in mode) and steps > 0:
                # Approximate an asynchronous/synchronous flag based on recent commits
                # If "max_concurrent_requests" exists in llm config, it's likely async aware, but we can't easily parse that from summary alone.
                # We'll just list them out to see the throughput
                throughput = steps / elapsed
                llm_runs.append((elapsed, steps, throughput, summary_file))
        except:
            pass

    # Sort by creation time / file path
    llm_runs.sort(key=lambda x: os.path.getmtime(x[3]))
    
    if not llm_runs:
        print("No significant LLM runs found for comparison.")
        return
        
    print("Recent LLM Simulation Runs (Ordered by Time):")
    for r in llm_runs:
        file_name = Path(r[3]).parent.name
        print(f"  Run: {file_name:<20} | Time: {r[0]:6.1f}s | Steps: {r[1]:<4} | Throughput: {r[2]:.2f} steps/s")

if __name__ == "__main__":
    analyze_topology_impact()
    analyze_performance()
