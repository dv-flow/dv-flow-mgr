import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from .task_listener_test import TaskListenerTest
from .marker_collector import MarkerCollector

def test_glob_sys(tmpdir):
    flow_dv = """
package:
  name: p1

  tasks:
  - name: glob1
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
      incdirs: ["srcdir"]
  - name: glob2
    uses: std.FileSet
    with:
      type: verilogSource
      include: "*.v"
      incdirs: ["srcdir"]
  - name: glob_base
    passthrough: all
    needs: [glob1]
  - name: glob_uses
    uses: glob_base
    needs: [glob2]
"""

    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    with open(os.path.join(rundir, "top.sv"), "w") as fp:
        fp.write("\n")
    with open(os.path.join(rundir, "top.v"), "w") as fp:
        fp.write("\n")
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("p1.glob_uses")
    output = asyncio.run(runner.run(task))

    print("output: %s" % str(output))

    assert len(output.output) == 2
    fs = output.output[0]
    assert len(fs.files) == 1
    assert fs.files[0] == "top.sv"
    fs = output.output[1]
    assert len(fs.files) == 1
    assert fs.files[0] == "top.v"
