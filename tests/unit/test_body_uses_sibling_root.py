"""
Test that a body task inside a compound/root task can reference a sibling
root task in the same fragment via 'uses:'.

Reproduces the pattern from ioapic bench/tests/flow.yaml where
reg_smoke_all's body task does 'uses: reg_smoke' to reuse the
reg_smoke root task defined in the same fragment.
"""
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from .marker_collector import MarkerCollector


def test_body_uses_sibling_root_in_package(tmpdir):
    """Body task 'uses:' a sibling root task defined in the same package."""
    flow_dv = """
package:
    name: mypkg

    tasks:
    - root: worker
      body:
      - name: step
        uses: std.Message
        with:
          msg: "worker running"

    - root: orchestrator
      body:
      - name: core
        uses: worker
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))

    # Loading should succeed without errors
    errors = [m for m in collector.markers if "error" in str(m.severity).lower()]
    assert len(errors) == 0, (
        f"Unexpected load errors: {[m.msg for m in errors]}")

    # Should be able to build and run the orchestrator
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    task = builder.mkTaskNode("mypkg.orchestrator")
    output = asyncio.run(runner.run(task))

    assert runner.status == 0


def test_body_uses_sibling_root_in_named_fragment(tmpdir):
    """Body task 'uses:' a sibling root task in the same named fragment."""
    frag_dv = """
fragment:
    name: tests

    tasks:
    - root: worker
      body:
      - name: step
        uses: std.Message
        with:
          msg: "worker running"

    - root: orchestrator
      body:
      - name: core
        uses: worker
"""

    flow_dv = """
package:
    name: mypkg

    fragments:
    - frag.dv
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))

    # Loading should succeed without errors
    errors = [m for m in collector.markers if "error" in str(m.severity).lower()]
    assert len(errors) == 0, (
        f"Unexpected load errors: {[m.msg for m in errors]}")

    # The fragment task should be mypkg.tests.worker
    assert "mypkg.tests.worker" in pkg.task_m, (
        f"Expected mypkg.tests.worker in {list(pkg.task_m.keys())}")
    assert "mypkg.tests.orchestrator" in pkg.task_m, (
        f"Expected mypkg.tests.orchestrator in {list(pkg.task_m.keys())}")

    # Should be able to build and run
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    task = builder.mkTaskNode("mypkg.tests.orchestrator")
    output = asyncio.run(runner.run(task))

    assert runner.status == 0


def test_body_uses_sibling_root_with_matrix(tmpdir):
    """Body task 'uses:' a sibling root task with matrix strategy."""
    frag_dv = """
fragment:
    name: tests

    tasks:
    - root: worker
      body:
      - name: step
        uses: std.Message
        with:
          msg: "worker running"

    - root: worker_all
      strategy:
        matrix:
          greeting:
          - "hello"
          - "world"
      body:
      - name: core
        uses: worker
"""

    flow_dv = """
package:
    name: mypkg

    fragments:
    - frag.dv
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "frag.dv"), "w") as fp:
        fp.write(frag_dv)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))

    errors = [m for m in collector.markers if "error" in str(m.severity).lower()]
    assert len(errors) == 0, (
        f"Unexpected load errors: {[m.msg for m in errors]}")

    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    task = builder.mkTaskNode("mypkg.tests.worker_all")
    output = asyncio.run(runner.run(task))

    assert runner.status == 0
