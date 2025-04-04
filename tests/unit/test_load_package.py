import asyncio
import os
from typing import Tuple
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter

def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: create_file
      uses: std.CreateFile
      with:
        filename: hello.txt
        content: |
          Hello World
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 1
    assert "create_file" in pkg.task_m.keys()

def test_need_same_pkg(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
    - name: t2
      needs: [t1]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 2
    assert "t1" in pkg.task_m.keys()
    assert "t2" in pkg.task_m.keys()

    t1 = pkg.task_m["t1"]
    t2 = pkg.task_m["t2"]
    assert t1.name == "t1"
    assert len(t1.needs) == 0
    assert t2.name == "t2"
    assert len(t2.needs) == 1
    assert t2.needs[0] is not None
    assert t2.needs[0].name == "t1"

def test_smoke_2(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: create_file
      uses: std.CreateFile
      with:
        filename: hello.txt
        content: |
          Hello World
      build:
        pytask
      check:
        # oracle ?
        # pytask (very short)
      body:
        strategy:
          chain:
          matrix: 
        tasks:
        pytask:
        shell:
        run: |
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 1
    assert "create_file" in pkg.task_m.keys()
