"""A result produced by one implementation never stands in for another's.

The same task name, rundir and params can be bound to a different
implementation from one run to the next -- `uses: hdlsim.${{ sim }}.SimImage`
under `--sim vlt` and then `--sim ivl`. The up-to-date check used to compare
only params and inputs, so the second run reused the first's result.
"""
import os
import asyncio
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner

IMPLS = '''
import os
from dv_flow.mgr import TaskDataResult

def _mark(input, which):
    with open(os.path.join(input.rundir, "impl.txt"), "w") as fp:
        fp.write(which)
    return TaskDataResult()

async def A(ctxt, input): return _mark(input, "A")
async def B(ctxt, input): return _mark(input, "B")
'''

FLOW = '''
package:
  name: p1
  with:
    impl: { type: str, value: "A" }
  tasks:
  - name: impl_A
    shell: pytask
    run: impls.py::A
  - name: impl_B
    shell: pytask
    run: impls.py::B
  - root: t
    uses: impl_${{ impl }}
'''


def _run(tmpdir, impl):
    rundir = os.path.join(tmpdir, "rundir")
    flow_path = os.path.join(tmpdir, "flow.dv")
    loader = PackageLoader(param_overrides={"impl": impl})
    pkg = loader.load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir=rundir, builder=builder)
    asyncio.run(runner.run(builder.mkTaskNode("p1.t")))
    assert runner.status == 0
    with open(os.path.join(rundir, "p1.t", "impl.txt")) as fp:
        return fp.read()


def test_changed_implementation_is_not_uptodate(tmpdir):
    with open(os.path.join(tmpdir, "impls.py"), "w") as fp:
        fp.write(IMPLS)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(FLOW)
    assert _run(tmpdir, "A") == "A"
    assert _run(tmpdir, "B") == "B"   # same name, params, inputs: new impl
    assert _run(tmpdir, "A") == "A"
