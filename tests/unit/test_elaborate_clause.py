#****************************************************************************
#* test_elaborate_clause.py
#*
#* The per-task `elaborate:` clause: a task type names a Python callable
#* (`module:function`) that elaborates the node at graph-build time, bound along
#* the `uses` chain. This is the declarative replacement for the elaborator
#* entry-point registry.
#****************************************************************************
import asyncio
import os
import sys
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_def import TaskDef
from .marker_collector import MarkerCollector


# An elaborator module written next to flow.dv; the function *is* the elaborator.
_ELAB_MODULE = '''
import dataclasses as dc

INVOKED = []

def passthrough(ctxt, task, name):
    """Record the invocation, then build the default interior unchanged."""
    INVOKED.append(name)
    return ctxt.buildDefault(task, name)

def rebind_to_banner(ctxt, task, name):
    """Rewrite `uses` to the flow's foo.Banner task (like the hdlsim backend
    selector rebinds to a concrete backend), so the node prints ELABORATED."""
    INVOKED.append(name)
    variant = dc.replace(task, uses=ctxt.getTask("foo.Banner"), paramT=None)
    return ctxt.buildDefault(variant, name)
'''


def _run(tmpdir, flow, taskname, capsys):
    d = str(tmpdir)
    with open(os.path.join(d, "elabmod.py"), "w") as f:
        f.write(_ELAB_MODULE)
    with open(os.path.join(d, "flow.dv"), "w") as f:
        f.write(flow)
    collector = MarkerCollector()
    sys.path.insert(0, d)
    try:
        for m in ("elabmod",):
            sys.modules.pop(m, None)
        pkg = PackageLoader(marker_listeners=[collector]).load(
            os.path.join(d, "flow.dv"))
        builder = TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(d, "rundir"),
                                   marker_l=collector)
        node = builder.mkTaskNode(taskname)
        out = asyncio.run(TaskSetRunner(rundir=os.path.join(d, "rundir")).run(node))
        import elabmod
        return node, capsys.readouterr().out, elabmod.INVOKED
    finally:
        sys.path.remove(d)


def test_elaborate_parses():
    t = TaskDef.model_validate({"name": "T", "elaborate": "mod:func"})
    assert t.elaborate == "mod:func"
    assert TaskDef.model_validate({"name": "T"}).elaborate is None


def test_elaborate_invoked_and_builds_default(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: R
    elaborate: elabmod:passthrough
    uses: std.Message
    with:
      msg: "hello"
'''
    node, out, invoked = _run(tmpdir, flow, "foo.R", capsys)
    assert invoked == ["foo.R"]          # the clause ran exactly once
    assert "hello" in out                # default interior built normally


def test_elaborate_can_rewrite_uses(tmpdir, capsys):
    # An elaborator that rebinds `uses` (like the hdlsim backend selector).
    flow = '''
package:
  name: foo
  tasks:
  - name: Banner
    uses: std.Message
    with:
      msg: "ELABORATED"
  - name: Abstract
    elaborate: elabmod:rebind_to_banner
  - name: R
    uses: Abstract
'''
    node, out, invoked = _run(tmpdir, flow, "foo.R", capsys)
    # Bound along the uses chain: R uses Abstract, which carries `elaborate:`.
    assert invoked == ["foo.R"]
    assert "ELABORATED" in out


def test_elaborate_bound_along_uses_chain_nearest_wins(tmpdir, capsys):
    # A derived type's own `elaborate:` is the one chosen at resolution (nearest
    # wins): Derived's rebind fires, not Base's passthrough.
    flow = '''
package:
  name: foo
  tasks:
  - name: Banner
    uses: std.Message
    with:
      msg: "ELABORATED"
  - name: Base
    elaborate: elabmod:passthrough
  - name: Derived
    elaborate: elabmod:rebind_to_banner
    uses: Base
  - name: R
    uses: Derived
'''
    node, out, invoked = _run(tmpdir, flow, "foo.R", capsys)
    # Derived's rebind (nearest) is selected -> banner prints.
    assert invoked == ["foo.R"]
    assert "ELABORATED" in out
