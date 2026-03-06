"""
Tests for std.TaskFailure emission and pass-through.

T1 – A failing leaf emits exactly one TaskFailure item in its output.
T2 – A skipped task passes upstream TaskFailure items through unchanged.
"""
import asyncio
import os
import pytest
from pydantic import BaseModel

from dv_flow.mgr import TaskSetRunner
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_data import TaskDataResult, TaskFailure


class EmptyParams(BaseModel):
    pass


def _make_ctxt(tmpdir):
    return TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=os.path.join(tmpdir, "rundir"),
        env=os.environ.copy()
    )


def _make_leaf(name, task_fn, ctxt, tmpdir):
    from dv_flow.mgr.task_def import ConsumesE, PassthroughE
    return TaskNodeLeaf(
        name=name,
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        task=task_fn,
        consumes=ConsumesE.All,
        passthrough=None,
    )


# ---------------------------------------------------------------------------
# T1 – TaskFailure emitted on leaf failure
# ---------------------------------------------------------------------------

def test_t1_failure_emits_task_failure_item(tmp_path):
    """A leaf that returns status=1 must emit a TaskFailure item in its output."""
    tmpdir = str(tmp_path)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    ctxt = _make_ctxt(tmpdir)

    async def failing_task(ctxt, input):
        return TaskDataResult(status=1, output=[])

    node = _make_leaf("failing_leaf", failing_task, ctxt, tmpdir)

    runner = TaskSetRunner(rundir=rundir, nproc=1, enable_server=False)
    asyncio.run(runner.run(node))

    assert node.result.status == 1
    failure_items = [o for o in node.output.output
                     if getattr(o, "type", None) == "std.TaskFailure"]
    assert len(failure_items) == 1, (
        "Expected exactly one TaskFailure item, got: %s" % node.output.output)
    fi = failure_items[0]
    assert isinstance(fi, TaskFailure)
    assert fi.task_name == "failing_leaf"
    assert fi.status == 1


def test_t1_success_emits_no_task_failure_item(tmp_path):
    """A leaf that succeeds must NOT emit a TaskFailure item."""
    tmpdir = str(tmp_path)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    ctxt = _make_ctxt(tmpdir)

    async def passing_task(ctxt, input):
        return TaskDataResult(status=0, output=[])

    node = _make_leaf("passing_leaf", passing_task, ctxt, tmpdir)

    runner = TaskSetRunner(rundir=rundir, nproc=1, enable_server=False)
    asyncio.run(runner.run(node))

    assert node.result.status == 0
    failure_items = [o for o in node.output.output
                     if getattr(o, "type", None) == "std.TaskFailure"]
    assert len(failure_items) == 0


# ---------------------------------------------------------------------------
# T2 – TaskFailure passes through a skipped task
# ---------------------------------------------------------------------------

def test_t2_failure_passthrough_skipped_task(tmp_path):
    """A skipped task must expose upstream TaskFailure items in its output."""
    tmpdir = str(tmp_path)
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    ctxt = _make_ctxt(tmpdir)

    # t1 fails
    async def failing_task(ctxt, input):
        return TaskDataResult(status=1, output=[])

    # t2 depends on t1 (no explicit run hook — will be skipped)
    async def second_task(ctxt, input):
        return TaskDataResult(status=0, output=[])

    from dv_flow.mgr.task_def import ConsumesE, PassthroughE

    t1 = TaskNodeLeaf(
        name="t1_fail",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        task=failing_task,
        consumes=ConsumesE.All,
        passthrough=None,
    )
    t2 = TaskNodeLeaf(
        name="t2_skipped",
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        task=second_task,
        consumes=ConsumesE.All,
        passthrough=PassthroughE.All,
    )
    t2.needs.append((t1, False))

    runner = TaskSetRunner(rundir=rundir, nproc=1, enable_server=False)
    asyncio.run(runner.run(t2))

    # t2 was skipped so its result.status should be 1
    assert t2.result.status == 1

    # t2's output must contain the TaskFailure from t1
    failure_items = [o for o in t2.output.output
                     if getattr(o, "type", None) == "std.TaskFailure"]
    assert len(failure_items) >= 1, (
        "Expected TaskFailure to pass through skipped t2, got: %s" % t2.output.output)
    assert failure_items[0].task_name == "t1_fail"
