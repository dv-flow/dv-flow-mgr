import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from .task_listener_test import TaskListenerTest
from .marker_collector import MarkerCollector

def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo
    tasks:
    - name: libfoo
      body:
      - name: build
        shell: bash
        rundir: inherit
        run: |
          make -C $TASK_RUNDIR -f $TASK_SRCDIR/Makefile
      - name: collect
        uses: std.FileSet
        rundir: inherit
        needs: [build]
        with:
          base: ${{ rundir }}
          include: "libfoo.so"
          type: sharedLibrary
"""
    makefile = """
SRCDIR:=$(dir $(abspath $(lastword $(MAKEFILE_LIST))))
all: libfoo.so

libfoo.so : $(SRCDIR)/foo.c
\t$(CC) -shared -fPIC -o $@ $<
"""

    foo_c = """
void foo() {
}
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    with open(os.path.join(tmpdir, "Makefile"), "w") as f:
        f.write(makefile)

    with open(os.path.join(tmpdir, "foo.c"), "w") as f:
        f.write(foo_c)

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(marker_listeners=[marker]).load(os.path.join(tmpdir, "flow.dv"))

    print("Package:\n%s\n" % pkg.dump())
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"))

    entry = builder.mkTaskNode("foo.libfoo")

    output = asyncio.run(runner.run(entry))

    assert runner.status == 0
    assert output is not None
    assert len(output.output) == 1
    len(output.output[0].files) == 1
    output.output[0].files[0] == "libfoo.so"