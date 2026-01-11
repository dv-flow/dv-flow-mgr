"""Performance test for measuring parallel task launch delays."""
import pytest
import subprocess
import os
import sys

def test_parallel_task_launch_delay(tmpdir):
    """Measure launch delay between parallel tasks."""
    nproc = int(subprocess.check_output(["nproc"]).decode().strip())
    num_tasks = nproc * 5
    
    print(f"\n=== Performance Test: Parallel Task Launch ===")
    print(f"CPU cores: {nproc}")
    print(f"Number of tasks: {num_tasks}")
    
    proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    rundir = str(tmpdir)
    
    # Create a simple flow file for the test
    flow_content = """
package:
  name: perftest

  tasks:
"""
    
    # Build list of task names for the 'needs' dependency
    for i in range(num_tasks):
        flow_content += f"""
  - name: task_{i}
    uses: std.Exec
    with:
      shell: bash
      command: "date +%s.%N > start_{i}.txt && sleep 1"
"""
    
    # Add a final task that depends on all others to trigger them all
    flow_content += """
  - name: RunAll
    uses: std.Message
    needs: ["""
    flow_content += ", ".join([f"task_{i}" for i in range(num_tasks)])
    flow_content += """]
    with:
      msg: "All tasks complete"
"""
    
    # Write the flow file
    flow_file = os.path.join(tmpdir, "flow.dv")
    with open(flow_file, "w") as f:
        f.write(flow_content)
    
    # Set up environment
    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir
    env["PYTHONPATH"] = os.path.join(proj_dir, "src")
    
    # Run the RunAll task which will trigger all others
    result = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", 
         "run",
         "-j", str(num_tasks),
         "RunAll"],
        cwd=rundir,
        env=env,
        capture_output=True,
        text=True
    )
    
    print(f"\nFlow execution output:")
    print(result.stdout)
    if result.stderr:
        print(f"Stderr: {result.stderr}")
    
    # Read all start times - files are created in the cwd where dfm was invoked
    start_times = []
    for i in range(num_tasks):
        start_file = os.path.join(rundir, f"start_{i}.txt")
        if os.path.exists(start_file):
            with open(start_file, "r") as f:
                timestamp = float(f.read().strip())
                start_times.append((i, timestamp))
    
    # Sort by timestamp
    start_times.sort(key=lambda x: x[1])
    
    # Calculate delays
    if start_times:
        first_start = start_times[0][1]
        last_start = start_times[-1][1]
        total_launch_span = last_start - first_start
        
        print(f"\n=== Results ===")
        print(f"Tasks launched: {len(start_times)}/{num_tasks}")
        print(f"Total launch span (first to last task): {total_launch_span:.3f}s")
        print(f"Average launch delay: {total_launch_span / (len(start_times) - 1) * 1000:.2f}ms")
        
        # Show launch time distribution
        print(f"\n=== Launch Time Distribution ===")
        for milestone in [10, 25, 50, 75, 90, 100]:
            idx = int((milestone / 100.0) * (len(start_times) - 1))
            if idx < len(start_times):
                task_id, timestamp = start_times[idx]
                delay_from_first = (timestamp - first_start) * 1000  # ms
                print(f"{milestone}% of tasks ({idx+1}/{len(start_times)}): {delay_from_first:.2f}ms from first")
        
        # Show delays between consecutive launches
        print(f"\n=== Consecutive Launch Delays (first 20) ===")
        consecutive_delays = []
        for i in range(1, min(20, len(start_times))):
            delay = (start_times[i][1] - start_times[i-1][1]) * 1000  # ms
            consecutive_delays.append(delay)
            print(f"Task {start_times[i-1][0]} -> Task {start_times[i][0]}: {delay:.2f}ms")
        
        if consecutive_delays:
            avg_consecutive = sum(consecutive_delays) / len(consecutive_delays)
            max_consecutive = max(consecutive_delays)
            min_consecutive = min(consecutive_delays)
            print(f"\nConsecutive delay stats (first 20):")
            print(f"  Average: {avg_consecutive:.2f}ms")
            print(f"  Min: {min_consecutive:.2f}ms")
            print(f"  Max: {max_consecutive:.2f}ms")
    
    assert len(start_times) == num_tasks, f"Expected {num_tasks} tasks, got {len(start_times)}"


def test_parallel_task_launch_scaled(tmpdir):
    """Measure launch delay with scaled up task count."""
    nproc = int(subprocess.check_output(["nproc"]).decode().strip())
    num_tasks = nproc * 10  # Scale to 10x
    
    print(f"\n=== Performance Test: Scaled Parallel Task Launch ===")
    print(f"CPU cores: {nproc}")
    print(f"Number of tasks: {num_tasks}")
    
    proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    rundir = str(tmpdir)
    
    # Create a simple flow file for the test
    flow_content = """
package:
  name: perftest_scaled

  tasks:
"""
    
    for i in range(num_tasks):
        flow_content += f"""
  - name: task_{i}
    uses: std.Exec
    with:
      shell: bash
      command: "date +%s.%N > start_{i}.txt && sleep 0.5"
"""
    
    # Add a final task that depends on all others to trigger them all
    flow_content += """
  - name: RunAll
    uses: std.Message
    needs: ["""
    flow_content += ", ".join([f"task_{i}" for i in range(num_tasks)])
    flow_content += """]
    with:
      msg: "All tasks complete"
"""
    
    # Write the flow file
    flow_file = os.path.join(tmpdir, "flow.dv")
    with open(flow_file, "w") as f:
        f.write(flow_content)
    
    # Set up environment
    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir
    env["PYTHONPATH"] = os.path.join(proj_dir, "src")
    
    # Run all tasks
    result = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", 
         "run",
         "-j", str(num_tasks),
         "RunAll"],
        cwd=rundir,
        env=env,
        capture_output=True,
        text=True
    )
    
    print(f"\nFlow execution completed with return code: {result.returncode}")
    
    # Read all start times - files are created in the cwd where dfm was invoked
    start_times = []
    for i in range(num_tasks):
        start_file = os.path.join(rundir, f"start_{i}.txt")
        if os.path.exists(start_file):
            with open(start_file, "r") as f:
                timestamp = float(f.read().strip())
                start_times.append((i, timestamp))
    
    # Sort by timestamp
    start_times.sort(key=lambda x: x[1])
    
    # Calculate delays
    if start_times:
        first_start = start_times[0][1]
        last_start = start_times[-1][1]
        total_launch_span = last_start - first_start
        
        print(f"\n=== Results ===")
        print(f"Tasks launched: {len(start_times)}/{num_tasks}")
        print(f"Total launch span (first to last task): {total_launch_span:.3f}s")
        print(f"Average launch delay: {total_launch_span / (len(start_times) - 1) * 1000:.2f}ms")
        
        # Show launch time distribution
        print(f"\n=== Launch Time Distribution ===")
        for milestone in [10, 25, 50, 75, 90, 100]:
            idx = int((milestone / 100.0) * (len(start_times) - 1))
            if idx < len(start_times):
                task_id, timestamp = start_times[idx]
                delay_from_first = (timestamp - first_start) * 1000  # ms
                print(f"{milestone}% of tasks ({idx+1}/{len(start_times)}): {delay_from_first:.2f}ms from first")
        
        # Calculate percentiles for consecutive delays
        consecutive_delays = []
        for i in range(1, len(start_times)):
            delay = (start_times[i][1] - start_times[i-1][1]) * 1000  # ms
            consecutive_delays.append(delay)
        
        if consecutive_delays:
            consecutive_delays_sorted = sorted(consecutive_delays)
            avg_consecutive = sum(consecutive_delays) / len(consecutive_delays)
            p50 = consecutive_delays_sorted[len(consecutive_delays_sorted) // 2]
            p90 = consecutive_delays_sorted[int(len(consecutive_delays_sorted) * 0.9)]
            p99 = consecutive_delays_sorted[int(len(consecutive_delays_sorted) * 0.99)]
            print(f"\n=== Consecutive Launch Delay Statistics ===")
            print(f"  Average: {avg_consecutive:.2f}ms")
            print(f"  Min: {min(consecutive_delays):.2f}ms")
            print(f"  P50 (median): {p50:.2f}ms")
            print(f"  P90: {p90:.2f}ms")
            print(f"  P99: {p99:.2f}ms")
            print(f"  Max: {max(consecutive_delays):.2f}ms")
    
    assert len(start_times) == num_tasks, f"Expected {num_tasks} tasks, got {len(start_times)}"
