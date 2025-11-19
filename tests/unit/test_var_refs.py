import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from .task_listener_test import TaskListenerTest
from .marker_collector import MarkerCollector

def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      DEBUG:
        type: bool
        value: false
    tasks:
    - name: t1
      with:
        param_1:
          type: bool
          value: ${{ DEBUG }}
        param_2:
          type: bool
          value: ${{ foo.DEBUG }}
      shell: pytask
      run: |
        with open(os.path.join(input.rundir, "foo.txt"), "w") as f:
          f.write("param_1: %s\\n" % input.params.param_1)
          f.write("param_2: %s\\n" % input.params.param_2)
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(marker_listeners=[marker]).load(os.path.join(tmpdir, "flow.dv"))

    print("Package:\n%s\n" % pkg.dump())
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    t1 = builder.mkTaskNode("foo.t1")
    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert os.path.isfile(os.path.join(tmpdir, "rundir/foo.t1", "foo.txt"))

def test_bool_params_are_bool_type(tmpdir):
    """Test that boolean parameters with variable references maintain Python bool type.
    
    This test verifies the fix for the issue where bool parameters were being 
    converted to strings ("true"/"false") instead of Python bool (True/False)
    when they contained variable references like ${{ DEBUG }}.
    """
    flow_dv = """
package:
    name: foo
    with:
      DEBUG:
        type: bool
        value: true
      VERBOSE:
        type: bool
        value: false
    tasks:
    - name: t1
      with:
        param_true:
          type: bool
          value: ${{ DEBUG }}
        param_false:
          type: bool
          value: ${{ VERBOSE }}
        param_qualified:
          type: bool
          value: ${{ foo.DEBUG }}
      shell: pytask
      run: |
        # Verify that parameters have the correct Python bool type
        assert isinstance(input.params.param_true, bool), f"param_true should be bool, got {type(input.params.param_true)}"
        assert isinstance(input.params.param_false, bool), f"param_false should be bool, got {type(input.params.param_false)}"
        assert isinstance(input.params.param_qualified, bool), f"param_qualified should be bool, got {type(input.params.param_qualified)}"
        
        # Verify that the values are correct
        assert input.params.param_true is True, f"param_true should be True, got {input.params.param_true}"
        assert input.params.param_false is False, f"param_false should be False, got {input.params.param_false}"
        assert input.params.param_qualified is True, f"param_qualified should be True, got {input.params.param_qualified}"
        
        # Write results to file for verification
        with open(os.path.join(input.rundir, "result.txt"), "w") as f:
          f.write("SUCCESS\\n")
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    t1 = builder.mkTaskNode("foo.t1")
    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert os.path.isfile(os.path.join(tmpdir, "rundir/foo.t1", "result.txt"))
    
    with open(os.path.join(tmpdir, "rundir/foo.t1", "result.txt"), "r") as f:
        content = f.read()
        assert "SUCCESS" in content
