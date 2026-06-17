import os
import sys
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from dv_flow.mgr.ext_rgy import ExtRgy
from .task_listener_test import TaskListenerTest
from .marker_collector import MarkerCollector
from dv_flow.mgr.task_data import SeverityE


@pytest.fixture(autouse=True)
def reset_extrgy():
    """Reset the ExtRgy singleton, sys.modules, sys.path, and MAKEFLAGS before each test to prevent state leakage"""
    # Save original sys.modules keys and sys.path
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    
    # Clear MAKEFLAGS to avoid jobserver issues - don't save/restore it
    # because the jobserver FIFO may not exist anymore
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']
    
    # Reset the singleton instance
    ExtRgy._inst = None
    yield
    # Clean up after test
    ExtRgy._inst = None
    
    # Remove any modules that were added during the test
    added_modules = set(sys.modules.keys()) - original_modules
    for mod_name in added_modules:
        del sys.modules[mod_name]
    
    # Restore sys.path
    sys.path[:] = original_path
    
    # Clear MAKEFLAGS again after test to prevent FIFO references from leaking
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']


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
    runner = TaskSetRunner(os.path.join(tmpdir, "rundir"), builder=builder)

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
    loader = PackageLoader(marker_listeners=[marker])
    pkg = loader.load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
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
    loader = PackageLoader(marker_listeners=[marker])
    pkg = loader.load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir, builder=builder)
    entry = builder.mkTaskNode("p1.sh1")
    output = asyncio.run(runner.run(entry))
    assert runner.status == 0
    out_file = os.path.join(rundir, "p1.sh1/out.txt")
    assert os.path.isfile(out_file)
    with open(out_file, "r") as fp:
        line = fp.read().strip()
        assert line == "override,m1,e2"


# ---------------------------------------------------------------------------
# Script <-> Dataflow I/O contract (data_io / DFM_*)
# ---------------------------------------------------------------------------

def _run(tmpdir, flow_dv, task, raise_on_marker=True):
    flow_path = os.path.join(tmpdir, "flow.dv")
    with open(flow_path, "w") as f:
        f.write(flow_dv)
    rundir = os.path.join(tmpdir, "rundir")
    listeners = []
    if raise_on_marker:
        def marker(marker):
            raise Exception("Marker: %s" % marker)
        listeners = [marker]
    loader = PackageLoader(marker_listeners=listeners)
    pkg = loader.load(flow_path)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
    runner = TaskSetRunner(rundir, builder=builder)
    entry = builder.mkTaskNode(task)
    output = asyncio.run(runner.run(entry))
    return runner, builder, entry, output, rundir


def test_dfm_output_fileset(tmpdir):
    """A shell task emits a std.FileSet via $DFM_OUTPUT."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: gen
    shell: bash
    run: |
      echo "content" > gen.sv
      echo '{"type":"std.FileSet","filetype":"verilogSource","basedir":".","files":["gen.sv"]}' >> "$DFM_OUTPUT"
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.gen")
    assert runner.status == 0
    fs = [o for o in output.output if getattr(o, "type", None) == "std.FileSet"]
    assert len(fs) == 1
    assert fs[0].files == ["gen.sv"]
    assert fs[0].basedir == os.path.join(rundir, "p1.gen")
    assert fs[0].filetype == "verilogSource"


def test_dfm_output_fileset_consumed_downstream(tmpdir):
    """Downstream task consuming std.FileSet sees the emitted fileset."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: gen
    shell: bash
    produces: [{type: std.FileSet}]
    run: |
      echo "content" > gen.sv
      echo '{"type":"std.FileSet","filetype":"verilogSource","basedir":".","files":["gen.sv"]}' >> "$DFM_OUTPUT"
  - name: consume
    shell: bash
    needs: [gen]
    consumes: [{type: std.FileSet}]
    run: |
      python3 -c "import json,os; d=json.load(open(os.environ['DFM_INPUTS'])); \
        files=[f for it in d if it.get('type')=='std.FileSet' for f in it.get('files',[])]; \
        open('seen.txt','w').write(','.join(files))"
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.consume")
    assert runner.status == 0
    seen = os.path.join(rundir, "p1.consume/seen.txt")
    assert os.path.isfile(seen)
    with open(seen) as fp:
        assert fp.read().strip() == "gen.sv"


def test_dfm_env_roundtrip(tmpdir):
    """$DFM_ENV from an upstream task lands in a downstream task's environment."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: up
    shell: bash
    run: |
      echo "GEN_OK=1" >> "$DFM_ENV"
  - name: down
    shell: bash
    needs: [up]
    run: |
      echo -n "$GEN_OK" > out.txt
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.down")
    assert runner.status == 0
    out_file = os.path.join(rundir, "p1.down/out.txt")
    assert os.path.isfile(out_file)
    with open(out_file) as fp:
        assert fp.read().strip() == "1"


def test_dfm_param_scalars(tmpdir):
    """DFM_PARAM_* exposes scalars verbatim and lists as compact JSON."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: t
    shell: bash
    with:
      top: {type: str, value: soc_top}
      seeds: {type: list, value: [1, 2, 3]}
    run: |
      echo -n "$DFM_PARAM_TOP|$DFM_PARAM_SEEDS" > out.txt
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.t")
    assert runner.status == 0
    with open(os.path.join(rundir, "p1.t/out.txt")) as fp:
        assert fp.read().strip() == "soc_top|[1,2,3]"


def test_dfm_markers(tmpdir):
    """A script-emitted error marker surfaces with its location; status unaffected."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: t
    shell: bash
    run: |
      echo '{"severity":"error","msg":"synthesis failed","loc":{"path":"top.sv","line":10}}' >> "$DFM_MARKERS"
      exit 0
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.t", raise_on_marker=False)
    assert runner.status == 0  # D4: exit code authoritative
    markers = entry.result.markers
    assert any(m.msg == "synthesis failed" and m.severity == SeverityE.Error
               and m.loc is not None and m.loc.path == "top.sv" and m.loc.line == 10
               for m in markers)


def test_dfm_memento_persists(tmpdir):
    """A script-written memento is persisted into exec.json for the next run."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: t
    shell: bash
    run: |
      echo '{"hash":"abc123"}' > "$DFM_MEMENTO_OUT"
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.t")
    assert runner.status == 0
    assert entry.result.memento == {"hash": "abc123"}
    # Persisted to exec.json
    import glob, json as _json
    exec_files = glob.glob(os.path.join(rundir, "p1.t", "*.json"))
    found = False
    for ef in exec_files:
        with open(ef) as fp:
            data = _json.load(fp)
        if isinstance(data, dict) and data.get("result", {}).get("memento") == {"hash": "abc123"}:
            found = True
    assert found, "memento not persisted to exec.json"


def test_dfm_backward_compat(tmpdir):
    """A shell task that writes none of the DFM files behaves as before."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: t
    shell: bash
    run: |
      echo -n "hi" > out.txt
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.t")
    assert runner.status == 0
    assert output.output == []
    with open(os.path.join(rundir, "p1.t/out.txt")) as fp:
        assert fp.read() == "hi"


def test_dfm_out_cli_roundtrip(tmpdir):
    """End-to-end: a shell task uses the dfm-out helper (resolved via PATH)."""
    flow_dv = """
package:
  name: p1
  tasks:
  - name: gen
    shell: bash
    produces: [{type: std.FileSet}]
    run: |
      echo "content" > gen.sv
      dfm-out fileset --filetype verilogSource gen.sv
      dfm-out env GEN_OK=1
  - name: consume
    shell: bash
    needs: [gen]
    consumes: [{type: std.FileSet}]
    run: |
      echo -n "$GEN_OK" > env.txt
      python3 -c "import json,os; d=json.load(open(os.environ['DFM_INPUTS'])); \
        files=[f for it in d if it.get('type')=='std.FileSet' for f in it.get('files',[])]; \
        open('seen.txt','w').write(','.join(files))"
"""
    runner, builder, entry, output, rundir = _run(tmpdir, flow_dv, "p1.consume")
    assert runner.status == 0
    with open(os.path.join(rundir, "p1.consume/seen.txt")) as fp:
        assert fp.read().strip() == "gen.sv"
    with open(os.path.join(rundir, "p1.consume/env.txt")) as fp:
        assert fp.read().strip() == "1"
