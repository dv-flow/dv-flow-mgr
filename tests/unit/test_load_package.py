import asyncio
import os
import pytest
from typing import Tuple
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter
from .marker_collector import MarkerCollector

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
    assert len(t1.needs) == 1
    assert t1.needs[0] is not None
    assert t1.needs[0].name == "foo.t2"
    assert t2.name == "foo.t2"
    assert len(t2.needs) == 0

def test_need_compound_1(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
      body:
      - name: t2
      - name: t3
        needs: [t2]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector],
        ).load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0

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
      - name: t2
      - name: t3
        needs: [t4]
    - name: t4
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector],
        ).load(os.path.join(tmpdir, "flow.dv"))
    
    assert len(marker_collector.markers) == 0

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
      - name: t2
      - name: t3
    - name: t2
      uses: t1
      body:
      - name: t4
        needs: [t3]
    - name: t4
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    assert len(marker_collector.markers) == 0

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

@pytest.mark.skip(reason="Not implemented")
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

    marker_collect = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collect]).load(os.path.join(tmpdir, "flow.dv"))

    assert len(marker_collect.markers) == 0

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 1
    assert "foo.create_file" in pkg.task_m.keys()

def test_need_fragment_1(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: t1
      body:
      - name: t2
      - name: t3
    - name: t2
      uses: t1
      body:
      - name: t4
        needs: [t3]
    - name: t4

    fragments:
    - frag.dv
"""

    frag_dv = """
fragment:
    tasks:
    - name: t5
      uses: t1
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    assert len(marker_collector.markers) == 0

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 4
    assert "foo.t1" in pkg.task_m.keys()
    assert "foo.t2" in pkg.task_m.keys()
    assert "foo.t5" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    assert t1.name == "foo.t1"
    assert len(t1.subtasks) == 2

    t2 = pkg.task_m["foo.t2"]
    assert len(t2.subtasks) == 1
    assert t2.subtasks[0].name == "foo.t2.t4"
    assert len(t2.subtasks[0].needs) == 1
    assert t2.subtasks[0].needs[0] is not None
    assert t2.subtasks[0].needs[0].name == "foo.t1.t3"

def test_dup_import(tmpdir):
    flow_dv = """
package:
    name: foo
    imports:
    - foo2/flow.dv
    - foo2/flow.dv

    tasks:
    - name: t1
      body:
      - name: t2
      - name: t3
    - name: t2
      uses: t1
      body:
      - name: t4
        needs: [t3]
    - name: t4
      need: [foo2.t5]

"""

    foo_dv = """
package:
    name: foo2
    tasks:
    - name: t5
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    os.makedirs(os.path.join(rundir, "foo2"))
    with open(os.path.join(rundir, "foo2/flow.dv"), "w") as fp:
        fp.write(foo_dv)

    def marker_collector(m):
        print("Marker: %s" % str(m))
        raise Exception("Marker not expected: %s" % m)

    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 3
    assert "foo.t1" in pkg.task_m.keys()
#    assert "foo.t2" in pkg.task_m.keys()
#    assert "foo.t5" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    assert t1.name == "foo.t1"
    assert len(t1.subtasks) == 2

def test_dup_import_subpkg(tmpdir):
    flow_dv = """
package:
    name: foo
    imports:
    - foo3/flow.dv
    - foo4/flow.dv

    tasks:
    - name: t1
      body:
      - name: t2
      - name: t3
    - name: t2
      uses: t1
      body:
      - name: t4
        needs: [t3]
    - name: t4
      need: [foo2.t5]

"""

    foo2_dv = """
package:
    name: foo2
    tasks:
    - name: t5
"""

    foo3_dv = """
package:
    name: foo3
    imports:
    - ../foo2/flow.dv
    tasks:
    - name: t5
"""

    foo4_dv = """
package:
    name: foo4
    imports:
    - ../foo2/flow.dv
    tasks:
    - name: t5
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    os.makedirs(os.path.join(rundir, "foo2"))
    with open(os.path.join(rundir, "foo2/flow.dv"), "w") as fp:
        fp.write(foo2_dv)
    os.makedirs(os.path.join(rundir, "foo3"))
    with open(os.path.join(rundir, "foo3/flow.dv"), "w") as fp:
        fp.write(foo3_dv)
    os.makedirs(os.path.join(rundir, "foo4"))
    with open(os.path.join(rundir, "foo4/flow.dv"), "w") as fp:
        fp.write(foo4_dv)

    def marker_collector(m):
        print("Marker: %s" % str(m))
        raise Exception("Marker not expected: %s" % m)

    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    assert pkg is not None
    assert pkg.pkg_def is not None
    assert pkg.name == "foo"
    assert pkg.basedir == rundir
    assert len(pkg.task_m) == 3
    assert "foo.t1" in pkg.task_m.keys()
#    assert "foo.t2" in pkg.task_m.keys()
#    assert "foo.t5" in pkg.task_m.keys()

    t1 = pkg.task_m["foo.t1"]
    assert t1.name == "foo.t1"
    assert len(t1.subtasks) == 2
