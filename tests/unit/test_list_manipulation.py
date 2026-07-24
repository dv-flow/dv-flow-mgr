"""Characterization + semantic tests for list-parameter manipulation
(`value` / `append` / `prepend`, plus `path-append` / `path-prepend`).

See docs/proposals/list_manipulation.md. These start as a mix of asserts (for
sites that already work) and xfails (for the three sites the proposal fixes);
the xfails flip to passes as P1/P2 land, which is the DoD signal.
"""
import os
import tempfile
import pytest
from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


def _build(flow_text, tmp_path):
    (tmp_path / "flow.dv").write_text(flow_text)
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    return TaskGraphBuilder(root_pkg=pkg,
                            rundir=str(tmp_path / "rundir"), loader=loader)


def _find_subtask(node, leaf_name):
    """Depth-first search for a subtask whose name ends with `leaf_name`."""
    for t in getattr(node, "tasks", []) or []:
        if t is node:
            continue
        if getattr(t, "name", "").endswith(leaf_name):
            return t
        found = _find_subtask(t, leaf_name)
        if found is not None:
            return found
    return None


_BASE = """\
package:
  name: pkg
  with:
    tn: { type: str, value: "wb_dma_arb_test" }
  tasks:
  - name: base
    uses: std.Message
    with:
      plusargs: { type: list, value: ["BASE=1"] }
      incs:     { type: list, value: ["/a"] }
      msg: "x"
"""


# ---- Sites that already work (regression guards) -------------------------

def test_uses_chain_append(tmp_path):
    b = _build(_BASE + """\
  - name: t
    uses: base
    with:
      plusargs: { append: ["CMP_BY_CHANNEL"] }
""", tmp_path)
    n = b.mkTaskNode("pkg.t")
    assert n.params.plusargs == ["BASE=1", "CMP_BY_CHANNEL"]


def test_uses_chain_prepend(tmp_path):
    b = _build(_BASE + """\
  - name: t
    uses: base
    with:
      plusargs: { prepend: ["FIRST=0"] }
""", tmp_path)
    n = b.mkTaskNode("pkg.t")
    assert n.params.plusargs == ["FIRST=0", "BASE=1"]


def test_prepend_operand_expression(tmp_path):
    # A ${{ }} inside a prepend operand is evaluated in scope.
    b = _build(_BASE + """\
  - name: t
    uses: base
    with:
      plusargs: { prepend: ["UVM_TESTNAME=${{ tn }}"] }
""", tmp_path)
    n = b.mkTaskNode("pkg.t")
    assert n.params.plusargs == ["UVM_TESTNAME=wb_dma_arb_test", "BASE=1"]


def test_matrix_body_append(tmp_path):
    b = _build(_BASE + """\
  - name: mtx
    strategy:
      matrix:
        extra: [ "CMP_BY_CHANNEL", "NO_CMP" ]
    body:
    - name: "cell_${{ this.extra }}"
      uses: base
      with:
        plusargs: { append: ["${{ this.extra }}"] }
""", tmp_path)
    n = b.mkTaskNode("pkg.mtx")
    c0 = _find_subtask(n, "cell_CMP_BY_CHANNEL_0")
    c1 = _find_subtask(n, "cell_NO_CMP_1")
    assert c0.params.plusargs == ["BASE=1", "CMP_BY_CHANNEL"]
    assert c1.params.plusargs == ["BASE=1", "NO_CMP"]


# ---- Sites the proposal fixes (xfail today -> pass when fixed) ------------

def test_path_append(tmp_path):
    """P1: path-append must join onto a path-like list param, not leak the
    raw ParamDef."""
    b = _build(_BASE + """\
  - name: t
    uses: base
    with:
      incs: { path-append: "/b" }
""", tmp_path)
    n = b.mkTaskNode("pkg.t")
    assert n.params.incs == ["/a", "/b"]


def test_matrix_body_listop_threading_splice(tmp_path):
    """P2 (the real SimSuite path): a matrix `body` cell composes plusargs
    (`prepend` a per-case testname onto the case's extra list) and the result
    threads FLAT through the compound boundary into the run subtask -- no
    nesting. This is the driving case; the splice fix in param_builder makes it
    work.
    """
    b = _build("""\
package:
  name: pkg
  tasks:
  - name: leaf
    uses: std.Message
    with: { plusargs: {type: list, value: []}, msg: "x" }
  - name: SimCase
    with:
      plusargs: {type: list, value: []}
    tasks:
    - name: run
      uses: leaf
      with:
        plusargs: "${{ plusargs }}"
  - name: SimSuite
    strategy:
      matrix:
        case:
        - { name: arb,   test: wb_dma_arb_test,   extra: [CMP_BY_CHANNEL] }
        - { name: arbeq, test: wb_dma_arb_eq_test, extra: [CMP_BY_CHANNEL, CMP_NO_ORDER] }
    body:
    - name: "${{ this.case.name }}"
      uses: SimCase
      with:
        plusargs:
          prepend: ["UVM_TESTNAME=${{ this.case.test }}"]
          value: "${{ this.case.extra }}"
""", tmp_path)
    n = b.mkTaskNode("pkg.SimSuite")
    runs = []
    def collect(node):
        for t in getattr(node, "tasks", []) or []:
            if t is node:
                continue
            if getattr(t, "name", "").endswith(".run"):
                runs.append(t.params.plusargs)
            collect(t)
    collect(n)
    assert ["UVM_TESTNAME=wb_dma_arb_test", "CMP_BY_CHANNEL"] in runs
    assert ["UVM_TESTNAME=wb_dma_arb_eq_test", "CMP_BY_CHANNEL", "CMP_NO_ORDER"] in runs


@pytest.mark.xfail(reason="Separate deeper bug (not needed by SimSuite): a "
                          "compound-subtask `override:` across a `uses` boundary "
                          "builds pkg.<Derived>.run but the adopted node keeps the "
                          "pkg.<Base>.run name, so the by-name replacement "
                          "(task_graph_builder.py:2007) never fires and the "
                          "override's list-op is dropped. SimSuite composes in the "
                          "matrix body instead (test above).",
                   strict=True)
def test_compound_subtask_override_prepend(tmp_path):
    """A compound-subtask `override:` list-op composing with the threaded base.
    Documented-broken; the matrix-body path (above) is the supported one."""
    b = _build("""\
package:
  name: pkg
  tasks:
  - name: leaf
    uses: std.Message
    with:
      plusargs: { type: list, value: [] }
      msg: "x"
  - name: SimCase
    with:
      plusargs: { type: list, value: [] }
    tasks:
    - name: run
      uses: leaf
      with:
        plusargs: "${{ plusargs }}"
  - name: SimUVMCase
    uses: SimCase
    with:
      UVM_TESTNAME: { type: str, value: "" }
    tasks:
    - override: run
      with:
        plusargs: { prepend: ["UVM_TESTNAME=${{ UVM_TESTNAME }}"] }
  - name: case_arb
    uses: SimUVMCase
    with:
      UVM_TESTNAME: "wb_dma_arb_test"
      plusargs: ["CMP_BY_CHANNEL"]
""", tmp_path)
    n = b.mkTaskNode("pkg.case_arb")
    run = _find_subtask(n, ".run")
    assert run is not None
    assert run.params.plusargs == ["UVM_TESTNAME=wb_dma_arb_test", "CMP_BY_CHANNEL"]


@pytest.mark.xfail(reason="P2/later: programmatic mkTaskNode does not interpret "
                          "list-op dicts (YAML is the primary surface)",
                   strict=True)
def test_programmatic_mktasknode_append(tmp_path):
    b = _build(_BASE, tmp_path)
    n = b.mkTaskNode("pkg.base", name="prog", plusargs={"append": ["Z=9"]})
    assert n.params.plusargs == ["BASE=1", "Z=9"]
