import asyncio
import json
import os
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter
from .marker_collector import MarkerCollector


def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      p1:
        type: str
        value: hello

    tasks:
    - name: entry
      shell: bash
      run: |
        echo "${{ p1 }}" > out.txt
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert os.path.isfile(os.path.join(rundir, "rundir/t1/out.txt"))
    with open(os.path.join(rundir, "rundir/t1/out.txt"), "r") as fp:
        assert fp.read().strip() == "hello"


def test_example(tmpdir):

    flow_dv = """
package:
  name: uvm
  with:
    sim:
      type: str
      value: "base"

  tasks:
  - name: a.base.c

  - name: t1
    uses: "a.${{ sim }}.c"
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("uvm.t1", name="t1")

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
#    assert os.path.isfile(os.path.join(rundir, "rundir/t1/out.txt"))
#    with open(os.path.join(rundir, "rundir/t1/out.txt"), "r") as fp:
#        assert fp.read().strip() == "hello"


def test_param_in_uses_elab(tmpdir):
    """Regression: parameter in uses expression should resolve without exception."""
    flow_dv = """
package:
  name: regress
  with:
    sim:
      type: str
      value: base
  tasks:
  - name: t_bad
    uses: "nonexist.${{ sim }}.task"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    from dv_flow.mgr import PackageLoader
    try:
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    except Exception as e:
        assert "Variable 'sim' not found" not in str(e), f"Parameter resolution failed: {e}"
        raise
    assert 'sim' in pkg.paramT.model_fields
    assert pkg.paramT.model_fields['sim'].default == 'base'

def test_pkg_import(tmpdir):
    """Regression: parameter in uses expression should resolve without exception."""
    flow_dv = """
package:
  name: regress
  with:
    sim:
      type: str
      value: base
  imports:
  - pkg.yaml
  tasks:
  - name: t_bad
    uses: pkg.p1_task
    with:
      param:
        type: str
        value: "${{ sim }}"
"""
    pkg_yaml = """
package:
    name: pkg
    tasks:
    - name: p1_task
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "pkg.yaml"), "w") as fp:
        fp.write(pkg_yaml)

    from dv_flow.mgr import PackageLoader
    try:
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    except Exception as e:
        assert "Variable 'sim' not found" not in str(e), f"Parameter resolution failed: {e}"
        raise
    assert 'sim' in pkg.paramT.model_fields
    assert pkg.paramT.model_fields['sim'].default == 'base'