import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskGraphRunnerLocal, PackageDef
from dv_flow.mgr.util import loadProjPkgDef

def test_message(tmpdir, capsys):
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    uses: std.Message
    with:
      msg: "Hello, World!"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    rundir = os.path.join(tmpdir, "rundir")

    pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=rundir)
    runner = TaskGraphRunnerLocal(rundir=rundir)

    task = builder.mkTaskGraph("pkg1.foo")

    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    assert captured.out.find("Hello, World!") >= 0
