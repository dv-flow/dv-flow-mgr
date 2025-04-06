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
    assert "foo.create_file" in pkg.task_m.keys()

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
    assert "foo.t1" in pkg.task_m.keys()
    assert "foo.t2" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    t2 = pkg.task_m["foo.t2"]
    assert t1.name == "foo.t1"
    assert len(t1.needs) == 0
    assert t2.name == "foo.t2"
    assert len(t2.needs) == 1
    assert t2.needs[0] is not None
    assert t2.needs[0].name == "foo.t1"

def test_need_same_pkg_ooo(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
      needs: [t2]
    - name: t2
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
    assert "foo.t1" in pkg.task_m.keys()
    assert "foo.t2" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    t2 = pkg.task_m["foo.t2"]
    assert t1.name == "foo.t1"
    assert t1.ctor is not None
    assert len(t1.needs) == 1
    assert t1.needs[0] is not None
    assert t1.needs[0].name == "foo.t2"
    assert t1.needs[0].ctor is not None
    assert t2.name == "foo.t2"
    assert t2.ctor is not None
    assert len(t2.needs) == 0

def test_need_compound_1(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
      body:
        tasks:
        - name: t2
        - name: t3
          needs: [t2]
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
    assert "foo.t1" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    assert t1.name == "foo.t1"
    assert len(t1.subtasks) == 2
    assert len(t1.subtasks[0].needs) == 0
    assert len(t1.subtasks[1].needs) == 1
    assert t1.subtasks[1].needs[0] is not None
    assert t1.subtasks[1].needs[0].name == "foo.t1.t2"

def test_need_compound_2(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
      body:
        tasks:
        - name: t2
        - name: t3
          needs: [t4]
    - name: t4
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
    assert "foo.t1" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    assert t1.name == "foo.t1"
    assert len(t1.subtasks) == 2
    assert len(t1.subtasks[0].needs) == 0
    assert len(t1.subtasks[1].needs) == 1
    assert t1.subtasks[1].needs[0] is not None
    assert t1.subtasks[1].needs[0].name == "foo.t4"

def test_need_compound_3(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
      body:
        tasks:
        - name: t2
        - name: t3
    - name: t2
      uses: t1
      body:
        tasks:
        - name: t4
          needs: [t3]
    - name: t4
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 3
    assert "foo.t1" in pkg.task_m.keys()
    assert "foo.t2" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    assert t1.name == "foo.t1"
    assert len(t1.subtasks) == 2

    t2 = pkg.task_m["foo.t2"]
    assert len(t2.subtasks) == 1
    assert t2.subtasks[0].name == "foo.t2.t4"
    assert len(t2.subtasks[0].needs) == 1
    assert t2.subtasks[0].needs[0] is not None
    assert t2.subtasks[0].needs[0].name == "foo.t1.t3"

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
    assert "foo.create_file" in pkg.task_m.keys()
