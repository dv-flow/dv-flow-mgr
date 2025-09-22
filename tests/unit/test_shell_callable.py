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

def test_command_env_ref(tmpdir):
    flow_dv = """
package:
    name: foo
    tasks:
    - name: entry
      shell: bash
      run: |
        echo "x${DISPLAY}x" > out.txt
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(marker_listeners=[marker]).load(os.path.join(tmpdir, "flow.dv"))

    print("Package:\n%s\n" % pkg.dump())
    env = os.environ.copy()
    env["DISPLAY"] = "Hello World!"
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"),
        env=env)
    
    runner = TaskSetRunner(
        os.path.join(tmpdir, "rundir"),
        env=env)

    entry = builder.mkTaskNode("foo.entry")

    output = asyncio.run(runner.run(entry))

    assert runner.status == 0
    assert output is not None
    assert os.path.isfile(os.path.join(rundir, "foo.entry/out.txt"))
    with open(os.path.join(rundir, "foo.entry/out.txt"), "r") as fp:
        line = fp.read().strip()
        assert line == "xHello World!x"

def test_dfm_env_var_ref(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      DISPLAY:
        type: str
        value: "Hello World!"
    tasks:
    - name: entry
      shell: bash
      run: |
        echo "x${{ env.DISPLAY }}x" > out.txt
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    env = os.environ.copy()
    env["DISPLAY"] = "Hello World!"

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(
        marker_listeners=[marker],
        env=env).load(os.path.join(tmpdir, "flow.dv"))

    print("Package:\n%s\n" % pkg.dump())
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"),
        env=env)
    
    runner = TaskSetRunner(
        os.path.join(tmpdir, "rundir"),
        env=env)

    entry = builder.mkTaskNode("foo.entry")

    output = asyncio.run(runner.run(entry))

    assert runner.status == 0
    assert output is not None
    assert os.path.isfile(os.path.join(rundir, "foo.entry/out.txt"))
    with open(os.path.join(rundir, "foo.entry/out.txt"), "r") as fp:
        line = fp.read().strip()
        assert line == "xHello World!x"

def test_package_var_ref(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      DISPLAY:
        type: str
        value: "Hello World!"
    tasks:
    - name: entry
      shell: bash
      run: |
        echo "x${{ DISPLAY }}x" > out.txt
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    env = os.environ.copy()

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(
        marker_listeners=[marker],
        env=env).load(os.path.join(tmpdir, "flow.dv"))

    print("Package:\n%s\n" % pkg.dump())
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(tmpdir, "rundir"),
        env=env)
    
    runner = TaskSetRunner(
        os.path.join(tmpdir, "rundir"),
        env=env)

    entry = builder.mkTaskNode("foo.entry")

    output = asyncio.run(runner.run(entry))

    assert runner.status == 0
    assert output is not None
    assert os.path.isfile(os.path.join(rundir, "foo.entry/out.txt"))
    with open(os.path.join(rundir, "foo.entry/out.txt"), "r") as fp:
        line = fp.read().strip()
        assert line == "xHello World!x"

def test_std_env_single(tmpdir):
    flow_dv = """
package:
  name: p1
  tasks:
  - name: env1
    uses: std.SetEnv
    with:
      setenv:
        FOO: "hello"
        BAR: "world"
  - name: sh1
    shell: bash
    needs: [env1]
    run: |
      echo -n "${FOO},${BAR}" > out.txt
"""
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(marker_listeners=[marker]).load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir, builder=builder)
    entry = builder.mkTaskNode("p1.sh1")
    output = asyncio.run(runner.run(entry))
    assert runner.status == 0
    out_file = os.path.join(rundir, "p1.sh1/out.txt")
    assert os.path.isfile(out_file)
    with open(out_file, "r") as fp:
        line = fp.read().strip()
        assert line == "hello,world"

def test_std_env_multi_override(tmpdir):
    flow_dv = """
package:
  name: p1
  tasks:
  - name: env1
    uses: std.SetEnv
    with:
      setenv:
        FOO: "base"
        MID: "m1"
  - name: env2
    uses: std.SetEnv
    needs: [env1]
    with:
      setenv:
        FOO: "override"
        END: "e2"
  - name: sh1
    shell: bash
    needs: [env1, env2]
    run: |
      echo -n "${FOO},${MID},${END}" > out.txt
"""
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as f:
        f.write(flow_dv)

    rundir = os.path.join(tmpdir, "rundir")
    def marker(marker):
        raise Exception("Marker: %s" % marker)
    pkg = PackageLoader(marker_listeners=[marker]).load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
    runner = TaskSetRunner(rundir, builder=builder)
    entry = builder.mkTaskNode("p1.sh1")
    output = asyncio.run(runner.run(entry))
    assert runner.status == 0
    out_file = os.path.join(rundir, "p1.sh1/out.txt")
    assert os.path.isfile(out_file)
    with open(out_file, "r") as fp:
        line = fp.read().strip()
        assert line == "override,m1,e2"
