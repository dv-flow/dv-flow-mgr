#****************************************************************************
#* test_task_elaborator.py
#*
#* Tests for per-type TaskElaborator dispatch (Feature A): binding along the
#* `uses` chain, the selectNeeds hook, the publish/lookup elaboration context,
#* and the root-only `args` rule. See
#* docs/proposals/task_elaboration_impl_plan.md §A and
#* docs/dfm_task_elaborator_design.md.
#****************************************************************************
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_elaborator import (
    TaskElaborator, DefaultLeafElaborator, DefaultCompoundElaborator)
from .marker_collector import MarkerCollector


def _builder(tmpdir, flow_dv):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector)
    return builder, collector


def _run(builder, taskname, capsys):
    runner = TaskSetRunner(rundir=builder.rundir)
    node = builder.mkTaskNode(taskname)
    asyncio.run(runner.run(node))
    return capsys.readouterr().out


# --- 1. Custom elaborator bound to a type is invoked -------------------------

def test_custom_elaborator_invoked(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Run
    uses: std.Message
    with:
      msg: "hello"
'''
    builder, _ = _builder(tmpdir, flow)

    class RecordElab(TaskElaborator):
        def __init__(self):
            self.seen = []
        def elaborate(self, ctxt, task, name):
            self.seen.append(name)
            return ctxt.buildDefault(task, name)

    elab = RecordElab()
    builder.register_elaborator("foo.Run", elab)
    out = _run(builder, "foo.Run", capsys)
    assert elab.seen == ["foo.Run"]
    assert "hello" in out


# --- 2. Binding resolves along the `uses` chain (nearest wins) ---------------

_CHAIN_FLOW = '''
package:
  name: foo
  tasks:
  - name: Base
    uses: std.Message
    with:
      msg: "base"
  - name: Mid
    uses: Base
  - name: Run
    uses: Mid
'''


def test_binding_nearest_ancestor_wins(tmpdir, capsys):
    builder, _ = _builder(tmpdir, _CHAIN_FLOW)

    class Tagged(TaskElaborator):
        def __init__(self, tag):
            self.tag = tag
            self.hits = 0
        def elaborate(self, ctxt, task, name):
            self.hits += 1
            return ctxt.buildDefault(task, name)

    e_base = Tagged("base")
    e_mid = Tagged("mid")
    builder.register_elaborator("foo.Base", e_base)
    builder.register_elaborator("foo.Mid", e_mid)
    _run(builder, "foo.Run", capsys)
    # foo.Run uses foo.Mid uses foo.Base: nearest bound ancestor is foo.Mid.
    assert e_mid.hits == 1
    assert e_base.hits == 0


def test_binding_grandparent_only(tmpdir, capsys):
    builder, _ = _builder(tmpdir, _CHAIN_FLOW)

    class Tagged(TaskElaborator):
        def __init__(self):
            self.hits = 0
        def elaborate(self, ctxt, task, name):
            self.hits += 1
            return ctxt.buildDefault(task, name)

    e_base = Tagged()
    builder.register_elaborator("foo.Base", e_base)
    _run(builder, "foo.Run", capsys)
    # Only the grandparent binds -> the walk reaches it.
    assert e_base.hits == 1


# --- 3. selectNeeds drops a subset of needs; body/leaf otherwise intact ------

def test_select_needs_drops_subset(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: A
    uses: std.Message
    with:
      msg: "A"
  - name: B
    uses: std.Message
    with:
      msg: "B"
  - name: Run
    uses: std.Message
    with:
      msg: "R"
    needs: [A, B]
'''
    builder, _ = _builder(tmpdir, flow)

    class DropB(TaskElaborator):
        def elaborate(self, ctxt, task, name):
            return ctxt.buildDefault(
                task, name,
                select_needs=lambda needs: [n for n in needs if not n.name.endswith(".B")])

    builder.register_elaborator("foo.Run", DropB())
    node = builder.mkTaskNode("foo.Run")
    need_names = [n.name for n, _ in node.needs]
    assert any(nm.endswith(".A") for nm in need_names)
    assert not any(nm.endswith(".B") for nm in need_names)


def test_default_compound_selectneeds_subclass(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: A
    uses: std.Message
    with:
      msg: "A"
  - name: B
    uses: std.Message
    with:
      msg: "B"
  - name: Top
    needs: [A, B]
    body:
    - name: Inner
      uses: std.Message
      with:
        msg: "inner"
'''
    builder, _ = _builder(tmpdir, flow)

    class DropB(DefaultCompoundElaborator):
        def selectNeeds(self, needs):
            return [n for n in needs if not n.name.endswith(".B")]

    builder.register_elaborator("foo.Top", DropB())
    node = builder.mkTaskNode("foo.Top")
    # Compound wires needs onto the input sentinel.
    input_need_names = [n.name for n, _ in node.input.needs]
    assert any(nm.endswith(".A") for nm in input_need_names)
    assert not any(nm.endswith(".B") for nm in input_need_names)
    # Body (wireBody) is intact.
    assert any(t.name.endswith(".Inner") for t in node.tasks)


# --- 4/5/7. publish / lookup elaboration context -----------------------------

_PARENT_CHILD_FLOW = '''
package:
  name: foo
  tasks:
  - name: Child
    uses: std.Message
    with:
      msg: "child"
  - name: Top
    body:
    - name: Child
      uses: std.Message
      with:
        msg: "child"
'''


def test_publish_lookup_root_to_nested(tmpdir, capsys):
    builder, _ = _builder(tmpdir, _PARENT_CHILD_FLOW)

    class RootElab(TaskElaborator):
        def elaborate(self, ctxt, task, name):
            ctxt.publish("filter", "SMOKE")
            return ctxt.buildDefault(task, name)

    class ChildElab(TaskElaborator):
        def __init__(self):
            self.seen = None
        def elaborate(self, ctxt, task, name):
            self.seen = ctxt.lookup("filter", "MISS")
            return ctxt.buildDefault(task, name)

    child = ChildElab()
    builder.register_elaborator("foo.Top", RootElab())
    # Body child is the nested task foo.Top.Child -> its *type* is std.Message,
    # so bind by the inner leaf name it resolves to. Bind to std.Message so the
    # nested body task picks it up.
    builder.register_elaborator("std.Message", child)
    _run(builder, "foo.Top", capsys)
    assert child.seen == "SMOKE"


def test_lookup_miss_returns_default(tmpdir, capsys):
    builder, _ = _builder(tmpdir, _PARENT_CHILD_FLOW)

    class ChildElab(TaskElaborator):
        def __init__(self):
            self.seen = None
        def elaborate(self, ctxt, task, name):
            self.seen = ctxt.lookup("absent", "DFLT")
            return ctxt.buildDefault(task, name)

    child = ChildElab()
    builder.register_elaborator("foo.Top", child)  # root, nothing published
    _run(builder, "foo.Top", capsys)
    assert child.seen == "DFLT"


# --- 6/12. Non-root elaborator reading args is a build error -----------------

def test_non_root_args_is_error(tmpdir, capsys):
    builder, _ = _builder(tmpdir, _PARENT_CHILD_FLOW)

    class RootElab(TaskElaborator):
        def elaborate(self, ctxt, task, name):
            return ctxt.buildDefault(task, name)

    class ChildElab(TaskElaborator):
        def elaborate(self, ctxt, task, name):
            _ = ctxt.args   # non-root -> must raise
            return ctxt.buildDefault(task, name)

    builder.register_elaborator("foo.Top", RootElab())
    builder.register_elaborator("std.Message", ChildElab())
    with pytest.raises(Exception) as ei:
        builder.mkTaskNode("foo.Top")
    assert "invariant #4" in str(ei.value) or "root-only" in str(ei.value)


def test_root_args_ok(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: "vlt"
  tasks:
  - name: Run
    uses: std.Message
    with:
      msg: "hi"
'''
    builder, _ = _builder(tmpdir, flow)

    class RootElab(TaskElaborator):
        def __init__(self):
            self.sim = None
        def elaborate(self, ctxt, task, name):
            args = ctxt.args
            self.sim = getattr(args, "sim", None)
            return ctxt.buildDefault(task, name)

    elab = RootElab()
    builder.register_elaborator("foo.Run", elab)
    _run(builder, "foo.Run", capsys)
    assert elab.sim == "vlt"


# --- 8. Default elaborator parity --------------------------------------------

def test_default_leaf_elaborator_parity(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Run
    uses: std.Message
    with:
      msg: "parity"
'''
    builder, _ = _builder(tmpdir, flow)
    builder.register_elaborator("foo.Run", DefaultLeafElaborator())
    out = _run(builder, "foo.Run", capsys)
    assert "parity" in out
