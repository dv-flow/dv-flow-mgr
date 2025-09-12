import os
import asyncio
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner

def _run_task(flow_path, rundir, task_name):
    pkg_def = PackageLoader().load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg_def, rundir=rundir)
    runner = TaskSetRunner(rundir=rundir, builder=builder)
    task = builder.mkTaskNode(task_name)
    return asyncio.run(runner.run(task)), runner

def test_setenv_basic(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)

    flow_dv = f"""
package:
  name: p1
  tasks:
  - name: env1
    uses: std.SetEnv
    with:
      setenv:
        FOO: "bar"
        BAZ: "baz"
"""
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as fp:
        fp.write(flow_dv)

    # First run
    out, runner = _run_task(flow_path, rundir, "p1.env1")
    assert runner.status == 0
    assert out.changed is True
    assert len(out.output) == 1
    env = out.output[0]
    assert env.type == "std.Env"
    assert env.vals["FOO"] == "bar"
    assert env.vals["BAZ"] == "baz"

    # Second run (no changes)
    out2, runner2 = _run_task(flow_path, rundir, "p1.env1")
    assert runner2.status == 0
    assert out2.changed is False

def test_setenv_glob_multi(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)

    # Create matching files
    for f in ["a.sv", "b.sv"]:
        with open(os.path.join(tmpdir, f), "w") as fp:
            fp.write("// file\n")

    flow_dv = f"""
package:
  name: p1
  tasks:
  - name: envg
    uses: std.SetEnv
    with:
      setenv:
        SV_FILES: "*.sv"
"""
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as fp:
        fp.write(flow_dv)

    out, runner = _run_task(flow_path, rundir, "p1.envg")
    assert runner.status == 0
    env = out.output[0]
    sv_val = env.vals["SV_FILES"]
    parts = sv_val.split(os.pathsep)
    assert len(parts) == 2
    assert all(os.path.isabs(p) for p in parts)
    basenames = set(os.path.basename(p) for p in parts)
    assert basenames == {"a.sv", "b.sv"}

    # Add another file and re-run
    with open(os.path.join(tmpdir, "c.sv"), "w") as fp:
        fp.write("// file\n")
    out2, runner2 = _run_task(flow_path, rundir, "p1.envg")
    assert runner2.status == 0
    assert out2.changed is True
    env2 = out2.output[0]
    parts2 = env2.vals["SV_FILES"].split(os.pathsep)
    basenames2 = set(os.path.basename(p) for p in parts2)
    assert basenames2 == {"a.sv", "b.sv", "c.sv"}

def test_setenv_glob_single(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)

    with open(os.path.join(tmpdir, "only.sv"), "w") as fp:
        fp.write("// file\n")

    flow_dv = f"""
package:
  name: p1
  tasks:
  - name: envs
    uses: std.SetEnv
    with:
      setenv:
        ONE: "only.sv"
        ONE_GLOB: "only.*"
"""
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as fp:
        fp.write(flow_dv)

    out, runner = _run_task(flow_path, rundir, "p1.envs")
    assert runner.status == 0
    env = out.output[0]
    # Non-glob preserved
    assert env.vals["ONE"] == "only.sv"
    # Glob expanded to absolute path
    assert os.path.isabs(env.vals["ONE_GLOB"])
    assert env.vals["ONE_GLOB"].endswith("only.sv")

def test_setenv_glob_nomatch_literal(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)

    flow_dv = f"""
package:
  name: p1
  tasks:
  - name: envnm
    uses: std.SetEnv
    with:
      setenv:
        NO_MATCH: "nofile_*.doesnotexist"
"""
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as fp:
        fp.write(flow_dv)

    out, runner = _run_task(flow_path, rundir, "p1.envnm")
    assert runner.status == 0
    env = out.output[0]
    assert env.vals["NO_MATCH"] == "nofile_*.doesnotexist"

    # Re-run unchanged
    out2, _ = _run_task(flow_path, rundir, "p1.envnm")
    assert out2.changed is False
