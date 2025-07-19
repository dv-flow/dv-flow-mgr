
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

def test_fragment_local_python(tmpdir):
    flow_dv = """
package:
  name: foo


  tasks:
  - name: entry
    uses: Example
#    with:
#      message: "hello"

  fragments:
  - subdir/fragment.yml
"""

    fragment = """
fragment:

  tasks:
  - name: Example
    shell: pytask
    run: ${{ srcdir }}/example.py::Example
    with:
      message:
        type: str

"""

    example_py = """
from dv_flow.mgr import TaskDataResult

async def Example(ctxt, input):
    print("Example")
    ctxt.info("pyexec: entry")
    return TaskDataResult()
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    os.makedirs(os.path.join(tmpdir, "subdir"))
    with open(os.path.join(tmpdir, "subdir", "fragment.yml"), "w") as f:
        f.write(fragment)
    with open(os.path.join(tmpdir, "subdir", "example.py"), "w") as f:
        f.write(example_py)

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

def test_package_local_python(tmpdir):
    flow_dv = """
package:
  name: foo

  imports:
  - subdir/package.yml

  tasks:
  - name: entry
    uses: p2.Example
    with:
      message: "hello"
"""

    package = """
package:
  name: p2

  tasks:
  - name: Example
    shell: pytask
    run: ${{ srcdir }}/example.py::Example
    with:
      message:
        type: str

"""

    example_py = """
from dv_flow.mgr import TaskDataResult

async def Example(ctxt, input):
    print("Example")
    ctxt.info("pyexec: entry")
    return TaskDataResult()
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    os.makedirs(os.path.join(tmpdir, "subdir"))
    with open(os.path.join(tmpdir, "subdir", "package.yml"), "w") as f:
        f.write(package)
    with open(os.path.join(tmpdir, "subdir", "example.py"), "w") as f:
        f.write(example_py)

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
