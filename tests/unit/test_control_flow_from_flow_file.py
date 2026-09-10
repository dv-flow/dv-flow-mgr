"""BUG: `control:` in a flow file is parsed and then silently ignored.

A task declaring `control: {type: if, cond: ...}` runs its `body:`
unconditionally. The condition is never evaluated, and the `else:` branch never
runs -- so a flow file that reads as a conditional behaves as a plain compound.
There is no error, no warning, and no marker: the only symptom is that the wrong
tasks run.

Where it breaks
===============

`TaskGraphBuilder._build_default_interior` selects the control path with::

    if hasattr(task, 'control') and task.control is not None:
        return self._buildControlNode(...)

`task` there is a resolved `Task` (`task.py`), a dataclass with no `control`
field -- so `hasattr` is always False and the branch is dead. Nothing in
`package_provider_yaml` carries `TaskDef.control` across to the resolved task,
so there is nowhere for it to come from.

`_buildControlNode` itself reads `task.body`, `task.root` and `task.export`,
which are `TaskDef` fields and not `Task` fields. It was written against the
*definition* object while the call site passes the *resolved* object, which is
the shape of the underlying mistake: the two were never connected.

Why it was not caught
=====================

`test_task_node_control.py` and `test_expr_control_flow.py` construct
`ControlDef` and `TaskNodeControl` directly. Both pass, and both will keep
passing: the node classes work. What is untested is the path from a flow file to
those classes, which is the only path a user has.

That is the general lesson worth keeping -- a feature tested exclusively through
its internal API is a feature with no evidence that anyone can reach it.

A secondary defect
==================

`ControlDef` has no `extra='forbid'` (`TaskDef` and most siblings do), so a
misspelled or invented key is dropped in silence. Writing `then:` for the
taken branch -- a reasonable guess, since `else:` is spelled out -- parses
cleanly and does nothing.

Status
======

The characterization test below documents today's behaviour so the bug is
visible in the suite rather than only in prose. The `xfail`s state what should
happen; they flip to passes when this is fixed, which is the completion signal.
"""
import pytest

from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


FLOW = """\
package:
  name: p
  imports:
  - std
  tasks:
  - name: gate
    control:
      type: if
      cond: "false"
      else:
      - name: not-taken
        uses: std.Message
        with:
          msg: "ELSE"
    body:
    - name: taken
      uses: std.Message
      with:
        msg: "THEN"
"""


def _build(tmp_path, flow=FLOW):
    (tmp_path / "flow.dv").write_text(flow)
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    return TaskGraphBuilder(root_pkg=pkg,
                            rundir=str(tmp_path / "rundir"),
                            loader=loader)


def _leaf_names(node):
    """Every subtask name below `node`, leaf portion only."""
    out = []
    for sub in (getattr(node, "tasks", None) or []):
        if sub is node:
            continue
        out.append(getattr(sub, "name", "").split('.')[-1])
        out.extend(_leaf_names(sub))
    return out


# ---- Characterization: what happens today --------------------------------

def test_control_is_parsed_into_the_definition(tmp_path):
    """The front half works. `ControlDef` is built and validated correctly."""
    (tmp_path / "flow.dv").write_text(FLOW)
    loader, pkg = loadProjPkgDef(str(tmp_path))

    taskdef = None
    for td in pkg.pkg_def.tasks:
        if td.name == "gate":
            taskdef = td
    assert taskdef is not None
    assert taskdef.control is not None
    assert taskdef.control.type == "if"
    assert taskdef.control.cond == "false"
    assert len(taskdef.control.else_body) == 1


def test_control_does_not_survive_resolution(tmp_path):
    """...and the back half never receives it.

    This is the bug in one line. `_build_default_interior` gates the control
    path on `hasattr(task, 'control')`, and this is why that test never
    succeeds.
    """
    builder = _build(tmp_path)
    task = builder.root_pkg.task_m["p.gate"]
    assert not hasattr(task, "control"), (
        "`Task` has grown a `control` field -- if this now carries the "
        "definition, the xfails below should be passing and this "
        "characterization test should be deleted")


def test_the_wrong_branch_runs_today(tmp_path):
    """`cond: "false"` and the then-branch is built anyway.

    Characterization, not an endorsement: this asserts the defect so that
    fixing it produces a visible, deliberate test change rather than a silent
    behaviour swap.
    """
    node = _build(tmp_path).mkTaskNode("p.gate")
    names = _leaf_names(node)
    assert "taken" in names
    assert "not-taken" not in names


# ---- What should happen (flip to passes when fixed) ----------------------

@pytest.mark.xfail(reason="`control:` never reaches the resolved Task",
                   strict=True)
def test_false_condition_takes_the_else_branch(tmp_path):
    node = _build(tmp_path).mkTaskNode("p.gate")
    assert "not-taken" in _leaf_names(node)


@pytest.mark.xfail(reason="`control:` never reaches the resolved Task",
                   strict=True)
def test_false_condition_skips_the_body(tmp_path):
    node = _build(tmp_path).mkTaskNode("p.gate")
    assert "taken" not in _leaf_names(node)


def test_true_condition_takes_the_body(tmp_path):
    """Passes today, for the wrong reason.

    A true condition is indistinguishable from the bug: ignoring `control:`
    entirely and running the body unconditionally produces exactly this result.
    Kept as a plain assertion rather than an xfail because it is what should
    happen -- it simply proves nothing on its own, which is worth saying out
    loud next to the tests that do.
    """
    flow = FLOW.replace('cond: "false"', 'cond: "true"')
    node = _build(tmp_path, flow).mkTaskNode("p.gate")
    names = _leaf_names(node)
    assert "taken" in names
    assert "not-taken" not in names


@pytest.mark.xfail(reason="ControlDef lacks extra='forbid'", strict=True)
def test_an_unknown_control_key_is_rejected(tmp_path):
    """`then:` is a reasonable guess -- `else:` is spelled out, after all --
    and it currently parses cleanly and does nothing."""
    from pydantic import ValidationError

    flow = """\
package:
  name: p
  imports:
  - std
  tasks:
  - name: gate
    control:
      type: if
      cond: "true"
      then:
      - name: taken
        uses: std.Message
"""
    (tmp_path / "flow.dv").write_text(flow)
    with pytest.raises(ValidationError):
        loadProjPkgDef(str(tmp_path))
