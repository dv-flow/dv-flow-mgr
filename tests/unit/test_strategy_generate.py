import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef

def test_smoke(tmpdir, capsys):
    flow_dv = """
package:
    name: foo
    tasks:
    - name: expand
      with:
        count:
          type: int
          value: 5
      strategy:
        generate:
          run: |
            tasks = []
            for i in range(input.params.count):
              ctxt.addTask(ctxt.mkTaskNode(
                "foo.leaf", 
                name=ctxt.mkName("msg%d" % i),
                msg="Hello world %d" % i))
              
    - name: leaf
      uses: std.Message
      with:
        msg: "Hello world"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")

    loader, pkg_def = loadProjPkgDef(os.path.join(tmpdir))
    assert pkg_def is not None
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=rundir)
    runner = TaskSetRunner(rundir=rundir)

    task = builder.mkTaskNode("foo.expand")

    output = asyncio.run(runner.run(task))

    captured = capsys.readouterr()
    print("Captured:\n%s\n" % captured.out)
    for i in range(5):
        assert captured.out.find("msg%d: Hello world %d" % (i, i)) >= 0
#    assert captured.out.find("Hello, World!") >= 0

