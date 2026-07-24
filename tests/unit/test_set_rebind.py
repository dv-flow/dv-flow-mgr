#****************************************************************************
#* test_set_rebind.py
#*
#* Phase 2 of the `set:` scoped-overrides feature: qualified-name assignments
#* rebind a package variable that ordinary ${{ pkg.var }} references resolve to,
#* under the precedence CLI(-D) > outer set: > inner set: > declared default.
#* See docs/proposals/set_overrides_impl_plan.md Phase 2 (§2.2 matrix).
#****************************************************************************
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from .marker_collector import MarkerCollector


def _run(tmpdir, flow_dv, taskname, capsys=None, param_overrides=None):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    loader_kwargs = {}
    if param_overrides is not None:
        loader_kwargs["param_overrides"] = param_overrides
    pkg_def = PackageLoader(marker_listeners=[collector], **loader_kwargs).load(
        os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode(taskname)
    out = asyncio.run(runner.run(task))
    captured = capsys.readouterr().out if capsys is not None else ""
    return builder, out, captured, collector


# a. no override -> declared default.
def test_default_when_no_override(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: Top
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ foo.sim }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "SIM=vlt" in out


# c. set: beats the declared default; sibling without set: keeps the default.
def test_set_rebind_and_sibling_isolation(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: Plain
    uses: std.Message
    with:
      msg: "PLAIN=${{ foo.sim }}"
  - name: Top
    set:
    - foo.sim: mti
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "TOP=${{ foo.sim }}"
'''
    # Top's subtree sees the rebind ...
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "TOP=mti" in out
    # ... a task outside Top's subtree keeps the default.
    _, _, out2, _ = _run(tmpdir, flow, "foo.Plain", capsys)
    assert "PLAIN=vlt" in out2


# d. outer set: overrides an inner set: on the same var (outer wins).
def test_outer_set_beats_inner(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: Top
    set:
    - foo.sim: mti
    body:
    - name: OuterRun
      uses: std.Message
      with:
        msg: "OUTER=${{ foo.sim }}"
    - name: Inner
      set:
      - foo.sim: xcm
      body:
      - name: InnerRun
        uses: std.Message
        with:
          msg: "INNER=${{ foo.sim }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "OUTER=mti" in out
    # Outer overrides inner: the nested set: does NOT re-decide the var.
    assert "INNER=mti" in out
    assert "INNER=xcm" not in out


# e. CLI (-D) is the ceiling: a `set:` rebind YIELDS to a CLI-pinned var, and the
# CLI value is what resolves.
def test_set_yields_to_cli_pinned_var(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: Top
    set:
    - foo.sim: mti
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ foo.sim }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys,
                        param_overrides={"foo.sim": "xsm"})
    # CLI wins over set:: the -D value resolves, not the set: value.
    assert "SIM=xsm" in out
    assert "SIM=mti" not in out


# matrix: per-cell rebind via set: referencing the matrix variable.
def test_matrix_set_sweep(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: none
  tasks:
  - name: RunAll
    strategy:
      matrix:
        sim: ['vlt', 'mti']
    set:
    - foo.sim: "${{ matrix.sim }}"
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ foo.sim }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.RunAll", capsys)
    assert "SIM=vlt" in out
    assert "SIM=mti" in out
    assert "SIM=none" not in out


# f. bare name at top level with no matcher -> info marker, no rebind.
def test_bare_toplevel_info_marker(tmpdir, capsys):
    flow = '''
package:
  name: foo
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: Top
    set:
    - sim: mti
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ foo.sim }}"
'''
    _, _, out, collector = _run(tmpdir, flow, "foo.Top", capsys)
    # bare 'sim' did not rebind foo.sim -> default still resolves
    assert "SIM=vlt" in out
    infos = [m for m in collector.markers
             if "info" in str(m.severity).lower() and "set:" in m.msg and "sim" in m.msg]
    assert len(infos) >= 1
