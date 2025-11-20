import os
import subprocess
import sys
import pytest

# Test that running an alias task that depends on an overridden task no longer
# reports a missing parameter error due to lack of implicit 'uses' chaining.
# Previously, override tasks without an explicit 'uses' failed to inherit
# parameters from the base task, producing a loader error about a missing field.

def test_run_t2_no_missing_param(tmp_path):
    # Run 'dfm run t2' from project root
    root = os.path.dirname(__file__)
    # Locate repository root (two levels up from tests/unit)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    # Use python -m to invoke dfm
    cmd = [sys.executable, '-m', 'dv_flow.mgr', 'run', 't2']
    proc = subprocess.run(cmd, cwd=os.path.join(repo_root, 'tests', 'unit', 'data'), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, f"dfm run t2 failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    # Ensure no missing field error appears
    assert 'Field msg not found' not in proc.stdout
    assert 'Field msg not found' not in proc.stderr
