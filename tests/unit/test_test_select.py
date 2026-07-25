#****************************************************************************
#* test_test_select.py
#*
#* `std.TestRunner`: graph-build selection over a test root's needs.
#*
#* The contract being pinned:
#*   * a deselected test is NEVER BUILT -- not built-and-skipped, which is what
#*     `iff:` would give. Anything reachable only through the pruned edge drops
#*     out too, so deselecting a view also skips building that view's image.
#*   * needs that are not tests are ALWAYS kept -- selecting tests must never
#*     break the build.
#*   * a selection that would silently under-run is an ERROR. Every failure mode
#*     here otherwise ends in a green run that tested less than was asked for.
#****************************************************************************
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.std.test_select import (
    Selection, SelectionError, plan_need, check_selection)
# Imported under an alias: pytest would otherwise collect `test_tag` itself as
# a test case and fail it for requesting a `task` "fixture".
from dv_flow.mgr.std.test_select import test_tag as read_test_tag
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
          view: [tlm, rtl]
          case:
          - { name: arb,    testname: t_arb }
          - { name: arb_eq, testname: t_arb_eq }
          - { name: err,    testname: t_err }
      body:
      - name: "${{ this.view }}-${{ this.case.name }}"
        shell: bash
        needs: [img]
        with:
          tn: { type: str, value: "${{ this.view }}/${{ this.case.name }}" }
        run: 'echo RAN-${{ tn }}'
    - name: solo
      shell: bash
      tags: [ { std.Test: { case: smoke } } ]
      run: 'echo RAN-solo'
    - name: helper
      shell: bash
      run: 'echo RAN-helper'
    - name: expr_suite
      iff: "${{ views_var | length > 0 }}"
      strategy:
        matrix:
          view: "${{ views_var }}"
          case:
          - { name: exprcase }
      body:
      - name: "${{ this.view }}-${{ this.case.name }}"
        shell: bash
        with:
          tn: { type: str, value: "${{ this.view }}/${{ this.case.name }}" }
        run: 'echo RAN-${{ tn }}'
    - root: tests
      uses: std.TestRunner
      needs: [suite, solo, helper]
"""


@pytest.fixture
def loaded(tmpdir):
    """(loader, pkg). The loader is required: `std.TestRunner` lives in the
    built-in `std` package, which the builder resolves through the loader
    rather than the root package's own task map."""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(FLOW)
    collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[collector])
    p = loader.load(os.path.join(str(tmpdir), "flow.dv"))
    assert [m.msg for m in collector.markers] == []
    return loader, p


@pytest.fixture
def pkg(loaded):
    return loaded[1]


def _needs(loaded, tmpdir, **overrides):
    """Build `tests` and report the leaf names of everything in its subgraph."""
    loader, pkg = loaded
    builder = TaskGraphBuilder(
        root_pkg=pkg, loader=loader,
        rundir=os.path.join(str(tmpdir), "rundir"),
        task_param_overrides={"p.tests": overrides} if overrides else {})
    node = builder.mkTaskNode("p.tests")

    seen = set()
    def walk(n):
        if n.name in seen:
            return
        seen.add(n.name)
        for sub in getattr(n, "tasks", None) or []:
            walk(sub)
        for need, _ in n.needs:
            walk(need)
    walk(node)
    return seen


def _cases(names):
    """Just the generated matrix cells, as `view-case` labels. A cell's node
    name carries the per-axis indices (`rtl-arb_0_0`); strip them."""
    import re
    return sorted(re.sub(r"(_\d+)+$", "", n.rsplit(".", 1)[-1])
                  for n in names if ".suite." in n and not n.endswith(".in"))


# --------------------------------------------------------------- unit level

def test_tag_is_read_off_a_task(pkg):
    assert read_test_tag(pkg.task_m["p.solo"]).case == "smoke"
    assert read_test_tag(pkg.task_m["p.helper"]) is None


def test_an_untagged_non_matrix_need_is_not_a_test(pkg):
    plan = plan_need(pkg.task_m["p.helper"], Selection(tests=["arb"]))
    assert plan.is_test is False
    assert plan.keep is True


def test_a_matrix_offers_its_cases_and_views(pkg):
    plan = plan_need(pkg.task_m["p.suite"], Selection())
    assert plan.is_test is True
    assert plan.cases == ["arb", "arb_eq", "err"]
    assert plan.views == ["tlm", "rtl"]


def test_a_fully_deselected_suite_is_dropped(pkg):
    """An empty matrix would build a suite that runs nothing, which reads as
    success; drop the whole need instead."""
    plan = plan_need(pkg.task_m["p.suite"], Selection(tests=["smoke"]))
    assert plan.keep is False


def test_no_selection_builds_no_variant(pkg):
    """Selecting everything must be the same graph as selecting nothing --
    otherwise the default path carries the cost of the feature."""
    assert plan_need(pkg.task_m["p.suite"], Selection()).variant is None
    assert plan_need(
        pkg.task_m["p.suite"],
        Selection(tests=["arb", "arb_eq", "err"])).variant is None


def test_an_expression_view_axis_is_resolved_when_it_can_be(pkg):
    """A real project writes the view axis as a variable
    (`image: "${{ images }}"`). Resolving it is what lets a mistyped `--views`
    be reported here, instead of being bound literally and failing much later
    with an error naming neither the view nor the flag that set it."""
    suite = pkg.task_m["p.expr_suite"]
    plan = plan_need(suite, Selection(), expand=lambda e: ["tlm", "rtl"])
    assert plan.views == ["tlm", "rtl"]
    assert plan.views_open is False


def test_an_unresolvable_view_axis_stays_open(pkg):
    """When the axis cannot be resolved its members are genuinely unknown, so
    validation must stay silent rather than reject a working flow."""
    suite = pkg.task_m["p.expr_suite"]
    plan = plan_need(suite, Selection(), expand=lambda e: e)
    assert plan.views_open is True


def test_an_open_view_axis_suppresses_view_validation(pkg):
    """The false-positive guard: with one suite's views unknowable, an
    unmatched view cannot be claimed."""
    sel = Selection(views=["anything"])
    open_plan = plan_need(pkg.task_m["p.expr_suite"], sel, expand=lambda e: e)
    known_plan = plan_need(pkg.task_m["p.suite"], sel)
    check_selection(sel, [open_plan, known_plan])   # must not raise


# ------------------------------------------------------------- diagnostics

def test_unmatched_test_is_an_error(pkg):
    plans = [plan_need(t, Selection(tests=["nosuch"]))
             for t in (pkg.task_m["p.suite"], pkg.task_m["p.solo"])]
    with pytest.raises(SelectionError, match="no test matches 'nosuch'"):
        check_selection(Selection(tests=["nosuch"]), plans)


def test_the_error_lists_what_is_available(pkg):
    sel = Selection(tests=["nosuch"])
    plans = [plan_need(t, sel)
             for t in (pkg.task_m["p.suite"], pkg.task_m["p.solo"])]
    with pytest.raises(SelectionError, match="arb, arb_eq, err, smoke"):
        check_selection(sel, plans)


def test_unmatched_view_is_an_error(pkg):
    sel = Selection(views=["nosuch"])
    plans = [plan_need(pkg.task_m["p.suite"], sel)]
    with pytest.raises(SelectionError, match="no view matches"):
        check_selection(sel, plans)


def test_selecting_with_no_tests_present_is_an_error(pkg):
    sel = Selection(tests=["arb"])
    plans = [plan_need(pkg.task_m["p.helper"], sel)]
    with pytest.raises(SelectionError, match="none of this task's needs"):
        check_selection(sel, plans)


def test_no_selection_never_raises(pkg):
    check_selection(Selection(), [plan_need(pkg.task_m["p.helper"], Selection())])


# ------------------------------------------------------------- graph level

def test_everything_runs_by_default(loaded, tmpdir):
    names = _needs(loaded, tmpdir)
    assert _cases(names) == sorted([
        "tlm-arb", "tlm-arb_eq", "tlm-err", "rtl-arb", "rtl-arb_eq", "rtl-err"])
    assert any(n.endswith(".solo") for n in names)


def test_selecting_a_case_prunes_the_other_cells(loaded, tmpdir):
    names = _needs(loaded, tmpdir, tests="arb")
    assert _cases(names) == ["rtl-arb", "tlm-arb"]


def test_selecting_a_view_prunes_the_other_view(loaded, tmpdir):
    names = _needs(loaded, tmpdir, views="rtl")
    assert _cases(names) == ["rtl-arb", "rtl-arb_eq", "rtl-err"]


def test_case_and_view_together(loaded, tmpdir):
    names = _needs(loaded, tmpdir, tests="arb,err", views="rtl")
    assert _cases(names) == ["rtl-arb", "rtl-err"]


def test_a_non_test_need_is_always_kept(loaded, tmpdir):
    """`helper` is wired to `tests` but is not a test. Pruning it would break
    the build, so a selection must never touch it."""
    names = _needs(loaded, tmpdir, tests="arb")
    assert any(n.endswith(".helper") for n in names)


def test_selecting_the_tagged_case_drops_the_suite(loaded, tmpdir):
    names = _needs(loaded, tmpdir, tests="smoke")
    assert _cases(names) == []
    assert any(n.endswith(".solo") for n in names)


# ------------------------------------------------------------ end to end

def _dfm(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(cwd), capture_output=True, text=True)


def _ran(cwd):
    out = []
    rundir = os.path.join(str(cwd), "rundir")
    for root, _, files in os.walk(rundir):
        for fn in files:
            if fn.endswith(".log"):
                with open(os.path.join(root, fn)) as f:
                    out.extend(l.strip() for l in f
                               if l.startswith(("RAN-", "BUILT-")))
    return sorted(out)


@pytest.fixture
def proj(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(FLOW)
    return str(tmpdir)


def test_cli_selection(proj):
    proc = _dfm(proj, "run", "tests", "--tests", "arb", "--views", "rtl")
    assert proc.returncode == 0, proc.stderr
    assert _ran(proj) == ["BUILT-IMAGE", "RAN-helper", "RAN-rtl/arb"]


def test_comma_and_repeated_flags_agree(proj):
    """`--tests a,b` and `--tests a --tests b` must mean the same thing, and
    both must match `-D tests=a,b` -- a list param is collected with
    `action='append'`, which does not comma-split on its own."""
    _dfm(proj, "run", "tests", "--tests", "arb,err", "--views", "tlm")
    comma = _ran(proj)
    _dfm(proj, "--clean", "run", "tests", "--tests", "arb", "--tests", "err",
         "--views", "tlm")
    repeated = _ran(proj)
    assert comma == repeated
    assert "RAN-tlm/arb" in comma and "RAN-tlm/err" in comma


def test_D_selection_matches_the_flag(proj):
    _dfm(proj, "run", "tests", "-D", "p.tests.tests=arb", "-D", "p.tests.views=tlm")
    assert "RAN-tlm/arb" in _ran(proj)


def test_unmatched_selector_fails_the_run(proj):
    proc = _dfm(proj, "run", "tests", "--tests", "nosuch")
    assert proc.returncode != 0
    assert "no test matches" in (proc.stdout + proc.stderr)
    assert _ran(proj) == []
