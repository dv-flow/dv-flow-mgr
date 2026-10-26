"""A task that `uses:` a base with `strategy: matrix:` + `body:` inherits both.

Covers the inherited-matrix proposal: one node per cell named
`<task>.<cell>`, body expressions seeing the inheriting task's parameters,
multi-level inheritance, and the override rules.
"""
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader


# Repro B: the base declares the matrix and body; each test only `uses:` it.
_REPRO_B = """\
package:
  name: pb
  tasks:
  - { name: img-amd, uses: std.Message, with: { msg: "build amd image" } }
  - { name: img-px,  uses: std.Message, with: { msg: "build px image" } }
  - name: case
    with:
      testname: { type: str, value: "" }
    strategy:
      matrix:
        image: [amd, px]
    body:
    - name: "${{ this.image }}"
      uses: std.Message
      needs: ["img-${{ this.image }}"]
      with: { msg: "${{ testname }} on ${{ this.image }}" }
  - { name: bypass_initial,  uses: case, with: { testname: t_bypass } }
  - { name: encrypt_initial, uses: case, with: { testname: t_encrypt } }
  - { name: uvm-tests, uses: std.TestSuite, needs: [bypass_initial, encrypt_initial] }
  - root: tests
    uses: std.TestRunner
    needs: [uvm-tests]
    with: { view_axis: image }
  - root: tests-info
    uses: std.TestInfo
    with: { target: tests, view_axis: image }
"""

# Same base, but the body doesn't reference the base's parameters, so it
# expands today. Used for the override cases.
_PLAIN_BASE = """\
package:
  name: pb
  tasks:
  - { name: img-amd, uses: std.Message, with: { msg: "build amd image" } }
  - { name: img-px,  uses: std.Message, with: { msg: "build px image" } }
  - name: case
    strategy:
      matrix:
        image: [amd, px]
    body:
    - name: "${{ this.image }}"
      uses: std.Message
      needs: ["img-${{ this.image }}"]
      with: { msg: "base-body on ${{ this.image }}" }
%s
"""


def _builder(tmp_path, text):
    (tmp_path / "flow.dv").write_text(text)
    loader = PackageLoader()
    pkg = loader.load(str(tmp_path / "flow.dv"))
    return TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "rundir"),
                            loader=loader)


def _cells(node):
    """Leaf names of a compound's cell nodes (its `.in` node excluded)."""
    return sorted(
        t.name.rsplit(".", 1)[-1] for t in (getattr(node, "tasks", None) or [])
        if t is not node and not t.name.endswith(".in"))


def _cell_needs(node):
    """{cell leaf: [needed leaf names]} for each cell of a compound."""
    ret = {}
    for t in getattr(node, "tasks", None) or []:
        if t is node or t.name.endswith(".in"):
            continue
        ret[t.name.rsplit(".", 1)[-1]] = sorted(
            n.name.rsplit(".", 1)[-1] for n, _ in t.needs
            if not n.name.endswith(".in"))
    return ret


def _run(builder, tmp_path, capsys, *tasks):
    runner = TaskSetRunner(rundir=str(tmp_path / "rundir"))
    nodes = [builder.mkTaskNode(t) for t in tasks]
    asyncio.run(runner.run(nodes if len(nodes) > 1 else nodes[0]))
    assert runner.status == 0
    return capsys.readouterr().out


def test_base_matrix_expands(tmp_path):
    """Sanity: the base itself expands one cell per image, each needing its image."""
    b = _builder(tmp_path, _PLAIN_BASE % "")
    n = b.mkTaskNode("pb.case")
    assert _cells(n) == ["amd_0", "px_1"]
    assert _cell_needs(n) == {"amd_0": ["img-amd"], "px_1": ["img-px"]}


@pytest.mark.xfail(strict=True, reason="item 2: strategy not inherited via uses")
def test_repro_b_loads_and_expands(tmp_path):
    """Plan §2 repro B: bypass_initial expands into its own amd/px cells."""
    b = _builder(tmp_path, _REPRO_B)
    n = b.mkTaskNode("pb.bypass_initial")
    assert _cells(n) == ["amd_0", "px_1"]
    assert all(t.name.startswith("pb.bypass_initial.")
               for t in n.tasks if t is not n)
    assert _cell_needs(n) == {"amd_0": ["img-amd"], "px_1": ["img-px"]}


@pytest.mark.xfail(strict=True, reason="item 2: strategy not inherited via uses")
def test_inherit_one_node_per_cell(tmp_path, capsys):
    """§5 case 1: no own strategy -> one node per inherited cell."""
    b = _builder(tmp_path, _PLAIN_BASE % "  - { name: t1, uses: case }")
    n = b.mkTaskNode("pb.t1")
    assert _cells(n) == ["amd_0", "px_1"]
    out = _run(b, tmp_path, capsys, "pb.t1")
    assert "base-body on amd" in out
    assert "base-body on px" in out


@pytest.mark.xfail(strict=True, reason="item 2: body can't see task params")
def test_inherit_body_sees_task_params(tmp_path, capsys):
    """§5 case 2: two tests with different `testname` get different results."""
    b = _builder(tmp_path, _REPRO_B)
    out = _run(b, tmp_path, capsys, "pb.bypass_initial", "pb.encrypt_initial")
    for t in ("t_bypass", "t_encrypt"):
        for img in ("amd", "px"):
            assert "%s on %s" % (t, img) in out


@pytest.mark.xfail(strict=True, reason="item 2: multi-level inheritance")
def test_inherit_multi_level(tmp_path, capsys):
    """§5 case 4: base -> mid (adds a default) -> test still gets the matrix."""
    b = _builder(tmp_path, _REPRO_B + """\
  - { name: mid, uses: case, with: { testname: t_mid } }
  - { name: leaf, uses: mid }
""")
    n = b.mkTaskNode("pb.leaf")
    assert _cells(n) == ["amd_0", "px_1"]
    out = _run(b, tmp_path, capsys, "pb.leaf")
    assert "t_mid on amd" in out
    assert "t_mid on px" in out


@pytest.mark.xfail(strict=True, reason="item 3: own strategy keeps base body")
def test_override_strategy_without_body(tmp_path, capsys):
    """§5 case 5a: own `strategy:` w/o `body:` runs the base body on the new matrix."""
    b = _builder(tmp_path, _PLAIN_BASE % """\
  - name: px_only
    uses: case
    strategy:
      matrix:
        image: [px]
""")
    n = b.mkTaskNode("pb.px_only")
    assert _cells(n) == ["px_0"]
    assert _cell_needs(n) == {"px_0": ["img-px"]}
    out = _run(b, tmp_path, capsys, "pb.px_only")
    assert "base-body on px" in out
    assert "build amd image" not in out


def test_override_strategy_and_body(tmp_path, capsys):
    """§5 case 5b: own `strategy:` and `body:` inherits nothing from the base."""
    b = _builder(tmp_path, _PLAIN_BASE % """\
  - name: own
    uses: case
    strategy:
      matrix:
        image: [px]
    body:
    - name: "${{ this.image }}"
      uses: std.Message
      with: { msg: "own-body on ${{ this.image }}" }
""")
    n = b.mkTaskNode("pb.own")
    assert _cells(n) == ["px_0"]
    assert _cell_needs(n) == {"px_0": []}
    out = _run(b, tmp_path, capsys, "pb.own")
    assert "own-body on px" in out
    assert "base-body" not in out
    assert "build" not in out
