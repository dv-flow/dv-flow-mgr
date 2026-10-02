#****************************************************************************
#* test_test_suites.py
#*
#* Test suites, test paths, and path-pattern selection.
#*
#* The contract being pinned:
#*   * suites nest: a `std.TestSuite` task's needs are its members, and a
#*     member may itself be a suite. A test's path is its position in that
#*     tree, relative to the runner;
#*   * `--tests` patterns match paths, left-unanchored, segment by segment.
#*     `--exclude` is applied last and always wins;
#*   * pruning reaches inside nested suites -- a deselected test is never built,
#*     however deep it sits;
#*   * `tests-info` resolves the same selection with the same code, and in a
#*     machine format its payload is the only thing on stdout.
#****************************************************************************
import json
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.std.test_select import (
    Pattern, Selection, SelectionError, build_tree, resolve)
from .marker_collector import MarkerCollector


FLOW = """\
package:
    name: p
    tasks:
    - { name: img, shell: bash, run: 'echo BUILT-IMAGE' }

    - name: reset
      shell: bash
      tags: [ std.Test ]
      run: 'echo RAN-reset'
    - name: csr-rw
      shell: bash
      tags: [ { std.Test: { name: csr_rw } } ]
      run: 'echo RAN-csr_rw'

    - name: uart-suite
      tags: [ { std.TestSuite: { name: uart } } ]
      strategy:
        matrix:
          view: [tlm, rtl]
          case:
          - { name: fifo_full }
          - { name: fifo_empty }
          - { name: break_det }
      body:
      - name: "${{ this.view }}-${{ this.case.name }}"
        shell: bash
        needs: [img]
        with:
          tn: { type: str, value: "${{ this.view }}/${{ this.case.name }}" }
        run: 'echo RAN-uart-${{ tn }}'

    - name: sanity
      uses: std.TestSuite
      needs: [reset, csr-rw]

    - name: periph
      uses: std.TestSuite
      needs: [uart-suite]

    - name: regress
      uses: std.TestSuite
      needs: [sanity, periph]

    - name: soak
      shell: bash
      tags: [ std.Test ]
      run: 'echo RAN-soak'

    - root: tests
      uses: std.TestRunner
      needs: [regress, soak]

    - root: tests-info
      uses: std.TestInfo
      with: { target: tests }
"""

ALL = ["regress.periph.uart.break_det", "regress.periph.uart.fifo_empty",
       "regress.periph.uart.fifo_full", "regress.sanity.csr_rw",
       "regress.sanity.reset", "soak"]


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


def _tree(pkg):
    return build_tree(pkg.task_m["p.tests"], lambda t: list(t.needs))


def _selected(pkg, **kw):
    tree = _tree(pkg)
    res = resolve(tree, Selection(**kw))
    return sorted(".".join(t.path) for t in res.kept_tests(tree))


# ------------------------------------------------------------------ patterns

@pytest.mark.parametrize("pattern,path,expect", [
    ("reset",           ("sanity", "reset"), True),
    ("reset",           ("reset",), True),
    ("res",             ("sanity", "reset"), False),    # not a substring match
    ("sanity.reset",    ("regress", "sanity", "reset"), True),
    (".sanity.reset",   ("regress", "sanity", "reset"), False),
    (".regress.sanity", ("regress", "sanity", "reset"), True),
    ("sanity",          ("regress", "sanity", "reset"), True),   # a suite
    ("sanity.",         ("regress", "sanity", "reset"), True),
    ("sanity.",         ("x", "sanity"), False),        # suites only
    ("sanity",          ("x", "sanity"), True),
    ("uart.fifo_*",     ("periph", "uart", "fifo_full"), True),
    ("uart.fifo_*",     ("periph", "uart", "break_det"), False),
    ("regress.**.reset", ("regress", "sanity", "reset"), True),
    ("regress.**.reset", ("regress", "reset"), True),
    ("regress.*.reset", ("regress", "a", "b", "reset"), False),
])
def test_pattern_matching(pattern, path, expect):
    assert Pattern.parse(pattern).selects(path) is expect


@pytest.mark.parametrize("bad", ["", ".", "a..b", "a@12", "a[view=rtl]"])
def test_a_malformed_or_unsupported_pattern_is_an_error(bad):
    with pytest.raises(SelectionError):
        Pattern.parse(bad)


def test_a_segment_glob_with_brackets_is_still_a_glob():
    assert Pattern.parse("fifo_[ef]*").selects(("uart", "fifo_full"))


# ---------------------------------------------------------------------- tree

def test_paths_follow_the_suite_tree(loaded):
    _, pkg = loaded
    assert sorted(".".join(t.path) for t in _tree(pkg).tests.values()) == ALL


def test_a_tag_name_overrides_the_task_name(loaded):
    """`csr-rw` is tagged `name: csr_rw`, and `uart-suite` `name: uart`: the
    path uses the declared names."""
    _, pkg = loaded
    paths = [".".join(t.path) for t in _tree(pkg).tests.values()]
    assert "regress.sanity.csr_rw" in paths
    assert "regress.periph.uart.fifo_full" in paths


def test_a_shared_suite_is_one_suite_with_two_paths(tmpdir):
    """Membership is by reference: a suite reached through two parents runs
    its tests once, and the inventory records the second route as an alias."""
    flow = FLOW.replace("needs: [regress, soak]",
                        "needs: [regress, sanity, soak]")
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(flow)
    pkg = PackageLoader().load(os.path.join(str(tmpdir), "flow.dv"))
    tree = _tree(pkg)
    reset = [t for t in tree.tests.values() if t.name == "reset"]
    assert len(reset) == 1
    assert [".".join(p) for p in reset[0].paths] == [
        "regress.sanity.reset", "sanity.reset"]


def test_a_suite_cycle_is_an_error(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write("""\
package:
    name: p
    tasks:
    - { name: t, shell: bash, tags: [std.Test], run: 'true' }
    - { name: a, uses: std.TestSuite, needs: [t, b] }
    - { name: b, uses: std.TestSuite, needs: [a] }
    - { root: tests, uses: std.TestRunner, needs: [a] }
""")
    pkg = PackageLoader().load(os.path.join(str(tmpdir), "flow.dv"))
    with pytest.raises(SelectionError, match="cycle"):
        _tree(pkg)


# ----------------------------------------------------------------- selection

def test_no_selection_selects_everything(loaded):
    _, pkg = loaded
    assert _selected(pkg) == ALL


def test_a_bare_name_still_selects_a_test(loaded):
    """Back-compat: `--tests reset` worked before suites had paths."""
    _, pkg = loaded
    assert _selected(pkg, tests=["reset"]) == ["regress.sanity.reset"]


def test_a_suite_prefix_selects_its_subtree(loaded):
    _, pkg = loaded
    assert _selected(pkg, tests=["sanity."]) == [
        "regress.sanity.csr_rw", "regress.sanity.reset"]


def test_a_super_suite_selects_everything_beneath_it(loaded):
    _, pkg = loaded
    assert _selected(pkg, tests=["regress."]) == ALL[:-1]


def test_patterns_union(loaded):
    _, pkg = loaded
    assert _selected(pkg, tests=["sanity.", "soak"]) == [
        "regress.sanity.csr_rw", "regress.sanity.reset", "soak"]


def test_exclude_wins_over_a_selection(loaded):
    _, pkg = loaded
    assert _selected(pkg, tests=["uart."], exclude=["break_det"]) == [
        "regress.periph.uart.fifo_empty", "regress.periph.uart.fifo_full"]


def test_exclude_alone_narrows_everything(loaded):
    _, pkg = loaded
    assert _selected(pkg, exclude=["regress."]) == ["soak"]


def test_an_exclude_that_matches_nothing_only_warns(loaded):
    """Excluding too little never under-tests, so it is not an error."""
    _, pkg = loaded
    res = resolve(_tree(pkg), Selection(exclude=["nosuch"]))
    assert res.warnings == ["--exclude 'nosuch' matches no test"]


def test_each_pattern_must_match_something(loaded):
    """One typo in a list of patterns must not silently shrink the run."""
    _, pkg = loaded
    with pytest.raises(SelectionError, match="no test matches 'sanityy.'"):
        _selected(pkg, tests=["reset", "sanityy."])


def test_excluding_everything_selected_is_an_error(loaded):
    _, pkg = loaded
    with pytest.raises(SelectionError, match="matched no tests"):
        _selected(pkg, tests=["sanity."], exclude=["sanity."])


def test_a_suite_with_nothing_selected_is_dropped(loaded):
    _, pkg = loaded
    res = resolve(_tree(pkg), Selection(tests=["sanity."]))
    assert {"p.periph", "p.uart-suite", "p.soak"} <= res.dropped
    assert "p.regress" not in res.dropped


# --------------------------------------------------------------- graph level

def _built(loaded, proj, **overrides):
    loader, pkg = loaded
    builder = TaskGraphBuilder(
        root_pkg=pkg, loader=loader, rundir=os.path.join(proj, "rundir"),
        task_param_overrides={"p.tests": overrides} if overrides else {})
    node = builder.mkTaskNode("p.tests")
    seen = set()

    def walk(n):
        if id(n) in seen:
            return
        seen.add(id(n))
        yield n.name
        for sub in getattr(n, "tasks", None) or []:
            yield from walk(sub)
        for need, _ in n.needs:
            yield from walk(need)
    return set(walk(node))


def _cells(names):
    import re
    return sorted(re.sub(r"(_\d+)+$", "", n.rsplit(".", 1)[-1])
                  for n in names if ".uart-suite." in n
                  and not n.endswith(".in"))


def test_pruning_reaches_inside_nested_suites(loaded, proj):
    """`fifo_full` sits three suites down; selecting it must narrow that matrix
    and drop `sanity` entirely -- not build the whole tree."""
    names = _built(loaded, proj, tests="fifo_full", views="rtl")
    assert _cells(names) == ["rtl-fifo_full"]
    assert not any(n.endswith((".reset", ".csr-rw", ".soak")) for n in names)
    assert "p.regress" in names and "p.periph" in names
    assert "p.img" in names


def test_an_unselected_branch_is_not_built(loaded, proj):
    names = _built(loaded, proj, tests="sanity.")
    assert _cells(names) == []
    assert "p.img" not in names       # only the dropped uart suite needed it
    assert "p.periph" not in names
    assert any(n.endswith(".reset") for n in names)


def test_everything_is_built_without_a_selection(loaded, proj):
    names = _built(loaded, proj)
    assert len(_cells(names)) == 6
    assert any(n.endswith(".soak") for n in names)


# ------------------------------------------------------------ end to end

def _dfm(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(cwd), capture_output=True, text=True)


def _ran(cwd):
    out = []
    for root, _, files in os.walk(os.path.join(str(cwd), "rundir")):
        for fn in files:
            if fn.endswith(".log"):
                with open(os.path.join(root, fn)) as f:
                    out.extend(l.strip() for l in f
                               if l.startswith(("RAN-", "BUILT-")))
    return sorted(out)


def test_cli_runs_a_suite_with_an_exclude(proj):
    proc = _dfm(proj, "run", "tests", "-t", "uart.", "-x", "fifo_*",
                "--views", "tlm")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _ran(proj) == ["BUILT-IMAGE", "RAN-uart-tlm/break_det"]


def test_info_json_is_the_only_thing_on_stdout(proj):
    """`dfm run tests-info --json | jq` must work: progress goes to stderr."""
    proc = _dfm(proj, "run", "tests-info", "--tests", "sanity.", "--json")
    assert proc.returncode == 0, proc.stderr
    inv = json.loads(proc.stdout)
    assert [t["path"] for t in inv["tests"]] == [
        "regress.sanity.reset", "regress.sanity.csr_rw"]
    assert inv["selection"]["tests"] == ["sanity."]


def test_info_list_prints_paths_the_runner_accepts(proj):
    """print == paste: every line of `--format list` is a valid `--tests`,
    anchored so it selects that one test and nothing that merely ends the
    same way."""
    proc = _dfm(proj, "run", "tests-info", "--format", "list",
                "-t", "regress.", "-x", "uart.")
    assert proc.returncode == 0, proc.stderr
    paths = proc.stdout.split()
    assert paths == [".regress.sanity.reset", ".regress.sanity.csr_rw"]
    proc = _dfm(proj, "run", "tests", "--tests", ",".join(paths))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _ran(proj) == ["RAN-csr_rw", "RAN-reset"]


def test_info_yaml(proj):
    import yaml
    proc = _dfm(proj, "run", "tests-info", "--format", "yaml", "-t", "soak")
    assert proc.returncode == 0, proc.stderr
    assert [t["path"] for t in yaml.safe_load(proc.stdout)["tests"]] == ["soak"]


def test_info_rejects_what_the_runner_rejects(proj):
    """Aligned strictness: a typo is an error in both, never an empty list."""
    for task in ("tests", "tests-info"):
        proc = _dfm(proj, "run", task, "--tests", "sanityy.")
        assert proc.returncode != 0, task
        assert "no test matches 'sanityy.'" in proc.stdout + proc.stderr


def test_info_text_shows_the_selection(proj):
    proc = _dfm(proj, "run", "tests-info", "-t", "sanity.")
    assert proc.returncode == 0, proc.stderr
    assert "--tests sanity." in proc.stdout
    assert "reset" in proc.stdout and "fifo_full" not in proc.stdout


# ------------------------------------------------------------- instances

from dv_flow.mgr.std.test_info import build_inventory


def _inv(pkg, instances=True, **kw):
    tree = _tree(pkg)
    return build_inventory(tree, resolve(tree, Selection(**kw)),
                           target="p.tests", instances=instances)


def test_an_instance_is_a_test_on_one_view(loaded):
    _, pkg = loaded
    inv = _inv(pkg, tests=["fifo_full", "reset"])
    assert [(i["id"], i["argv"]) for i in inv["instances"]] == [
        ("regress.sanity.reset",
         ["run", "p.tests", "--tests", ".regress.sanity.reset"]),
        ("regress.periph.uart.fifo_full[view=tlm]",
         ["run", "p.tests", "--tests", ".regress.periph.uart.fifo_full",
          "--views", "tlm"]),
        ("regress.periph.uart.fifo_full[view=rtl]",
         ["run", "p.tests", "--tests", ".regress.periph.uart.fifo_full",
          "--views", "rtl"]),
    ]


def test_instances_honor_the_view_selection(loaded):
    _, pkg = loaded
    inv = _inv(pkg, tests=["uart."], views=["rtl"])
    assert {i["view"] for i in inv["instances"]} == {"rtl"}
    assert len(inv["instances"]) == 3


def test_instances_are_only_listed_when_asked(loaded):
    _, pkg = loaded
    assert "instances" not in _inv(pkg, instances=False)
    assert _inv(pkg, instances=False)["schema"] == 1


def test_a_selector_is_anchored_against_a_suffix_twin(tmpdir):
    """`x.reset` and `y.x.reset` are different tests; an unanchored `x.reset`
    would select both, so the emitted selector must not be."""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write("""\
package:
    name: p
    tasks:
    - { name: reset, shell: bash, tags: [std.Test], run: 'true' }
    - { name: reset2, shell: bash, tags: [{std.Test: {name: reset}}], run: 'true' }
    - { name: x, uses: std.TestSuite, needs: [reset] }
    - { name: x2, uses: std.TestSuite, needs: [reset2],
        tags: [{std.TestSuite: {name: x}}] }
    - { name: y, uses: std.TestSuite, needs: [x2] }
    - { root: tests, uses: std.TestRunner, needs: [x, y] }
""")
    pkg = PackageLoader().load(os.path.join(str(tmpdir), "flow.dv"))
    tree = _tree(pkg)
    inv = build_inventory(tree, resolve(tree, Selection()), instances=True)
    assert [t["selector"] for t in inv["tests"]] == [".x.reset", ".y.x.reset"]


def test_an_unresolvable_view_axis_cannot_be_listed_as_runs(loaded):
    """One entry silently covering every view would defeat per-run entries."""
    _, pkg = loaded
    tree = build_tree(pkg.task_m["p.tests"], lambda t: list(t.needs))
    for t in tree.tests.values():
        if t.key[0] == "p.uart-suite":
            t.views, t.views_open = [], True
    res = resolve(tree, Selection(tests=["uart."]))
    res.run_views["p.uart-suite"] = None
    with pytest.raises(SelectionError, match="could not be resolved"):
        build_inventory(tree, res, target="p.tests", instances=True)


def test_every_instance_argv_runs_exactly_that_run(proj):
    """The contract a per-test runner relies on: replaying `argv` runs that
    one test on that one view."""
    proc = _dfm(proj, "run", "tests-info", "--json", "--instances",
                "-t", "uart.fifo_*,reset")
    assert proc.returncode == 0, proc.stderr
    instances = json.loads(proc.stdout)["instances"]
    assert len(instances) == 5
    for inst in instances:
        # Run options go between `run` and the task, as for any dfm command.
        argv = inst["argv"]
        proc = _dfm(proj, argv[0], "--clean", *argv[1:])
        assert proc.returncode == 0, proc.stdout + proc.stderr
        ran = [r for r in _ran(proj) if r.startswith("RAN-")]
        if inst["view"]:
            case = inst["test"].rsplit(".", 1)[1]
            assert ran == ["RAN-uart-%s/%s" % (inst["view"], case)], inst["id"]
        else:
            assert ran == ["RAN-reset"], inst["id"]


def test_list_with_instances_prints_selection_arguments(proj):
    proc = _dfm(proj, "run", "tests-info", "--format", "list", "--instances",
                "-t", "fifo_full", "--views", "rtl")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == \
        "--tests .regress.periph.uart.fifo_full --views rtl"
