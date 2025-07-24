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

