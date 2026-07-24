"""
Integration regression tests for typed parameter expansion through compound
boundaries (docs/proposals/typed_param_expansion.md §7).

These drive the real TaskGraphBuilder/TaskSetRunner and assert on the resolved
FileSet, covering the three historical failure modes plus the string-splits and
partial-interpolation backward-compat guards.
"""
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.param_types import ParamTypeError


def _run(tmpdir, flow_dv, taskname):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode(taskname)
    out = asyncio.run(runner.run(task))
    return runner, out


def _mkfiles(tmpdir, *names):
    for n in names:
        with open(os.path.join(tmpdir, n), "w") as f:
            f.write("// %s\n" % n)


# 1. list through compound, whole-value (Mode A)
def test_list_through_compound_whole_value(tmpdir):
    _mkfiles(tmpdir, "a.sv", "b.sv")
    flow = '''
package:
  name: p1
  tasks:
  - name: fset-of
    with:
      names:
        type: list
    tasks:
    - name: fs
      uses: std.FileSet
      with:
        type: systemVerilogSource
        base: "%s"
        include: "${{ names }}"
  - name: top
    uses: fset-of
    with:
      names: [a.sv, b.sv]
''' % str(tmpdir)
    runner, out = _run(tmpdir, flow, "p1.top")
    assert runner.status == 0
    files = sorted(f for fs in out.output for f in fs.files)
    assert files == ["a.sv", "b.sv"]


# 2. compound reused twice with different list values (Mode B)
def test_compound_reused_no_cross_contamination(tmpdir):
    _mkfiles(tmpdir, "a.sv", "b.sv")
    flow = '''
package:
  name: p2
  tasks:
  - name: fset-of
    with:
      names:
        type: list
    tasks:
    - name: fs
      uses: std.FileSet
      with:
        type: systemVerilogSource
        base: "%s"
        include: "${{ names }}"
  - name: ta
    uses: fset-of
    with:
      names: [a.sv]
  - name: tb
    uses: fset-of
    with:
      names: [b.sv]
''' % str(tmpdir)
    runner_a, out_a = _run(tmpdir, flow, "p2.ta")
    assert runner_a.status == 0
    assert sorted(f for fs in out_a.output for f in fs.files) == ["a.sv"]

    runner_b, out_b = _run(tmpdir, flow, "p2.tb")
    assert runner_b.status == 0
    assert sorted(f for fs in out_b.output for f in fs.files) == ["b.sv"]


# 3. bare override, type inherited across the seam (Mode C: no "Expected none")
def test_bare_override_type_inherited(tmpdir):
    _mkfiles(tmpdir, "a.sv", "b.sv")
    flow = '''
package:
  name: p3
  tasks:
  - name: files
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "%s"
      include: [a.sv]
  - name: files2
    uses: p3.files
    with:
      include: [a.sv, b.sv]
''' % str(tmpdir)
    runner, out = _run(tmpdir, flow, "p3.files2")
    assert runner.status == 0
    assert sorted(f for fs in out.output for f in fs.files) == ["a.sv", "b.sv"]


# 4. string into list passes through & is split downstream (no scalar->list wrap)
def test_string_into_list_splits(tmpdir):
    _mkfiles(tmpdir, "file2.sv")
    flow = '''
package:
  name: p4
  tasks:
  - name: files
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "%s"
      include: "*.sv"
      attributes: "attr1=val1 attr2=val2 attr3"
''' % str(tmpdir)
    runner, out = _run(tmpdir, flow, "p4.files")
    assert runner.status == 0
    fs = out.output[0]
    assert len(fs.attributes) == 3
    assert "attr1=val1" in fs.attributes and "attr3" in fs.attributes


# 5. container into scalar slot is a located ParamTypeError at build time
def test_container_into_scalar_is_located_error(tmpdir):
    flow = '''
package:
  name: p5
  tasks:
  - name: t
    with:
      n:
        type: int
    tasks:
    - name: m
      uses: std.Message
      with:
        msg: "n=${{ n }}"
  - name: bad
    uses: p5.t
    with:
      n: [1, 2]
'''
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    with pytest.raises(ParamTypeError) as ei:
        builder.mkTaskNode("p5.bad")
    # located at the offending task/param
    assert "bad" in str(ei.value) and "n" in str(ei.value)


# 6. partial interpolation still stringifies into a str dst (backward-compat)
def test_partial_interpolation_stringifies(tmpdir, capsys):
    flow = '''
package:
  name: p6
  tasks:
  - name: say
    uses: std.Message
    with:
      msg: "pre_${{ 'X' }}_post"
'''
    runner, out = _run(tmpdir, flow, "p6.say")
    assert runner.status == 0
    captured = capsys.readouterr()
    assert "pre_X_post" in captured.out
