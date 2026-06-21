import asyncio
import json
import os
import sys
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_node import TaskNode
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, SeverityE
from dv_flow.mgr.task_listener_report import TaskListenerReport, REPORT_SCHEMA
from dv_flow.mgr.util import loadProjPkgDef
from dv_flow.mgr.ext_rgy import ExtRgy


@pytest.fixture(autouse=True)
def reset_extrgy():
    """Reset the ExtRgy singleton, sys.modules, sys.path, and MAKEFLAGS before
    each test to prevent state leakage."""
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()

    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']

    ExtRgy._inst = None
    yield
    ExtRgy._inst = None

    added_modules = set(sys.modules.keys()) - original_modules
    for mod_name in added_modules:
        del sys.modules[mod_name]

    sys.path[:] = original_path

    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']


# ---------------------------------------------------------------------------
# Unit tests: generate() over synthetic nodes
# ---------------------------------------------------------------------------

def _mk_node(name, task_dir, status, markers=None, changed=True,
             cache_hit=False, write_log=True):
    """Build a synthetic TaskNode with a result and (optionally) a logfile.

    rundir is set to [abs task_dir] so the listener's fallback resolver
    (no runner) resolves directly to task_dir (absolute first segment).
    """
    os.makedirs(task_dir, exist_ok=True)
    node = TaskNode(name=name, srcdir=task_dir, params=None, ctxt=None)
    node.rundir = [task_dir]
    node.result = TaskDataResult(
        status=status, changed=changed, cache_hit=cache_hit,
        markers=markers or [])
    if write_log:
        # ctxt is None -> _get_log_filename() returns "<name>.log"
        with open(os.path.join(task_dir, "%s.log" % name), "w") as f:
            f.write("log output for %s\n" % name)
    return node


def test_report_generate_unit(tmpdir):
    tmpdir = str(tmpdir)
    report_dir = os.path.join(tmpdir, "report")

    n1 = _mk_node("pkg.build", os.path.join(tmpdir, "build"), 0)
    n2 = _mk_node("pkg.sim", os.path.join(tmpdir, "sim"), 1,
                  markers=[TaskMarker(msg="boom", severity=SeverityE.Error)])

    rpt = TaskListenerReport(rundir=tmpdir, root_name="pkg")
    rpt.event(n1, "leave")
    rpt.event(n2, "leave")
    rpt.event(n2, "leave")  # duplicate must be ignored

    failed = rpt.generate(report_dir, generated_unix=123)
    assert failed == 1

    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)

    assert data["schema"] == REPORT_SCHEMA
    assert data["root"] == "pkg"
    assert data["status"] == 1
    assert data["generated_unix"] == 123
    assert data["counts"]["tasks_total"] == 2
    assert data["counts"]["tasks_failed"] == 1
    assert data["counts"]["markers"]["error"] == 1
    assert data["counts"]["markers"]["warning"] == 0

    # Logs copied (dot is a permitted filename char)
    assert os.path.isfile(os.path.join(report_dir, "logs", "pkg.build.log"))
    assert os.path.isfile(os.path.join(report_dir, "logs", "pkg.sim.log"))

    # Per-task entries
    by_name = {t["name"]: t for t in data["tasks"]}
    assert by_name["pkg.build"]["status"] == 0
    assert by_name["pkg.build"]["log"] == os.path.join("logs", "pkg.build.log")
    assert by_name["pkg.sim"]["status"] == 1
    assert len(by_name["pkg.sim"]["markers"]) == 1

    # markers.jsonl carries the task name
    with open(os.path.join(report_dir, "markers.jsonl")) as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    assert len(lines) == 1
    m = json.loads(lines[0])
    assert m["task"] == "pkg.sim"
    assert m["severity"] == "error"
    assert m["msg"] == "boom"

    # Markdown summary exists and names the failing task
    with open(os.path.join(report_dir, "report.md")) as f:
        md = f.read()
    assert "pkg.sim" in md
    assert "FAIL" in md


def test_report_no_logfile(tmpdir):
    """A task with no logfile is still reported, with log == None."""
    tmpdir = str(tmpdir)
    report_dir = os.path.join(tmpdir, "report")
    n = _mk_node("pkg.pyonly", os.path.join(tmpdir, "pyonly"), 0, write_log=False)

    rpt = TaskListenerReport(rundir=tmpdir, root_name="pkg")
    rpt.event(n, "leave")
    rpt.generate(report_dir)

    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    assert data["tasks"][0]["log"] is None
    assert not os.listdir(os.path.join(report_dir, "logs"))


def test_report_log_name_collision(tmpdir):
    """Distinct tasks whose names sanitize to the same base get unique logs."""
    tmpdir = str(tmpdir)
    report_dir = os.path.join(tmpdir, "report")
    # Both sanitize to "a_b" (space -> '_'; underscore unchanged). Names are
    # kept free of '/' so the synthetic "<name>.log" file is writable.
    n1 = _mk_node("a b", os.path.join(tmpdir, "t1"), 0)
    n2 = _mk_node("a_b", os.path.join(tmpdir, "t2"), 0)

    rpt = TaskListenerReport(rundir=tmpdir, root_name="pkg")
    rpt.event(n1, "leave")
    rpt.event(n2, "leave")
    rpt.generate(report_dir)

    logs = sorted(os.listdir(os.path.join(report_dir, "logs")))
    assert logs == ["a_b.1.log", "a_b.log"]

    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    log_fields = sorted(t["log"] for t in data["tasks"])
    assert log_fields == [os.path.join("logs", "a_b.1.log"),
                          os.path.join("logs", "a_b.log")]


def test_report_reads_exec_data_from_disk(tmpdir):
    """Backend-agnostic path: data is read from the on-disk exec_data.json
    even when the in-memory task.result is absent (as for remote backends)."""
    tmpdir = str(tmpdir)
    report_dir = os.path.join(tmpdir, "report")
    task_dir = os.path.join(tmpdir, "build")
    os.makedirs(task_dir)

    # The exec_data.json a remote worker would have written to the shared rundir
    with open(os.path.join(task_dir, "pkg.build.exec_data.json"), "w") as f:
        json.dump({
            "name": "pkg.build",
            "rundir": task_dir,
            "logfile": "pkg.build.log",
            "result": {
                "status": 2,
                "changed": True,
                "markers": [{"msg": "remote boom", "severity": "error"}],
            },
        }, f)
    with open(os.path.join(task_dir, "pkg.build.log"), "w") as f:
        f.write("remote log contents\n")

    node = TaskNode(name="pkg.build", srcdir=task_dir, params=None, ctxt=None)
    node.rundir = task_dir          # resolved absolute string (post-run form)
    node.result = None             # simulate remote: no in-memory result

    rpt = TaskListenerReport(rundir=tmpdir, root_name="pkg")
    rpt.event(node, "leave")
    failed = rpt.generate(report_dir)

    assert failed == 1
    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    entry = data["tasks"][0]
    assert entry["status"] == 2
    assert entry["markers"][0]["msg"] == "remote boom"
    assert data["counts"]["markers"]["error"] == 1
    # Log resolved via the logfile field in exec_data.json
    assert entry["log"] == os.path.join("logs", "pkg.build.log")
    with open(os.path.join(report_dir, entry["log"])) as f:
        assert "remote log contents" in f.read()


def test_report_dir_created_nested(tmpdir):
    """generate() creates a missing (nested) report directory."""
    tmpdir = str(tmpdir)
    report_dir = os.path.join(tmpdir, "a", "b", "report")
    n = _mk_node("pkg.t", os.path.join(tmpdir, "t"), 0)
    rpt = TaskListenerReport(rundir=tmpdir, root_name="pkg")
    rpt.event(n, "leave")
    rpt.generate(report_dir)
    assert os.path.isfile(os.path.join(report_dir, "report.json"))


# ---------------------------------------------------------------------------
# End-to-end tests: run a real flow with the listener attached
# ---------------------------------------------------------------------------

def _run_with_report(tmpdir, flow_dv, task_name, extra_files=None):
    """Build + run a flow with a report listener wired exactly like cmd_run,
    then generate the bundle. Returns (runner, report_dir)."""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    report_dir = os.path.join(tmpdir, "report")

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    for fname, content in (extra_files or {}).items():
        with open(os.path.join(tmpdir, fname), "w") as f:
            f.write(content)

    loader, pkg_def = loadProjPkgDef(tmpdir)
    assert pkg_def is not None

    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir, loader=loader)
    runner = TaskSetRunner(builder=builder, rundir=rundir, nproc=2)

    report = TaskListenerReport(rundir=rundir, root_name=pkg_def.name)
    runner.add_listener(report.event)

    task = builder.mkTaskNode(task_name)
    asyncio.run(runner.run(task))
    report.generate(report_dir, generated_unix=1)
    return runner, report_dir


def test_report_e2e_pass(tmpdir):
    tmpdir = str(tmpdir)
    flow_dv = """
package:
  name: rpt_pass
  tasks:
  - name: Hello
    shell: bash
    run: |
      echo "hello world"
"""
    runner, report_dir = _run_with_report(tmpdir, flow_dv, "rpt_pass.Hello")
    assert runner.status == 0

    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    assert data["root"] == "rpt_pass"
    assert data["status"] == 0
    assert data["counts"]["tasks_failed"] == 0

    hello = next(t for t in data["tasks"] if t["name"].endswith("Hello"))
    assert hello["status"] == 0
    assert hello["log"] is not None
    with open(os.path.join(report_dir, hello["log"])) as f:
        assert "hello world" in f.read()


def test_report_e2e_fail(tmpdir):
    tmpdir = str(tmpdir)
    flow_dv = """
package:
  name: rpt_fail
  tasks:
  - name: Boom
    shell: bash
    run: |
      echo "about to fail"
      exit 2
"""
    runner, report_dir = _run_with_report(tmpdir, flow_dv, "rpt_fail.Boom")
    assert runner.status != 0

    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    assert data["status"] >= 1
    assert data["counts"]["tasks_failed"] >= 1
    boom = next(t for t in data["tasks"] if t["name"].endswith("Boom"))
    assert boom["status"] != 0
    with open(os.path.join(report_dir, boom["log"])) as f:
        assert "about to fail" in f.read()


def test_report_e2e_markers(tmpdir):
    tmpdir = str(tmpdir)
    producer_py = """
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, SeverityE

async def Warn(ctxt, input):
    return TaskDataResult(
        status=0,
        markers=[
            TaskMarker(msg="heads up", severity=SeverityE.Warning),
            TaskMarker(msg="just so you know", severity=SeverityE.Info),
        ])
"""
    flow_dv = """
package:
  name: rpt_mark
  tasks:
  - name: Warn
    shell: pytask
    run: producer.Warn
"""
    runner, report_dir = _run_with_report(
        tmpdir, flow_dv, "rpt_mark.Warn",
        extra_files={"producer.py": producer_py})
    assert runner.status == 0

    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    assert data["counts"]["markers"]["warning"] == 1
    assert data["counts"]["markers"]["info"] == 1

    with open(os.path.join(report_dir, "markers.jsonl")) as f:
        markers = [json.loads(l) for l in f.read().splitlines() if l.strip()]
    sevs = sorted(m["severity"] for m in markers)
    assert sevs == ["info", "warning"]
    assert all(m["task"].endswith("Warn") for m in markers)

    # The real run must have persisted markers + logfile to exec_data.json
    # (the backend-agnostic source the report reads from).
    warn = next(t for t in data["tasks"] if t["name"].endswith("Warn"))
    exec_data_files = [f for f in os.listdir(warn["rundir"])
                       if f.endswith(".exec_data.json")]
    assert exec_data_files
    with open(os.path.join(warn["rundir"], exec_data_files[0])) as f:
        ed = json.load(f)
    assert "logfile" in ed
    assert len(ed["result"]["markers"]) == 2


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------

def test_report_cli_arg_parsed():
    from dv_flow.mgr.__main__ import get_parser
    parser = get_parser()
    args = parser.parse_args(["run", "--report", "out/dir", "sometask"])
    assert args.report_dir == "out/dir"

    args = parser.parse_args(["run", "sometask"])
    assert args.report_dir is None


def test_report_cli_end_to_end(tmpdir):
    """Drive CmdRun with --report and confirm the bundle is written."""
    from dv_flow.mgr.__main__ import get_parser
    from dv_flow.mgr.cmds.cmd_run import CmdRun

    tmpdir = str(tmpdir)
    report_dir = os.path.join(tmpdir, "report")
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write("""
package:
  name: rpt_cli
  tasks:
  - name: Hello
    shell: bash
    run: |
      echo "from cli"
""")

    parser = get_parser()
    args = parser.parse_args(
        ["run", "--root", tmpdir, "--report", report_dir, "rpt_cli.Hello"])

    old_cwd = os.getcwd()
    os.chdir(tmpdir)
    try:
        status = CmdRun()(args)
    finally:
        os.chdir(old_cwd)

    assert status == 0
    assert os.path.isfile(os.path.join(report_dir, "report.json"))
    with open(os.path.join(report_dir, "report.json")) as f:
        data = json.load(f)
    assert data["root"] == "rpt_cli"
    assert data["generated_unix"] is not None
    hello = next(t for t in data["tasks"] if t["name"].endswith("Hello"))
    assert hello["log"] is not None
