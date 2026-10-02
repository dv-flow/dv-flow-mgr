#****************************************************************************
#* test_test_requires.py
#*
#* The build fan-in of a test selection: which producers of some data (a
#* simulation image) the selected runs depend on.
#*
#* The contract being pinned:
#*   * the walk is dataflow, not dependency: it stops at the NEAREST matching
#*     producer on each path, and does not pass a task that consumes what it
#*     receives;
#*   * each run (a test on one view) is mapped to its own built cell, so a run
#*     on `rtl` requires the rtl image and not the tlm one;
#*   * `tests-info --requires` builds nothing, and `--build-only` builds the
#*     producers and runs no test;
#*   * the three steps compose: list, build once, run each test in its own
#*     rundir against the build with `--base-rundir`, rebuilding nothing.
#****************************************************************************
import json
import os
import subprocess
import sys

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.std.checks import producers
from dv_flow.mgr.std.test_select import (
    Selection, build_tree, resolve, run_requires)
from dv_flow.mgr.type_match import parse_pattern


FLOW = """\
package:
    name: p
    tasks:
    - name: elab-rtl
      shell: bash
      run: 'echo BUILT-elab'
      produces: [ { type: std.FileSet, filetype: simDir } ]
    - name: img-rtl
      shell: bash
      needs: [elab-rtl]
      consumes: none
      passthrough: all
      run: 'echo BUILT-rtl'
      produces: [ { type: std.FileSet, filetype: simDir } ]
    - name: img-tlm
      shell: bash
      run: 'echo BUILT-tlm'
      produces: [ { type: std.FileSet, filetype: simDir } ]

    - name: reset
      shell: bash
      tags: [ std.Test ]
      needs: [img-rtl]
      run: 'echo RAN-reset'

    - name: uart-suite
      tags: [ { std.TestSuite: { name: uart } } ]
      strategy:
        matrix:
          view: [tlm, rtl]
          case:
          - { name: fifo_full }
          - { name: break_det }
      body:
      - name: "${{ this.view }}-${{ this.case.name }}"
        shell: bash
        needs: [ "img-${{ this.view }}" ]
        consumes: [ { filetype: simDir } ]
        with:
          tn: { type: str, value: "${{ this.view }}/${{ this.case.name }}" }
        run: 'echo RAN-uart-${{ tn }}'

    - name: regress
      uses: std.TestSuite
      needs: [reset, uart-suite]

    - root: tests
      uses: std.TestRunner
      needs: [regress]

    - root: tests-info
      uses: std.TestInfo
      with: { target: tests }
"""

SIMDIR = "filetype=simDir"


@pytest.fixture
def proj(tmpdir):
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(FLOW)
    return str(tmpdir)


def _dfm(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(cwd), capture_output=True, text=True)


def _info(proj, *args):
    proc = _dfm(proj, "run", "tests-info", "--json", "--requires", SIMDIR,
                *args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def _logged(rundir, prefix):
    out = []
    for root, _, files in os.walk(rundir):
        for fn in files:
            if fn.endswith(".log"):
                with open(os.path.join(root, fn)) as f:
                    out.extend(l.strip() for l in f if l.startswith(prefix))
    return sorted(out)


# ------------------------------------------------------------------ patterns

@pytest.mark.parametrize("text,expect", [
    ("std.FileSet:filetype=simDir", {"type": "std.FileSet", "filetype": "simDir"}),
    ("filetype=simDir",             {"filetype": "simDir"}),
    ("std.FileSet",                 {"type": "std.FileSet"}),
    ("a=1, b=2",                    {"a": "1", "b": "2"}),
    ("",                            None),
])
def test_a_produce_pattern_parses(text, expect):
    assert parse_pattern(text) == expect


@pytest.mark.parametrize("bad", ["std.FileSet:simDir", "=x"])
def test_a_malformed_produce_pattern_is_an_error(bad):
    with pytest.raises(ValueError, match="malformed"):
        parse_pattern(bad)


# ---------------------------------------------------------------- the walk

def _node(name, produces=None, needs=(), passthrough="unused", consumes="all"):
    """A built node's dataflow shape; the defaults are the engine's."""
    from types import SimpleNamespace
    return SimpleNamespace(name=name, produces=produces,
                           needs=[(n, False) for n in needs],
                           passthrough=passthrough, consumes=consumes)


IMG = [{"type": "std.FileSet", "filetype": "simDir"}]


def test_the_walk_stops_at_the_nearest_producer():
    elab = _node("elab", IMG)
    img = _node("img", IMG, needs=[elab], passthrough="all")
    run = _node("run", needs=[img])
    assert [n.name for n in producers([run], {"filetype": "simDir"})["run"]] \
        == ["img"]


def test_the_walk_does_not_pass_a_task_that_consumes_its_inputs():
    img = _node("img", IMG)
    sink = _node("sink", needs=[img])
    fwd = _node("fwd", needs=[img], passthrough="all")
    assert producers([_node("a", needs=[sink])], {"filetype": "simDir"}) \
        == {"a": []}
    assert [n.name for n in
            producers([_node("b", needs=[fwd])], {"filetype": "simDir"})["b"]] \
        == ["img"]


def test_a_roots_own_declaration_does_not_count():
    run = _node("run", IMG)
    assert producers([run], {"filetype": "simDir"}) == {"run": []}


# -------------------------------------------------------- runs in the graph

def _required(proj, **sel):
    loader = PackageLoader()
    pkg = loader.load(os.path.join(proj, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg, loader=loader, rundir=os.path.join(proj, "rundir"),
        task_param_overrides={"p.tests": sel} if sel else {})
    root = builder.mkTaskNode("p.tests")
    tree = build_tree(pkg.task_m["p.tests"], lambda t: list(t.needs))
    res = resolve(tree, Selection(
        tests=[sel["tests"]] if "tests" in sel else [],
        views=[sel["views"]] if "views" in sel else []))
    req = run_requires(tree, res, root, {"filetype": "simDir"})
    return {(".".join(tree.tests[k].path), v): [n.name for n in nodes]
            for (k, v), nodes in req.items()}


def test_each_run_requires_its_own_views_image(proj):
    assert _required(proj) == {
        ("regress.reset", None): ["p.img-rtl"],
        ("regress.uart.fifo_full", "tlm"): ["p.img-tlm"],
        ("regress.uart.fifo_full", "rtl"): ["p.img-rtl"],
        ("regress.uart.break_det", "tlm"): ["p.img-tlm"],
        ("regress.uart.break_det", "rtl"): ["p.img-rtl"],
    }


def test_only_selected_runs_are_mapped(proj):
    assert _required(proj, tests="fifo_full", views="tlm") == {
        ("regress.uart.fifo_full", "tlm"): ["p.img-tlm"]}


# ---------------------------------------------------------------- tests-info

def test_requires_reports_runs_producers_and_the_build_command(proj):
    inv = _info(proj, "-t", "uart.", "--views", "rtl")
    assert {i["id"]: i["requires"] for i in inv["instances"]} == {
        "regress.uart.fifo_full[view=rtl]": ["p.img-rtl"],
        "regress.uart.break_det[view=rtl]": ["p.img-rtl"],
    }
    assert inv["producers"] == [{
        "node": "p.img-rtl", "rundir": "p.img-rtl",
        "needed_by": ["regress.uart.fifo_full[view=rtl]",
                      "regress.uart.break_det[view=rtl]"]}]
    assert inv["build"]["argv"] == [
        "run", "p.tests", "--tests", "uart.", "--views", "rtl",
        "--build-only", SIMDIR]
    assert inv["requires"]["produces"] == {"filetype": "simDir"}


def test_requires_builds_nothing(proj):
    _info(proj)
    assert _logged(os.path.join(proj, "rundir"), "BUILT-") == []
    assert not os.path.isdir(os.path.join(proj, "rundir", "p.img-rtl"))


def test_a_pattern_nothing_produces_warns_once(proj):
    proc = _dfm(proj, "run", "tests-info", "--json", "--requires", "bogus")
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr.count("no selected test depends on a producer of bogus") == 1
    inv = json.loads(proc.stdout)
    assert inv["producers"] == []


def test_a_malformed_pattern_fails_the_command(proj):
    proc = _dfm(proj, "run", "tests-info", "--json", "--requires", "a:b")
    assert proc.returncode != 0
    assert "malformed pattern" in proc.stdout + proc.stderr


# ---------------------------------------------------------------- build-only

def test_build_only_builds_the_producers_and_runs_no_test(proj):
    proc = _dfm(proj, "run", "tests", "-t", "uart.", "--views", "tlm",
                "--build-only", SIMDIR)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rundir = os.path.join(proj, "rundir")
    assert _logged(rundir, "BUILT-") == ["BUILT-tlm"]
    assert _logged(rundir, "RAN-") == []


# ---------------------------------------------------------- split regression

def test_list_build_once_then_run_each_test_against_the_build(proj, tmpdir):
    """The workflow `--requires` exists for: one build session, then one
    rundir per run linked back to it. No run rebuilds an image."""
    inv = _info(proj, "-t", "fifo_full,reset")
    build = inv["build"]["argv"]
    proc = _dfm(proj, *build)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    shared = os.path.join(proj, "rundir")
    assert _logged(shared, "BUILT-") == ["BUILT-elab", "BUILT-rtl", "BUILT-tlm"]
    for p in inv["producers"]:
        assert os.path.isdir(os.path.join(shared, p["rundir"])), p

    for n, inst in enumerate(inv["instances"]):
        run_dir = os.path.join(str(tmpdir), "run%d" % n)
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "flow.dv"), "w") as f:
            f.write(FLOW)
        argv = inst["argv"]
        proc = _dfm(run_dir, argv[0], "--base-rundir", shared, *argv[1:])
        assert proc.returncode == 0, proc.stdout + proc.stderr
        local = os.path.join(run_dir, "rundir")
        assert _logged(local, "BUILT-") == [], inst["id"]
        ran = _logged(local, "RAN-")
        if inst["view"]:
            assert ran == ["RAN-uart-%s/fifo_full" % inst["view"]], inst["id"]
        else:
            assert ran == ["RAN-reset"], inst["id"]
