#****************************************************************************
#* test_set_matchers.py
#*
#* Phase 4 of the `set:` scoped-overrides feature: uses:/path: matchers +
#* forceful param sets on matched descendants (override with:, yield to CLI,
#* outer rule wins) and narrowed qualified rebinds under a scope item.
#* See docs/proposals/set_overrides_impl_plan.md Phase 4.
#****************************************************************************
import asyncio
import os
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from .marker_collector import MarkerCollector


def _load(tmpdir, flow_dv, param_overrides=None):
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    lk = {}
    if param_overrides is not None:
        lk["param_overrides"] = param_overrides
    pkg_def = PackageLoader(marker_listeners=[collector], **lk).load(
        os.path.join(tmpdir, "flow.dv"))
    return pkg_def, collector


def _run(tmpdir, flow_dv, taskname, capsys=None, builder_kwargs=None):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    pkg_def, collector = _load(tmpdir, flow_dv)
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector,
                               **(builder_kwargs or {}))
    runner = TaskSetRunner(rundir=rundir)
    node = builder.mkTaskNode(taskname)
    out = asyncio.run(runner.run(node))
    captured = capsys.readouterr().out if capsys is not None else ""
    return builder, node, captured, collector


def _build(tmpdir, flow_dv, taskname, builder_kwargs=None):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    pkg_def, collector = _load(tmpdir, flow_dv)
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector,
                               **(builder_kwargs or {}))
    return builder, builder.mkTaskNode(taskname), collector


def _find(node, frag):
    if frag in node.name:
        return node
    for t in getattr(node, "tasks", []):
        r = _find(t, frag)
        if r is not None:
            return r
    return None


# --- uses: force -----------------------------------------------------------

def test_uses_force_overrides_with(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    set:
    - uses: "std.Message"
      set:
      - msg: "FORCED"
    body:
    - name: R
      uses: std.Message
      with:
        msg: "orig"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "FORCED" in out and "orig" not in out


def test_uses_no_match_info(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    set:
    - uses: "foo.DoesNotExist*"
      set:
      - msg: "FORCED"
    body:
    - name: R
      uses: std.Message
      with:
        msg: "orig"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "orig" in out and "FORCED" not in out


def test_uses_matches_derived_isa(tmpdir, capsys):
    # A rule keyed on a base type matches an instance derived from it.
    flow = '''
package:
  name: foo
  tasks:
  - name: Base
    uses: std.Message
    with:
      msg: "base"
  - name: Top
    set:
    - uses: "foo.Base"
      set:
      - msg: "HIT"
    body:
    - name: R
      uses: Base
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "HIT" in out


# --- path: matcher ---------------------------------------------------------

def test_path_selects_region(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    set:
    - path: "**/Smoke*"
      set:
      - msg: "SMOKE"
    body:
    - name: Smoke
      uses: std.Message
      with:
        msg: "s-orig"
    - name: Other
      uses: std.Message
      with:
        msg: "o-orig"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "SMOKE" in out
    assert "o-orig" in out
    assert "s-orig" not in out


def test_uses_and_path_intersection(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    set:
    - uses: "std.Message"
      path: "**/Keep*"
      set:
      - msg: "HIT"
    body:
    - name: Keep
      uses: std.Message
      with:
        msg: "k-orig"
    - name: Skip
      uses: std.Message
      with:
        msg: "s-orig"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "HIT" in out
    assert "s-orig" in out
    assert "k-orig" not in out


# --- multiple rules / precedence -------------------------------------------

def test_two_scope_items_different_params(tmpdir):
    flow = '''
package:
  name: foo
  tasks:
  - name: Two
    uses: std.Message
    with:
      a:
        type: str
        value: "a0"
      b:
        type: str
        value: "b0"
      msg: "m"
  - name: Top
    set:
    - uses: "foo.Two"
      set:
      - a: "AX"
    - uses: "foo.Two"
      set:
      - b: "BX"
    body:
    - name: Item
      uses: Two
'''
    _, node, _ = _build(tmpdir, flow, "foo.Top")
    t = _find(node, "Item")
    assert t is not None
    assert t.params.a == "AX"
    assert t.params.b == "BX"


def test_outer_rule_beats_inner(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    set:
    - uses: "std.Message"
      set:
      - msg: "OUTER"
    body:
    - name: Inner
      set:
      - uses: "std.Message"
        set:
        - msg: "INNER"
      body:
      - name: R
        uses: std.Message
        with:
          msg: "orig"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "OUTER" in out
    assert "INNER" not in out
    assert "orig" not in out


def test_force_yields_to_cli_pinned(tmpdir, capsys):
    # A force rule must not override a param pinned from the CLI/-D. (The CLI
    # value itself is not applied to descendants here — a pre-existing limit —
    # so the observable is that the FORCE value did not take.)
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    set:
    - uses: "std.Message"
      set:
      - msg: "FORCED"
    body:
    - name: R
      uses: std.Message
      with:
        msg: "orig"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys,
                        builder_kwargs={"task_param_overrides": {"foo.Top.R": {"msg": "CLI"}}})
    assert "FORCED" not in out


# --- narrowed qualified rebind under a scope item --------------------------

def test_narrowed_qualified_rebind(tmpdir, capsys):
    # A qualified rebind under uses:/path: only reaches matched readers.
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: Reader
    uses: std.Message
    with:
      msg: "SIM=${{ foo.sim }}"
  - name: Top
    set:
    - path: "**/Match*"
      set:
      - foo.sim: mti
    body:
    - name: MatchIt
      uses: Reader
    - name: Skip
      uses: Reader
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    # The matched leg sees the rebind; the other keeps the default.
    assert "SIM=mti" in out
    assert "SIM=vlt" in out
