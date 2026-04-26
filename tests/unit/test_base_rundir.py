"""Tests for --base-rundir support."""
import asyncio
import json
import os
import sys
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.ext_rgy import ExtRgy


@pytest.fixture(autouse=True)
def reset_extrgy():
    """Reset ExtRgy singleton between tests."""
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


def _run_flow(tmpdir, flow_dv, task_name, **runner_kwargs):
    """Helper: load a flow, build graph, run a task, return (runner, task_node)."""
    flow_path = os.path.join(str(tmpdir), "flow.dv")
    with open(flow_path, "w") as f:
        f.write(flow_dv)

    loader = PackageLoader()
    pkg = loader.load(flow_path)
    rundir = runner_kwargs.pop("rundir", os.path.join(str(tmpdir), "rundir"))
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir, builder=builder, **runner_kwargs)

    node = builder.mkTaskNode(task_name)
    asyncio.run(runner.run(node))
    return runner, node


SIMPLE_FLOW = """\
package:
  name: pkg
  tasks:
  - name: build
    uses: std.CreateFile
    with:
      filename: out.txt
      content: "built"
"""


def test_base_rundir_satisfies_leaf_task(tmpdir):
    """A task with exec_data in base-rundir is satisfied without re-execution."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    # Phase 1: populate the base rundir
    r1, n1 = _run_flow(base_dir, SIMPLE_FLOW, "pkg.build",
                        rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0
    assert n1.result.changed is True

    # Phase 2: run with base-rundir -- task should be satisfied
    r2, n2 = _run_flow(local_dir, SIMPLE_FLOW, "pkg.build",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0
    assert n2.result.base_hit is True
    assert n2.result.changed is False
    # No local directory created for the satisfied task
    local_task_dir = os.path.join(local_dir, "rundir", "pkg.build")
    assert not os.path.isdir(local_task_dir)


TWO_TASK_FLOW = """\
package:
  name: pkg
  tasks:
  - name: build
    uses: std.CreateFile
    with:
      filename: out.txt
      content: "built"
  - name: test
    uses: std.CreateFile
    needs: [build]
    with:
      filename: result.txt
      content: "tested"
"""


def test_base_rundir_runs_unsatisfied_task(tmpdir):
    """Build is satisfied from base; test runs locally."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    # Phase 1: run only build
    r1, _ = _run_flow(base_dir, TWO_TASK_FLOW, "pkg.build",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    # Phase 2: run test with base-rundir
    r2, n2 = _run_flow(local_dir, TWO_TASK_FLOW, "pkg.test",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0
    # build should be satisfied from base
    build_node = None
    for dep, _ in n2.needs:
        if "build" in dep.name:
            build_node = dep
            break
    assert build_node is not None
    assert build_node.result.base_hit is True
    # test should have run locally
    assert n2.result.changed is True
    assert n2.result.base_hit is False


def test_base_rundir_force_ignores_base(tmpdir):
    """--force causes tasks to run even when present in base-rundir."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    r1, _ = _run_flow(base_dir, SIMPLE_FLOW, "pkg.build",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    r2, n2 = _run_flow(local_dir, SIMPLE_FLOW, "pkg.build",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"),
                        force_run=True)
    assert r2.status == 0
    assert n2.result.base_hit is False
    assert n2.result.changed is True
    # Local task dir should exist because the task ran locally
    assert os.path.isdir(os.path.join(local_dir, "rundir", "pkg.build"))


def test_base_rundir_failed_task_not_satisfied(tmpdir):
    """A task that failed in base-rundir is not treated as satisfied."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    # Populate base with a successful run first, then corrupt exec_data
    r1, _ = _run_flow(base_dir, SIMPLE_FLOW, "pkg.build",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    # Set status to non-zero in exec_data
    task_dir = os.path.join(base_dir, "rundir", "pkg.build")
    exec_files = [f for f in os.listdir(task_dir) if f.endswith(".exec_data.json")]
    assert len(exec_files) > 0
    exec_path = os.path.join(task_dir, exec_files[0])
    with open(exec_path, "r") as f:
        data = json.load(f)
    data["result"]["status"] = 1
    with open(exec_path, "w") as f:
        json.dump(data, f)

    # Run with base-rundir -- should NOT be satisfied (status != 0)
    r2, n2 = _run_flow(local_dir, SIMPLE_FLOW, "pkg.build",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0
    assert n2.result.base_hit is False
    assert n2.result.changed is True


def test_base_rundir_missing_exec_data(tmpdir):
    """Tasks run locally when base-rundir exists but has no exec_data."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    # Create the base rundir structure without any exec_data files
    os.makedirs(os.path.join(base_dir, "rundir", "pkg.build"))

    r2, n2 = _run_flow(local_dir, SIMPLE_FLOW, "pkg.build",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0
    assert n2.result.base_hit is False
    assert n2.result.changed is True


PASSTHROUGH_FLOW = """\
package:
  name: pkg
  tasks:
  - name: create
    uses: std.CreateFile
    with:
      filename: data.txt
      content: "data"
  - name: pass
    uses: std.Null
    passthrough: all
    needs: [create]
  - name: consume
    needs: [pass]
    passthrough: all
    consumes: none
"""


def test_base_rundir_with_passthrough(tmpdir):
    """Passthrough chains work correctly across base-rundir boundary."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    # Phase 1: run full chain to populate base
    r1, _ = _run_flow(base_dir, PASSTHROUGH_FLOW, "pkg.consume",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    # Phase 2: run consume with base-rundir
    r2, n2 = _run_flow(local_dir, PASSTHROUGH_FLOW, "pkg.consume",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0
    # All tasks should have been satisfied from base
    assert n2.result.base_hit is True
    # Output should carry through the file from create
    assert len(n2.output.output) >= 1


def test_base_rundir_output_paths_reference_base(tmpdir):
    """Output items from base-satisfied tasks reference the base-rundir."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    r1, _ = _run_flow(base_dir, TWO_TASK_FLOW, "pkg.test",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    r2, n2 = _run_flow(local_dir, TWO_TASK_FLOW, "pkg.test",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0

    # Find the build dependency node
    build_node = None
    for dep, _ in n2.needs:
        if "build" in dep.name:
            build_node = dep
            break
    assert build_node is not None
    assert build_node.result.base_hit is True

    # Check that output items from build reference base_dir, not local_dir
    for item in build_node.output.output:
        basedir = getattr(item, "basedir", None)
        if basedir is not None:
            assert base_dir in basedir, \
                "Expected basedir in base-rundir, got: %s" % basedir
            assert local_dir not in basedir


def test_base_rundir_listener_events(tmpdir):
    """Listener receives base_hit events for satisfied tasks."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    r1, _ = _run_flow(base_dir, SIMPLE_FLOW, "pkg.build",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    # Set up a recording listener
    events = []
    def recorder(task, reason):
        events.append((getattr(task, 'name', None), reason))

    flow_path = os.path.join(str(local_dir), "flow.dv")
    with open(flow_path, "w") as f:
        f.write(SIMPLE_FLOW)

    loader = PackageLoader()
    pkg = loader.load(flow_path)
    rundir = os.path.join(str(local_dir), "rundir")
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir, builder=builder,
                           base_rundir=os.path.join(base_dir, "rundir"))
    runner.add_listener(recorder)

    node = builder.mkTaskNode("pkg.build")
    asyncio.run(runner.run(node))

    # Should have enter, base_hit, leave for the satisfied task
    task_events = [(name, reason) for name, reason in events
                   if name == "pkg.build"]
    reasons = [r for _, r in task_events]
    assert "enter" in reasons
    assert "base_hit" in reasons
    assert "leave" in reasons


def test_base_rundir_env_variable(tmpdir):
    """DFM_BASE_RUNDIR env var is set when base_rundir is provided."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    flow_path = os.path.join(str(local_dir), "flow.dv")
    with open(flow_path, "w") as f:
        f.write(SIMPLE_FLOW)

    loader = PackageLoader()
    pkg = loader.load(flow_path)
    rundir = os.path.join(str(local_dir), "rundir")
    base_rundir_path = os.path.join(base_dir, "rundir")
    os.makedirs(base_rundir_path, exist_ok=True)

    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir, builder=builder,
                           base_rundir=base_rundir_path)

    node = builder.mkTaskNode("pkg.build")
    asyncio.run(runner.run(node))

    assert runner.env.get("DFM_BASE_RUNDIR") == base_rundir_path


def test_base_rundir_nonexistent_base(tmpdir):
    """base_rundir pointing to a nonexistent directory is a no-op (no crash)."""
    local_dir = str(tmpdir.mkdir("local"))

    # base_rundir that doesn't exist -- tasks should just run locally
    r, n = _run_flow(local_dir, SIMPLE_FLOW, "pkg.build",
                     rundir=os.path.join(local_dir, "rundir"),
                     base_rundir="/nonexistent/path/rundir")
    assert r.status == 0
    assert n.result.base_hit is False
    assert n.result.changed is True


COMPOUND_FLOW = """\
package:
  name: pkg
  tasks:
  - name: compound
    body:
    - name: step1
      uses: std.CreateFile
      with:
        filename: step1.txt
        content: "step1"
    - name: step2
      uses: std.CreateFile
      needs: [step1]
      with:
        filename: step2.txt
        content: "step2"
  - name: entry
    uses: std.Null
    passthrough: all
    needs: [compound]
"""


def test_base_rundir_satisfies_compound_task(tmpdir):
    """A compound task satisfied from base-rundir should not create a local directory."""
    base_dir = str(tmpdir.mkdir("base"))
    local_dir = str(tmpdir.mkdir("local"))

    # Phase 1: populate the base rundir
    r1, _ = _run_flow(base_dir, COMPOUND_FLOW, "pkg.entry",
                       rundir=os.path.join(base_dir, "rundir"))
    assert r1.status == 0

    # Verify the compound wrote exec_data in the base rundir
    compound_dir = os.path.join(base_dir, "rundir", "pkg.compound")
    assert os.path.isdir(compound_dir)
    exec_files = [f for f in os.listdir(compound_dir) if f.endswith(".exec_data.json")]
    # Should have exec_data for compound itself plus its subtasks
    compound_exec = [f for f in exec_files if "compound.exec_data" in f or f.startswith("pkg.compound.exec_data")]
    assert len(compound_exec) > 0, "Compound task should write its own exec_data; found: %s" % exec_files

    # Phase 2: run with base-rundir -- compound should be satisfied, no local directory
    r2, n2 = _run_flow(local_dir, COMPOUND_FLOW, "pkg.entry",
                        rundir=os.path.join(local_dir, "rundir"),
                        base_rundir=os.path.join(base_dir, "rundir"))
    assert r2.status == 0

    # The compound directory should NOT exist in the local rundir
    local_compound_dir = os.path.join(local_dir, "rundir", "pkg.compound")
    assert not os.path.isdir(local_compound_dir), \
        "Compound task should be satisfied from base-rundir, not create a local directory"
