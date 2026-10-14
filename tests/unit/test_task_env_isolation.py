"""A task's std.Env inputs are ITS environment, never the run's.

Regression: ExecCallable used to merge a task's std.Env inputs into the run's
shared env dict in place, so they leaked into every task that ran alongside
or after it (seen as a Verilator-only cocotb setting reaching a concurrent
Icarus run, which then hung).
"""
import os
import json
import asyncio
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner

PROBE = '''
import os, json
from dv_flow.mgr import TaskDataResult

async def Probe(ctxt, input):
    seen = {k: ctxt.env.get(k) for k in ("ISO_A", "ISO_B")}
    with open(os.path.join(input.rundir, "seen.json"), "w") as fp:
        json.dump(seen, fp)
    return TaskDataResult()
'''

FLOW = '''
package:
  name: p1
  tasks:
  - name: env_a
    uses: std.SetEnv
    with: { setenv: { ISO_A: "a" } }
  - name: env_b
    uses: std.SetEnv
    with: { setenv: { ISO_B: "b" } }
  - name: ta
    shell: pytask
    run: probe.py::Probe
    needs: [env_a]
  - name: tb
    shell: pytask
    run: probe.py::Probe
    needs: [env_b]
  # Runs after both, and is given no std.Env of its own.
  - name: tc
    shell: pytask
    run: probe.py::Probe
    needs: [ta, tb]
  - root: top
    needs: [tc]
'''


def _seen(rundir, task):
    with open(os.path.join(rundir, "p1.%s" % task, "seen.json")) as fp:
        return json.load(fp)


def test_std_env_does_not_leak_between_tasks(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    with open(os.path.join(tmpdir, "probe.py"), "w") as fp:
        fp.write(PROBE)
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as fp:
        fp.write(FLOW)

    loader = PackageLoader()
    pkg = loader.load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir, builder=builder)
    asyncio.run(runner.run(builder.mkTaskNode("p1.top")))
    assert runner.status == 0

    assert _seen(rundir, "ta") == {"ISO_A": "a", "ISO_B": None}
    assert _seen(rundir, "tb") == {"ISO_A": None, "ISO_B": "b"}
    assert _seen(rundir, "tc") == {"ISO_A": None, "ISO_B": None}
