#****************************************************************************
#* test_uses_chain.py
#*
#* Phase 3 of the `set:` scoped-overrides feature: each elaborated node exposes
#* the ordered list of task TYPE names along its `uses` chain (most-derived
#* first), the input the `set:` `uses:` matcher needs.
#* See docs/proposals/set_overrides_impl_plan.md Phase 3.
#****************************************************************************
import os
from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from .marker_collector import MarkerCollector


def _build(tmpdir, flow_dv, taskname):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    collector = MarkerCollector()
    pkg_def = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, marker_l=collector)
    return builder, builder.mkTaskNode(taskname)


def _find(node, leafname):
    """Depth-first search for a descendant node whose name contains leafname
    (matrix cells carry a combination suffix, so match on substring)."""
    if leafname in node.name:
        return node
    for t in getattr(node, "tasks", []):
        found = _find(t, leafname)
        if found is not None:
            return found
    return None


def test_chain_includes_derived_and_base():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        flow = '''
package:
  name: foo
  tasks:
  - name: A
    uses: std.Message
    with:
      msg: "a"
  - name: B
    uses: A
'''
        _, node = _build(tmpdir, flow, "foo.B")
        # B derives from A which derives from std.Message.
        assert "foo.B" in node.uses_chain
        assert "foo.A" in node.uses_chain
        assert "std.Message" in node.uses_chain
        # Most-derived first.
        assert node.uses_chain.index("foo.B") < node.uses_chain.index("foo.A")
        assert node.uses_chain.index("foo.A") < node.uses_chain.index("std.Message")


def test_direct_concrete_use():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        flow = '''
package:
  name: foo
  tasks:
  - name: R
    uses: std.Message
    with:
      msg: "r"
'''
        _, node = _build(tmpdir, flow, "foo.R")
        assert node.uses_chain[0] == "foo.R"
        assert "std.Message" in node.uses_chain


def test_chain_exposed_under_compound_body():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        flow = '''
package:
  name: foo
  tasks:
  - name: Leaf
    uses: std.Message
    with:
      msg: "x"
  - name: Top
    body:
    - name: Child
      uses: Leaf
'''
        _, node = _build(tmpdir, flow, "foo.Top")
        child = _find(node, "Child")
        assert child is not None
        assert "foo.Leaf" in child.uses_chain
        assert "std.Message" in child.uses_chain


def test_chain_survives_matrix_expansion():
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        flow = '''
package:
  name: foo
  tasks:
  - name: Leaf
    uses: std.Message
    with:
      msg: "x"
  - name: RunAll
    strategy:
      matrix:
        k: ['a', 'b']
    body:
    - name: Cell
      uses: Leaf
'''
        _, node = _build(tmpdir, flow, "foo.RunAll")
        cell = _find(node, "Cell")
        assert cell is not None
        assert "foo.Leaf" in cell.uses_chain
        assert "std.Message" in cell.uses_chain
