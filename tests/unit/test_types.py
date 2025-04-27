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
    types:
    - name: Params
      with:
        param1:
          type: str
          value: "1"
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

    params = builder.mkDataItem("foo.Params", param1="2")
    assert hasattr(params, "type")
    assert getattr(params, "type") == "foo.Params"
    print("params: %s" % str(params))
    assert hasattr(params, "param1")
    assert getattr(params, "param1") == "2"
