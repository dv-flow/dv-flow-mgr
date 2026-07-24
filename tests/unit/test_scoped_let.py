#****************************************************************************
#* test_scoped_let.py
#*
#* Integration tests for the `let:` scoped-variable block and its interaction
#* with resolve(). See docs/proposals/scoped_variables_impl_plan.md §A2.4.
#*
#* These drive the real TaskGraphBuilder/TaskSetRunner. Body tasks surface the
#* resolved value through std.Message so it appears on stdout (captured by
#* capsys), mirroring tests/unit/test_strategy_matrix.py.
#****************************************************************************
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from .marker_collector import MarkerCollector


def _run(tmpdir, flow_dv, taskname, capsys=None):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode(taskname)
    out = asyncio.run(runner.run(task))
    captured = capsys.readouterr().out if capsys is not None else ""
    return runner, out, captured, collector


# 1. Compound with let; body task resolves the scoped value.
def test_compound_let_seen_by_body(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    let:
      sim: vlt
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ resolve('sim', 'none') }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "SIM=vlt" in out


# 2. Motivating end-to-end: matrix sweep pushed into the subtree via let.
def test_matrix_let_sweep(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: RunAll
    strategy:
      matrix:
        sim: ['vlt', 'mti']
    let:
      sim: "${{ matrix.sim }}"
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ resolve('sim', 'none') }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.RunAll", capsys)
    assert "SIM=vlt" in out
    assert "SIM=mti" in out
    # 8. Sibling isolation: no cell leaks 'none' (i.e. resolve always found a binding)
    assert "SIM=none" not in out


# 3. Nested let: inner subtree shadows, outer sibling keeps the outer value.
def test_nested_let_shadowing(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    let:
      opt: "-O1"
    body:
    - name: OuterRun
      uses: std.Message
      with:
        msg: "OUTER=${{ resolve('opt', 'none') }}"
    - name: Inner
      let:
        opt: "-O3"
      body:
      - name: InnerRun
        uses: std.Message
        with:
          msg: "INNER=${{ resolve('opt', 'none') }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "OUTER=-O1" in out
    assert "INNER=-O3" in out


# 4. A let entry referencing an earlier entry in the same block by bare name.
def test_let_entry_references_earlier(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    let:
      base: "x"
      derived: "${{ base }}-y"
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "D=${{ resolve('derived', 'none') }}"
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    assert "D=x-y" in out


# 6. Explicit with: on an instance beats an ancestor let (precedence invariant #4).
def test_explicit_with_beats_let(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: SimEcho
    uses: std.Message
    with:
      sim:
        type: str
        value: "${{ resolve('sim', 'dflt') }}"
      msg: "SIM=${{ sim }}"
  - name: Top
    let:
      sim: fromlet
    body:
    - name: R1
      uses: SimEcho
    - name: R2
      uses: SimEcho
      with:
        sim: explicit
'''
    _, _, out, _ = _run(tmpdir, flow, "foo.Top", capsys)
    # R1 has no explicit sim -> picks up the let binding
    assert "SIM=fromlet" in out
    # R2 explicitly sets sim -> the let binding is ignored
    assert "SIM=explicit" in out


# 7. let on a leaf task emits a build warning and has no effect.
def test_let_on_leaf_warns(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Leaf
    uses: std.Message
    let:
      sim: vlt
    with:
      msg: "hello"
'''
    _, _, out, collector = _run(tmpdir, flow, "foo.Leaf", capsys)
    warnings = [m for m in collector.markers
                if "warning" in str(m.severity).lower() and "let" in m.msg]
    assert len(warnings) >= 1
    assert "hello" in out


# 9. A bare ${{ name }} does NOT read a let binding (resolve() is the only reader).
def test_bare_ref_does_not_see_let(tmpdir, capsys):
    flow = '''
package:
  name: foo
  tasks:
  - name: Top
    let:
      sim: vlt
    body:
    - name: Run
      uses: std.Message
      with:
        msg: "SIM=${{ sim }}"
'''
    # 'sim' is not a normal variable, only a scoped (let) binding; a bare ref
    # must not resolve it. The reference is therefore undefined and raises,
    # proving the let binding did not leak into normal variable resolution.
    with pytest.raises(Exception) as ei:
        _run(tmpdir, flow, "foo.Top", capsys)
    assert "sim" in str(ei.value)
