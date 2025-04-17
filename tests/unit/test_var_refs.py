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
