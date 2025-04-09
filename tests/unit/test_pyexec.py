
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
  tasks:
  - name: entry
    shell: pytask
    run: |
      ctxt.info("pyexec: entry")
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(tmpdir, "flow.dv"))
    assert len(marker_collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("foo.entry")
    output = asyncio.run(runner.run(task))

    assert runner.status == 0
    assert len(task.result.markers) == 1
#    assert os.path.isdir(os.path.join(rundir, "pkg1.foo"))


