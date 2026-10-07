#****************************************************************************
#* test_elab_rebind_chain.py
#*
#* An elaborator bound to an abstract type is inherited along the `uses`
#* chain, so it often fires on a task that reaches the abstract type through
#* the user's own tasks (`R uses Base uses Abstract`). Specializing such a task
#* must keep everything the intermediate tasks declare -- params, needs -- and
#* must actually run the selected implementation.
#*
#* The original idiom, `dc.replace(task, uses=concrete)`, replaced R's FIRST
#* link and so spliced `Base` out of the chain. `ElabCtxt.rebindUses` rebinds
#* the link that points at the abstract type instead. These tests cover that
#* and the neighbors it touches: implementation borrowing (which used to look
#* the base up by name), shared intermediates, compound targets, and inherited
#* attributes.
#*
#* The two implementations record which one ran and with what params, so a
#* test can tell "right params, wrong (or empty) body" apart from success.
#****************************************************************************
import asyncio
import os
import sys
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task import iter_uses_chain
from dv_flow.mgr.task_graph_builder import BuilderElabCtxt
from .marker_collector import MarkerCollector


_MODULE = '''
from dv_flow.mgr import TaskDataResult

INVOKED = []
RAN = []

CONCRETE = ("foo.ImplA", "foo.ImplB", "foo.ImplC", "foo.ImplP")

def _chain(task):
    cur = task
    while cur is not None:
        yield cur
        cur = cur.uses

def select(ctxt, task, name):
    """Backend-selector shape: read `target`, rebind the abstract link."""
    INVOKED.append(name)
    if any(t.name in CONCRETE for t in _chain(task)):
        return ctxt.buildDefault(task, name)
    target = ctxt.resolveParam(task, "target", "")
    if target == "":
        raise Exception("no target selected for %s" % name)
    abstract = next(t for t in _chain(task) if t.elaborate == "rbmod:select")
    concrete = ctxt.getTask("foo.Impl%s" % target)
    return ctxt.buildDefault(ctxt.rebindUses(task, abstract, concrete), name)

async def impl_a(runner, input):
    RAN.append(("A", input.name, input.params.msg, input.params.extra))
    return TaskDataResult()

async def impl_b(runner, input):
    RAN.append(("B", input.name, input.params.msg, input.params.extra))
    return TaskDataResult()

async def impl_p(runner, input):
    RAN.append(("P", input.name, input.params.msg, input.params.extra))
    return TaskDataResult()

async def always_uptodate(ctxt):
    return True
'''


_HEADER = '''
package:
  name: foo
  tasks:
  - name: Abstract
    elaborate: rbmod:select
    with:
      target: {type: str, value: ""}
      msg: {type: str, value: "default"}
      extra: {type: str, value: "default"}
  - name: ImplA
    uses: Abstract
    pytask: rbmod.impl_a
    uptodate: rbmod:always_uptodate
  - name: ImplB
    uses: Abstract
    pytask: rbmod.impl_b
  - name: ImplP
    pytask: rbmod.impl_p
  - name: Dep1
    uses: std.Message
    with: {msg: "dep1"}
  - name: Dep2
    uses: std.Message
    with: {msg: "dep2"}
'''


@pytest.fixture
def env(tmpdir):
    d = str(tmpdir)
    with open(os.path.join(d, "rbmod.py"), "w") as f:
        f.write(_MODULE)
    sys.path.insert(0, d)
    sys.modules.pop("rbmod", None)
    yield d
    sys.path.remove(d)
    sys.modules.pop("rbmod", None)


def _builder(d, tasks):
    with open(os.path.join(d, "flow.dv"), "w") as f:
        f.write(_HEADER + tasks)
    collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[collector])
    pkg = loader.load(os.path.join(d, "flow.dv"))
    return TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(d, "rundir"),
                            marker_l=collector, loader=loader)


def _run(d, node):
    runner = TaskSetRunner(rundir=os.path.join(d, "rundir"))
    asyncio.run(runner.run(node))
    assert runner.status == 0
    import rbmod
    return rbmod


def _need_names(node):
    return sorted(n.name for n, _ in node.needs)


# --- The reported bug -------------------------------------------------------

def test_intermediate_with_survives_and_selected_body_runs(env):
    """REGRESSION: `with:` on an intermediate task reached the elaborator (it
    picked the right target) but was then dropped from the node's params."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: A, msg: "from-base"}
  - name: R
    uses: Base
''')
    node = b.mkTaskNode("foo.R")
    assert node.params.msg == "from-base"
    assert node.params.target == "A"
    rb = _run(env, node)
    assert rb.INVOKED == ["foo.R"]
    assert rb.RAN == [("A", "foo.R", "from-base", "default")]


def test_leaf_with_wins_intermediate_only_field_survives(env):
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: A, msg: "from-base", extra: "base-extra"}
  - name: R
    uses: Base
    with: {msg: "from-leaf"}
''')
    rb = _run(env, b.mkTaskNode("foo.R"))
    assert rb.RAN == [("A", "foo.R", "from-leaf", "base-extra")]


def test_two_intermediates_both_contribute(env):
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: B, extra: "base-extra"}
  - name: Mid
    uses: Base
    with: {msg: "from-mid"}
  - name: R
    uses: Mid
''')
    rb = _run(env, b.mkTaskNode("foo.R"))
    assert rb.RAN == [("B", "foo.R", "from-mid", "base-extra")]


# --- Adjacent: needs ----------------------------------------------------------

def test_intermediate_needs_survive(env):
    """The splice dropped an intermediate's `needs:` too, not only its params."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    needs: [Dep1]
    with: {target: A}
  - name: R
    uses: Base
''')
    assert _need_names(b.mkTaskNode("foo.R")) == ["foo.Dep1"]


def test_needs_from_every_level_are_wired(env):
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    needs: [Dep1]
    with: {target: A}
  - name: Mid
    uses: Base
    needs: [Dep2]
  - name: R
    uses: Mid
''')
    assert _need_names(b.mkTaskNode("foo.R")) == ["foo.Dep1", "foo.Dep2"]


# --- Adjacent: implementation borrowing ---------------------------------------

def test_leaf_selects_different_target_than_intermediate(env):
    """The leaf overrides the intermediate's selection. Params AND body must
    both follow the leaf: borrowing the body by the intermediate's NAME would
    build the original `Base` (target A, or the abstract's empty body)."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: A, msg: "from-base"}
  - name: R
    uses: Base
    with: {target: B}
''')
    rb = _run(env, b.mkTaskNode("foo.R"))
    assert rb.RAN == [("B", "foo.R", "from-base", "default")]


def test_no_stray_intermediate_node(env):
    """Specializing R must not build a node for `Base` as a side effect."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: A}
  - name: R
    uses: Base
''')
    b.mkTaskNode("foo.R")
    assert "foo.Base" not in b._task_node_m


def test_shared_intermediate_not_mutated(env):
    """Two consumers of one `Base` select different targets. Each gets its own
    implementation, and the shared `Base` Task is left as declared."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {msg: "shared"}
  - name: RA
    uses: Base
    with: {target: A}
  - name: RB
    uses: Base
    with: {target: B}
  - name: Top
    needs: [RA, RB]
''')
    base = b.lookupTask("foo.Base")
    abstract = b.lookupTask("foo.Abstract")
    base_uses_before = base.uses
    rb = _run(env, b.mkTaskNode("foo.Top"))
    assert sorted(rb.RAN) == [("A", "foo.RA", "shared", "default"),
                              ("B", "foo.RB", "shared", "default")]
    assert base.uses is base_uses_before is abstract
    assert base.paramT is None or "target" in base.paramT.model_fields


def test_intermediate_still_builds_on_its_own(env):
    """Building `Base` directly after a consumer specialized through it uses
    Base's own selection -- the consumer's rebind left no trace on it."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: A, msg: "from-base"}
  - name: R
    uses: Base
    with: {target: B}
  - name: Top
    needs: [R, Base]
''')
    rb = _run(env, b.mkTaskNode("foo.Top"))
    assert sorted(rb.RAN) == [("A", "foo.Base", "from-base", "default"),
                              ("B", "foo.R", "from-base", "default")]


def test_abstract_built_directly(env):
    """`task is old_base`: the elaborated task is the abstract type itself."""
    b = _builder(env, "")
    rb = _run(env, b.mkTaskNode("foo.Abstract", target="B", msg="kw"))
    assert rb.RAN == [("B", "foo.Abstract", "kw", "default")]


def test_target_not_derived_from_abstract(env):
    """The target need not `uses:` the abstract type (hdlsim's flag-set
    backends don't). The abstract link is replaced, so its declarations leave
    the chain -- by design: hdlsim's selection-only `sim` must not reach the
    emitted item. What the intermediate and the leaf set must still reach the
    target."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: P, msg: "from-base"}
  - name: R
    uses: Base
    with: {extra: "from-leaf"}
''')
    rb = _run(env, b.mkTaskNode("foo.R"))
    assert rb.RAN == [("P", "foo.R", "from-base", "from-leaf")]


def test_target_not_derived_from_abstract_direct(env):
    b = _builder(env, "")
    rb = _run(env, b.mkTaskNode("foo.Abstract", target="P", msg="kw"))
    assert rb.RAN == [("P", "foo.Abstract", "kw", "default")]


# --- Adjacent: compound target ------------------------------------------------

def test_compound_target_through_intermediate(env):
    """A compound implementation is borrowed by Task object, not by name; it
    must keep working through an intermediate and see the intermediate's
    params."""
    b = _builder(env, '''
  - name: ImplC
    uses: Abstract
    body:
    - name: inner
      uses: std.Message
      with: {msg: "inner ${{ msg }}"}
  - name: Base
    uses: Abstract
    with: {target: C, msg: "from-base"}
  - name: R
    uses: Base
''')
    node = b.mkTaskNode("foo.R")
    assert node.params.msg == "from-base"
    inner = [t for t in node.tasks if t.name.endswith("inner")]
    assert len(inner) == 1
    assert inner[0].params.msg == "inner from-base"


# --- Adjacent: inherited attributes -------------------------------------------

def test_target_uptodate_inherited_through_intermediate(env):
    """`uptodate` lives on the implementation; the specialized node must pick
    it up even though `Base`'s materialized value came from the abstract."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    with: {target: A}
  - name: R
    uses: Base
''')
    assert b.mkTaskNode("foo.R").uptodate == "rbmod:always_uptodate"


def test_intermediate_uptodate_wins_over_target(env):
    """An `uptodate:` the user declared on the intermediate is nearer than the
    implementation's and must survive the rebind."""
    b = _builder(env, '''
  - name: Base
    uses: Abstract
    uptodate: false
    with: {target: A}
  - name: R
    uses: Base
''')
    assert b.mkTaskNode("foo.R").uptodate is False


# --- rebindUses contract ------------------------------------------------------

def _ctxt(b):
    return BuilderElabCtxt(builder=b)


def test_rebind_uses_copies_every_link(env):
    b = _builder(env, '''
  - name: Base
    uses: Abstract
  - name: Mid
    uses: Base
  - name: R
    uses: Mid
''')
    r, mid, base = (b.lookupTask("foo.%s" % n) for n in ("R", "Mid", "Base"))
    abstract, impl = b.lookupTask("foo.Abstract"), b.lookupTask("foo.ImplA")
    v = _ctxt(b).rebindUses(r, abstract, impl)
    chain = list(iter_uses_chain(v))
    # Links above the abstract type are copies; the abstract link itself is
    # replaced by the target, whose own chain follows unchanged.
    assert [t.name for t in chain] == [
        "foo.R", "foo.Mid", "foo.Base", "foo.ImplA", "foo.Abstract"]
    for copy, orig in zip(chain[:3], (r, mid, base)):
        assert copy is not orig
    assert chain[3] is impl and chain[4] is abstract
    # originals untouched
    assert r.uses is mid and mid.uses is base and base.uses is abstract


def test_rebind_uses_matches_by_identity_not_name(env):
    import dataclasses as dc
    b = _builder(env, '''
  - name: Base
    uses: Abstract
  - name: R
    uses: Base
''')
    r = b.lookupTask("foo.R")
    lookalike = dc.replace(b.lookupTask("foo.Abstract"))
    with pytest.raises(Exception, match="not in the uses chain"):
        _ctxt(b).rebindUses(r, lookalike, b.lookupTask("foo.ImplA"))


def test_rebind_uses_task_is_old_base(env):
    b = _builder(env, "")
    abstract, impl = b.lookupTask("foo.Abstract"), b.lookupTask("foo.ImplA")
    v = _ctxt(b).rebindUses(abstract, abstract, impl)
    assert v is not abstract and v.uses is impl and abstract.uses is None
