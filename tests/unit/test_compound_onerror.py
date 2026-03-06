"""
Tests for TaskNodeCompound on_error/run callable, max_failures, and hierarchical scoping.

T3  – Compound with default aggregator propagates failures.
T4  – Compound with explicit run hook can absorb failures (return status=0).
T5  – max_failures=-1: independent subtasks continue after a sibling failure.
T6  – max_failures=1: independent subtasks are stopped after the first failure.
T7  – max_failures=N: independent subtasks stop after N failures.
T8  – Hierarchical scoping: inner compound policies are independent of outer.
T9  – Plain compound (backward-compat): still works correctly on success.
T12 – YAML round-trip: max_failures and on_error wired into TaskNodeCompound.
"""
import asyncio
import os
import pytest
from pydantic import BaseModel

from dv_flow.mgr import TaskSetRunner
from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
from dv_flow.mgr.task_node_compound import TaskNodeCompound
from dv_flow.mgr.task_data import (
    CompoundRunInput, TaskDataResult, TaskDataOutput, TaskFailure,
)
from dv_flow.mgr.task_def import ConsumesE, PassthroughE


class EmptyParams(BaseModel):
    pass


def _ctxt(tmpdir):
    return TaskNodeCtxt(
        root_pkgdir=tmpdir,
        root_rundir=os.path.join(tmpdir, "rundir"),
        env=os.environ.copy()
    )


def _leaf(name, task_fn, ctxt, tmpdir, needs=None, passthrough=None, consumes=None):
    node = TaskNodeLeaf(
        name=name,
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        task=task_fn,
        consumes=consumes if consumes is not None else ConsumesE.All,
        passthrough=passthrough,
    )
    if needs:
        for n in needs:
            node.needs.append((n, False))
    return node


def _make_compound(name, subtasks, ctxt, tmpdir, max_failures=-1, run=None):
    """Create a TaskNodeCompound wrapping the given subtasks."""
    compound = TaskNodeCompound(
        name=name,
        srcdir=tmpdir,
        params=EmptyParams(),
        ctxt=ctxt,
        max_failures=max_failures,
        run=run,
    )
    for t in subtasks:
        # Wire the compound's input sentinel as a prerequisite for each subtask
        if not any(n[0] is compound.input for n in t.needs):
            t.needs.append((compound.input, False))
        compound.tasks.append(t)
    # The compound itself depends on all terminal subtasks
    for t in subtasks:
        compound.needs.append((t, False))
    return compound


def _run(root, tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    runner = TaskSetRunner(rundir=rundir, nproc=4, enable_server=False)
    asyncio.run(runner.run(root))
    return runner


# ---------------------------------------------------------------------------
# T3 – Default aggregator propagates failures
# ---------------------------------------------------------------------------

def test_t3_default_aggregator_propagates_failure(tmp_path):
    """Compound with no explicit run hook propagates failure via default aggregator."""
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    async def prep(c, i): return TaskDataResult(status=1, output=[])
    async def run_task(c, i): return TaskDataResult(status=0, output=[])

    t_prep = _leaf("prep", prep, ctxt, tmpdir)
    # run_task depends on prep — will be skipped
    t_run = _leaf("run_task", run_task, ctxt, tmpdir, needs=[t_prep])

    compound = _make_compound("test_a", [t_prep, t_run], ctxt, tmpdir)

    runner = _run(compound, tmpdir)
    assert compound.result.status != 0
    assert runner.status != 0

    failure_items = [o for o in compound.output.output
                     if getattr(o, "type", None) == "std.TaskFailure"]
    assert len(failure_items) >= 1
    assert failure_items[0].task_name == "prep"


# ---------------------------------------------------------------------------
# T4 – Explicit run hook absorbs failures → status=0
# ---------------------------------------------------------------------------

def test_t4_explicit_run_absorbs_failure(tmp_path):
    """A compound whose run callable returns status=0 should make runner.status=0."""
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    async def prep(c, i): return TaskDataResult(status=1, output=[])

    t_prep = _leaf("prep", prep, ctxt, tmpdir)

    async def absorbing_run(ctxt, compound_input: CompoundRunInput):
        failures = [it for it in compound_input.inputs
                    if getattr(it, "type", None) == "std.TaskFailure"]
        assert len(failures) >= 1, "Expected at least one TaskFailure in compound input"
        # Absorb: translate to status=0 result
        return TaskDataResult(status=0, output=[])

    compound = _make_compound("test_a", [t_prep], ctxt, tmpdir, run=absorbing_run)

    runner = _run(compound, tmpdir)
    assert compound.result.status == 0, (
        "Compound status should be 0 after absorbing run; got %d" % compound.result.status)
    assert runner.status == 0, "runner.status should be 0 when compound absorbed failure"


# ---------------------------------------------------------------------------
# T5 – max_failures=-1: independent tasks continue after a failure
# ---------------------------------------------------------------------------

def test_t5_max_failures_neg1_continues(tmp_path):
    """With max_failures=-1 all independent subtasks run even after one fails."""
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    ran = []

    async def fail_task(c, i): return TaskDataResult(status=1, output=[])

    async def track(c, i, tag=None):
        ran.append(tag)
        return TaskDataResult(status=0, output=[])

    import functools
    t_a = _leaf("t_a", fail_task, ctxt, tmpdir)
    t_b = _leaf("t_b", functools.partial(track, tag="b"), ctxt, tmpdir)
    t_c = _leaf("t_c", functools.partial(track, tag="c"), ctxt, tmpdir)
    t_d = _leaf("t_d", functools.partial(track, tag="d"), ctxt, tmpdir)

    ran_results = []

    async def collecting_run(ctxt, inp: CompoundRunInput):
        return TaskDataResult(status=0, output=[])

    compound = _make_compound(
        "group", [t_a, t_b, t_c, t_d], ctxt, tmpdir,
        max_failures=-1, run=collecting_run)

    runner = _run(compound, tmpdir)

    # All of b, c, d should have run (t_a failed but is independent)
    assert set(ran) == {"b", "c", "d"}, (
        "Expected b,c,d to run with max_failures=-1; actually ran: %s" % ran)


# ---------------------------------------------------------------------------
# T6 – max_failures=1: independent tasks are stopped after first failure
# ---------------------------------------------------------------------------

def test_t6_max_failures_1_stops_on_first(tmp_path):
    """With max_failures=1 independent subtasks are skipped after the first failure.
    
    We force serial execution (nproc=1) to make this deterministic.
    """
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    ran = []

    async def ordered_fail(c, i): return TaskDataResult(status=1, output=[])
    async def ordered_ok(c, i, tag=None):
        ran.append(tag)
        return TaskDataResult(status=0, output=[])

    import functools
    t_a = _leaf("t_a", ordered_fail, ctxt, tmpdir)
    t_b = _leaf("t_b", functools.partial(ordered_ok, tag="b"), ctxt, tmpdir)
    t_c = _leaf("t_c", functools.partial(ordered_ok, tag="c"), ctxt, tmpdir)

    async def absorbing_run(ctxt, inp: CompoundRunInput):
        return TaskDataResult(status=0, output=[])

    compound = _make_compound(
        "group", [t_a, t_b, t_c], ctxt, tmpdir,
        max_failures=1, run=absorbing_run)

    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    runner = TaskSetRunner(rundir=rundir, nproc=1, enable_server=False)
    asyncio.run(runner.run(compound))

    # At least one of b,c should have been skipped
    assert len(ran) < 2, (
        "Expected fewer than 2 independent tasks to run with max_failures=1; ran: %s" % ran)


# ---------------------------------------------------------------------------
# T7 – max_failures=N threshold
# ---------------------------------------------------------------------------

def test_t7_max_failures_threshold(tmp_path):
    """With max_failures=2, the 3rd independent failing task should be skipped."""
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    ran = []

    async def fail_task(c, i, tag=None):
        ran.append(tag)
        return TaskDataResult(status=1, output=[])

    import functools
    t_a = _leaf("t_a", functools.partial(fail_task, tag="a"), ctxt, tmpdir)
    t_b = _leaf("t_b", functools.partial(fail_task, tag="b"), ctxt, tmpdir)
    t_c = _leaf("t_c", functools.partial(fail_task, tag="c"), ctxt, tmpdir)
    t_d = _leaf("t_d", functools.partial(fail_task, tag="d"), ctxt, tmpdir)

    async def absorbing_run(ctxt, inp: CompoundRunInput):
        return TaskDataResult(status=0, output=[])

    compound = _make_compound(
        "group", [t_a, t_b, t_c, t_d], ctxt, tmpdir,
        max_failures=2, run=absorbing_run)

    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    runner = TaskSetRunner(rundir=rundir, nproc=1, enable_server=False)
    asyncio.run(runner.run(compound))

    # With nproc=1 and max_failures=2, after 2 failures the 3rd+ should be skipped
    assert len(ran) <= 2, (
        "Expected at most 2 tasks to run with max_failures=2; ran: %s" % ran)


# ---------------------------------------------------------------------------
# T8 – Hierarchical scoping: inner compounds are independent
# ---------------------------------------------------------------------------

def test_t8_hierarchical_scoping(tmp_path):
    """Outer compound (max_failures=-1) should run both inner compounds even if one fails."""
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    inner_a_ran = []
    inner_b_ran = []

    async def fail_task(c, i): return TaskDataResult(status=1, output=[])
    async def pass_task(c, i, tracker=None):
        if tracker is not None:
            tracker.append(True)
        return TaskDataResult(status=0, output=[])

    import functools

    # Inner compound A: max_failures=1 wrapping [fail, should-skip]
    t_a1 = _leaf("a1_fail", fail_task, ctxt, tmpdir)
    t_a2 = _leaf("a2_skip", functools.partial(pass_task, tracker=inner_a_ran), ctxt, tmpdir)
    inner_a_run_called = []

    async def inner_a_run(ctxt, inp: CompoundRunInput):
        inner_a_run_called.append(True)
        return TaskDataResult(status=1, output=[])  # re-raise failure

    inner_a = _make_compound("inner_a", [t_a1, t_a2], ctxt, tmpdir,
                              max_failures=1, run=inner_a_run)

    # Inner compound B: independent, should still run
    t_b1 = _leaf("b1", functools.partial(pass_task, tracker=inner_b_ran), ctxt, tmpdir)
    inner_b_run_called = []

    async def inner_b_run(ctxt, inp: CompoundRunInput):
        inner_b_run_called.append(True)
        return TaskDataResult(status=0, output=[])

    inner_b = _make_compound("inner_b", [t_b1], ctxt, tmpdir, run=inner_b_run)

    # Outer compound: max_failures=-1 (run all)
    outer_run_called = []

    async def outer_run(ctxt, inp: CompoundRunInput):
        outer_run_called.append(True)
        return TaskDataResult(status=0, output=[])

    outer = _make_compound("outer", [inner_a, inner_b], ctxt, tmpdir,
                            max_failures=-1, run=outer_run)

    runner = _run(outer, tmpdir)

    # Inner A's run should have been called
    assert inner_a_run_called, "inner_a run callable should have been invoked"
    # Inner B should have run despite inner_a failing
    assert inner_b_run_called, "inner_b run callable should have been invoked"
    assert inner_b_ran, "inner_b tasks should have executed"
    # Outer run should have been called
    assert outer_run_called, "outer run callable should have been invoked"
    # Outer absorbed the failure → runner.status should be 0
    assert runner.status == 0


# ---------------------------------------------------------------------------
# T9 – Backward compatibility: plain compound succeeds as before
# ---------------------------------------------------------------------------

def test_t9_plain_compound_backward_compat(tmp_path):
    """A plain compound with no on_error/max_failures changes still works."""
    tmpdir = str(tmp_path)
    ctxt = _ctxt(tmpdir)

    async def ok_task(c, i): return TaskDataResult(status=0, output=[])

    t1 = _leaf("t1", ok_task, ctxt, tmpdir)
    t2 = _leaf("t2", ok_task, ctxt, tmpdir, needs=[t1])

    compound = _make_compound("plain", [t1, t2], ctxt, tmpdir)

    runner = _run(compound, tmpdir)
    assert compound.result.status == 0
    assert runner.status == 0


# ---------------------------------------------------------------------------
# T12 – YAML round-trip: max_failures and on_error wired
# ---------------------------------------------------------------------------

def test_t12_yaml_max_failures_roundtrip(tmp_path):
    """max_failures from flow.yaml must reach the TaskNodeCompound."""
    import json
    from dv_flow.mgr import PackageLoader, TaskGraphBuilder

    tmpdir = str(tmp_path)
    flow_yaml = """\
package:
    name: test_pkg

    tasks:
    - name: group
      max_failures: 2
      body:
      - name: subtask_a
        run: "exit 0"
"""
    flow_path = os.path.join(tmpdir, "flow.yaml")
    with open(flow_path, "w") as f:
        f.write(flow_yaml)

    pkg = PackageLoader().load(flow_path)
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.group")

    assert isinstance(node, TaskNodeCompound), (
        "Expected TaskNodeCompound, got %s" % type(node))
    assert node.max_failures == 2, (
        "Expected max_failures=2, got %d" % node.max_failures)
