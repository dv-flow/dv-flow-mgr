"""
Tests for run_subgraph() with max_failures.

T10 – run_subgraph with max_failures=-1: independent tasks run even after a failure.
T11 – run_subgraph with max_failures=1: independent task is skipped after a failure.
"""
import asyncio
import os
import pytest
from pydantic import BaseModel

from dv_flow.mgr import TaskSetRunner
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_data import TaskDataResult
from dv_flow.mgr.task_def import ConsumesE


class EmptyParams(BaseModel):
    pass


def _ctxt(tmpdir):
    return TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=os.path.join(tmpdir, "rundir"),
        env=os.environ.copy()
    )


def _leaf(name, task_fn, ctxt, tmpdir, needs=None):
    node = TaskNodeLeaf(
        name=name,
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        task=task_fn,
        consumes=ConsumesE.All,
        passthrough=None,
    )
    if needs:
        for n in needs:
            node.needs.append((n, False))
    return node


# ---------------------------------------------------------------------------
# T10 – run_subgraph with max_failures=-1 continues after failure
# ---------------------------------------------------------------------------

def test_t10_run_subgraph_max_failures_neg1_continues(tmp_path):
    """run_subgraph(max_failures=-1): independent task runs even after sibling fails."""
    tmpdir = str(tmp_path)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    ctxt = _ctxt(tmpdir)

    ran = []

    async def parent_task(task_ctxt, input):
        async def fail_task(c, i):
            return TaskDataResult(status=1, output=[])

        async def ok_task(c, i):
            ran.append("ok")
            return TaskDataResult(status=0, output=[])

        t_fail = _leaf("dyn_fail", fail_task, ctxt, tmpdir)
        t_ok   = _leaf("dyn_ok",   ok_task,   ctxt, tmpdir)

        # max_failures=-1: both tasks are independent, ok_task should run
        await task_ctxt.run_subgraph([t_fail, t_ok], max_failures=-1)
        return TaskDataResult(status=0, output=[])

    parent = _leaf("parent", parent_task, ctxt, tmpdir)

    runner = TaskSetRunner(rundir=rundir, nproc=2, enable_server=False)
    asyncio.run(runner.run(parent))

    assert "ok" in ran, (
        "Expected ok_task to run with max_failures=-1; ran=%s" % ran)


# ---------------------------------------------------------------------------
# T11 – run_subgraph with max_failures=1 skips independent task after failure
# ---------------------------------------------------------------------------

def test_t11_run_subgraph_max_failures_1_skips(tmp_path):
    """run_subgraph(max_failures=1): independent task is skipped after the first failure."""
    tmpdir = str(tmp_path)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    ctxt = _ctxt(tmpdir)

    ran = []

    async def parent_task(task_ctxt, input):
        async def fail_task(c, i):
            return TaskDataResult(status=1, output=[])

        async def ok_task(c, i):
            ran.append("ok")
            return TaskDataResult(status=0, output=[])

        t_fail = _leaf("dyn_fail2", fail_task, ctxt, tmpdir)
        t_ok   = _leaf("dyn_ok2",   ok_task,   ctxt, tmpdir)

        # max_failures=1: after t_fail fails, t_ok should be skipped
        await task_ctxt.run_subgraph([t_fail, t_ok], max_failures=1)
        return TaskDataResult(status=0, output=[])

    parent = _leaf("parent2", parent_task, ctxt, tmpdir)

    # nproc=1 for deterministic ordering
    runner = TaskSetRunner(rundir=rundir, nproc=1, enable_server=False)
    asyncio.run(runner.run(parent))

    assert "ok" not in ran, (
        "Expected ok_task to be skipped with max_failures=1; ran=%s" % ran)
