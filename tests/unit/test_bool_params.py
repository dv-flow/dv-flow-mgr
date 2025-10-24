"""
Test for boolean parameter representation.

This test verifies that boolean parameters are properly represented as
Python bool strings (True/False) rather than JSON bool strings (true/false)
when used in expressions.
"""
import asyncio
import os
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from .marker_collector import MarkerCollector


def test_bool_param_representation(tmpdir):
    """Test that bool parameters use Python string representation (True/False)."""
    flow_dv = """
package:
    name: foo
    with:
      enabled:
        type: bool
        value: true
      disabled:
        type: bool
        value: false
      count:
        type: int
        value: 42
      pi:
        type: float
        value: 3.14

    tasks:
    - name: entry
      shell: bash
      run: |
        echo "enabled=${{ enabled }}" > out.txt
        echo "disabled=${{ disabled }}" >> out.txt
        echo "count=${{ count }}" >> out.txt
        echo "pi=${{ pi }}" >> out.txt
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))

    assert len(collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    asyncio.run(runner.run(t1))

    assert runner.status == 0
    
    # Verify output file exists and has correct content
    out_file = os.path.join(rundir, "rundir/t1/out.txt")
    assert os.path.isfile(out_file)
    
    with open(out_file, "r") as fp:
        lines = fp.read().strip().split('\n')
        # Boolean parameters should be represented as Python strings (True/False)
        # not as JSON strings (true/false)
        assert lines[0] == "enabled=True", f"Expected 'enabled=True', got '{lines[0]}'"
        assert lines[1] == "disabled=False", f"Expected 'disabled=False', got '{lines[1]}'"
        # Integer and float parameters should also use Python string representation
        assert lines[2] == "count=42", f"Expected 'count=42', got '{lines[2]}'"
        assert lines[3] == "pi=3.14", f"Expected 'pi=3.14', got '{lines[3]}'"


def test_bool_param_in_paramT(tmpdir):
    """Test that bool parameters maintain their type in the paramT."""
    flow_dv = """
package:
    name: foo
    with:
      flag:
        type: bool
        value: true

    tasks:
    - name: entry
      shell: bash
      run: echo "test"
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))

    # Create an instance of the paramT
    params = pkg.paramT()
    
    # Verify that the parameter is a Python bool, not a string
    assert isinstance(params.flag, bool), f"Expected bool type, got {type(params.flag)}"
    assert params.flag == True, f"Expected True, got {params.flag}"
