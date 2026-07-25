#****************************************************************************
#* test_test_info.py
#*
#* `std.TestInfo`: introspection of a test root's inventory.
#*
#* The contract being pinned:
#*   * the inventory is read off the TARGET root's declared needs, so it cannot
#*     drift from what `tests` would actually run;
#*   * introspection BUILDS NOTHING -- no image, no case;
#*   * what it reports and what `--tests`/`--views` accept are the same set
#*     (both go through test_select.plan_need).
#****************************************************************************
import json
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.std.test_info import scope_rows
from .marker_collector import MarkerCollector


FLOW = """\
package:
    name: p
    with:
      views_var: { type: list, value: [tlm, rtl] }
    tasks:
    - { name: img, shell: bash, run: 'echo BUILT-IMAGE' }
    - name: suite
      strategy:
        matrix:
          view: "${{ views_var }}"
          case:
          - { name: arb, testname: t_arb }
          - { name: err, testname: t_err }
      body:
      - name: "${{ this.view }}-${{ this.case.name }}"
        shell: bash
        needs: [img]
        run: 'echo RAN-${{ this.view }}/${{ this.case.name }}'
    - name: solo
      shell: bash
      tags: [ { std.Test: { case: smoke } } ]
      run: 'echo RAN-solo'
    - name: helper
      shell: bash
      run: 'echo RAN-helper'
    - root: tests
      uses: std.TestRunner
      needs: [suite, solo, helper]
    - root: tests-info
      uses: std.TestInfo
      with:
        target: tests
"""


@pytest.fixture
def proj(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(FLOW)
    return str(tmpdir)


@pytest.fixture
def loaded(proj):
    collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[collector])
    p = loader.load(os.path.join(proj, "flow.dv"))
    assert [m.msg for m in collector.markers] == []
    return loader, p


def _inventory(loaded, proj, **overrides):
    loader, pkg = loaded
    builder = TaskGraphBuilder(
        root_pkg=pkg, loader=loader,
        rundir=os.path.join(proj, "rundir"),
        task_param_overrides={"p.tests-info": overrides} if overrides else {})
    node = builder.mkTaskNode("p.tests-info")
    return node, json.loads(node.params.inventory)


# --------------------------------------------------------------- unit level

def test_cases_come_from_both_a_suite_and_a_tagged_case(loaded, proj):
    _, inv = _inventory(loaded, proj)
    assert sorted(inv["cases"]) == ["arb", "err", "smoke"]


def test_the_target_is_reported(loaded, proj):
    _, inv = _inventory(loaded, proj)
    assert inv["target"] == "p.tests"


def test_an_expression_view_axis_is_resolved(loaded, proj):
    """`view: "${{ views_var }}"` must be reported by its members, not left
    open -- an inventory that cannot name the views is not an inventory."""
    _, inv = _inventory(loaded, proj)
    assert inv["views"] == ["tlm", "rtl"]
    assert inv["views_open"] is False


def test_suites_are_reported_individually(loaded, proj):
    """Per-suite rows are what tell a user that a case exists on only some
    views (the HS-only pattern) -- the union alone hides it."""
    _, inv = _inventory(loaded, proj)
    by_name = {s["name"]: s for s in inv["suites"]}
    assert sorted(by_name["p.suite"]["cases"]) == ["arb", "err"]
    assert by_name["p.solo"]["cases"] == ["smoke"]


def test_a_non_test_need_is_reported_separately(loaded, proj):
    _, inv = _inventory(loaded, proj)
    assert inv["other"] == ["p.helper"]
    assert all(s["name"] != "p.helper" for s in inv["suites"])


def test_nothing_upstream_is_built(loaded, proj):
    """The point of the task: no image, no case, no helper in the subgraph."""
    node, _ = _inventory(loaded, proj)
    assert node.needs == []
    assert not (getattr(node, "tasks", None) or [])


# ------------------------------------------------------------- hierarchy

def _s(name):
    scope, _, short = name.rpartition(".")
    return {"name": name, "scope": scope, "short": short, "cases": [], "views": []}


def test_siblings_share_one_scope_header():
    """The point of grouping: the shared prefix is written once, and what is a
    sibling of what is visible without reading every row to the end."""
    rows = scope_rows([_s("p.uvm.universal"), _s("p.uvm.hs-only")])
    assert [(d, l) for d, l, _ in rows] == [
        (0, "p.uvm"), (1, "universal"), (1, "hs-only")]


def test_a_single_child_chain_is_collapsed():
    """`p.uvm` as one label, not `p` > `uvm`: an intermediate scope with
    nothing else in it costs a line and a level of indent to say nothing."""
    rows = scope_rows([_s("p.uvm.universal")])
    assert [l for _, l, _ in rows] == ["p.uvm", "universal"]


def test_separate_scopes_get_separate_headers():
    rows = scope_rows([_s("p.uvm.universal"), _s("p.formal.bmc")])
    assert [(d, l) for d, l, _ in rows] == [
        (0, "p"), (1, "uvm"), (2, "universal"), (1, "formal"), (2, "bmc")]


def test_a_suite_beside_a_nested_scope_keeps_its_own_depth():
    rows = scope_rows([_s("p.smoke"), _s("p.uvm.universal")])
    assert [(d, l) for d, l, _ in rows] == [
        (0, "p"), (1, "smoke"), (1, "uvm"), (2, "universal")]


def test_declaration_order_is_preserved():
    rows = scope_rows([_s("p.b"), _s("p.a")])
    assert [l for _, l, s in rows if s is not None] == ["b", "a"]


def test_entries_carry_scope_and_short_name(loaded, proj):
    _, inv = _inventory(loaded, proj)
    suite = [s for s in inv["suites"] if s["name"] == "p.suite"][0]
    assert (suite["scope"], suite["short"]) == ("p", "suite")


def test_an_unknown_target_is_an_error(loaded, proj):
    """A typo'd target must not read as "this project has no tests"."""
    with pytest.raises(Exception) as exc:
        _inventory(loaded, proj, target="nosuch")
    assert "nosuch" in str(exc.value)


# ------------------------------------------------------------ end to end

def test_run_reports_and_runs_nothing(proj):
    proc = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run", "tests-info"],
        cwd=proj, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    with open(os.path.join(proj, "rundir", "p.tests-info",
                           "tests-info.json")) as f:
        inv = json.load(f)
    assert sorted(inv["cases"]) == ["arb", "err", "smoke"]

    # Nothing else ran: the only rundir entry is the info task's own.
    ran = []
    for root, _, files in os.walk(os.path.join(proj, "rundir")):
        for fn in files:
            if fn.endswith(".log"):
                with open(os.path.join(root, fn)) as f:
                    ran.extend(l.strip() for l in f
                               if l.startswith(("RAN-", "BUILT-")))
    assert ran == []
