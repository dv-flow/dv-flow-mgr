"""End-to-end tests: dfm run with a live daemon and worker pool.

These tests start an in-process daemon, let it spawn worker subprocesses,
then run tasks through the full orchestrator -> daemon -> worker pipeline
and verify correct results.
"""
import asyncio
import os
import sys
import json
import pytest

from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.daemon import Daemon
from dv_flow.mgr.daemon_client import DaemonClientBackend
from dv_flow.mgr.runner_config import RunnerConfig


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
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path
    if 'MAKEFLAGS' in os.environ:
        del os.environ['MAKEFLAGS']


def _write_flow(tmpdir, flow_dv, extra_files=None):
    """Write a flow.dv and any extra Python files into tmpdir."""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    if extra_files:
        for name, content in extra_files.items():
            with open(os.path.join(tmpdir, name), "w") as f:
                f.write(content)


class TestDaemonEndToEnd:
    """Tests that start a daemon, connect via DaemonClientBackend, and
    run real tasks through workers."""

    def test_pytask_via_daemon(self, tmp_path):
        """A simple pytask (std.Message) executes through the daemon."""
        projdir = str(tmp_path / "proj")
        os.makedirs(projdir)
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir)

        _write_flow(projdir, """
package:
  name: test_daemon_pytask
  tasks:
  - name: hello
    scope: root
    uses: std.Message
    with:
      msg: "hello from daemon"
""")

        async def run():
            daemon = Daemon(project_root=projdir, config=RunnerConfig())
            dtask = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.3)

            try:
                loader, pkg = loadProjPkgDef(projdir)
                assert pkg is not None

                backend = DaemonClientBackend(projdir)
                await backend.start()

                builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
                runner = TaskSetRunner(rundir=rundir, builder=builder, backend=backend, nproc=2)

                task = builder.mkTaskNode("test_daemon_pytask.hello")
                result = await runner.run(task)

                assert runner.status == 0
                assert result is not None

                await backend.stop()
            finally:
                await daemon.shutdown()
                await asyncio.sleep(0.2)
                dtask.cancel()
                try:
                    await dtask
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())

    def test_shell_task_via_daemon(self, tmp_path):
        """A shell task executes through the daemon and creates output."""
        projdir = str(tmp_path / "proj")
        os.makedirs(projdir)
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir)

        _write_flow(projdir, """
package:
  name: test_daemon_shell
  tasks:
  - name: greet
    scope: root
    shell: bash
    run: |
      echo "hello from worker" > ${{ rundir }}/greeting.txt
""")

        async def run():
            daemon = Daemon(project_root=projdir, config=RunnerConfig())
            dtask = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.3)

            try:
                loader, pkg = loadProjPkgDef(projdir)
                assert pkg is not None

                backend = DaemonClientBackend(projdir)
                await backend.start()

                builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
                runner = TaskSetRunner(rundir=rundir, builder=builder, backend=backend, nproc=2)

                task = builder.mkTaskNode("test_daemon_shell.greet")
                result = await runner.run(task)

                assert runner.status == 0

                # Verify the shell task actually ran and wrote output
                greeting_files = []
                for root, dirs, files in os.walk(rundir):
                    for f in files:
                        if f == "greeting.txt":
                            greeting_files.append(os.path.join(root, f))
                assert len(greeting_files) > 0, "greeting.txt not found in rundir"
                with open(greeting_files[0]) as f:
                    assert "hello from worker" in f.read()

                await backend.stop()
            finally:
                await daemon.shutdown()
                await asyncio.sleep(0.2)
                dtask.cancel()
                try:
                    await dtask
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())

    def test_task_chain_via_daemon(self, tmp_path):
        """Two tasks with a dependency: upstream produces a FileSet,
        downstream consumes it."""
        projdir = str(tmp_path / "proj")
        os.makedirs(projdir)
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir)

        # Create a source file for the FileSet
        srcdir = os.path.join(projdir, "src")
        os.makedirs(srcdir)
        with open(os.path.join(srcdir, "hello.sv"), "w") as f:
            f.write("module hello; endmodule\n")

        _write_flow(projdir, """
package:
  name: test_daemon_chain
  tasks:
  - name: sources
    uses: std.FileSet
    with:
      base: src
      include: "*.sv"
      type: verilogSource

  - name: report
    scope: root
    needs: [sources]
    shell: bash
    run: |
      echo "got inputs" > ${{ rundir }}/report.txt
""")

        async def run():
            daemon = Daemon(project_root=projdir, config=RunnerConfig())
            dtask = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.3)

            try:
                loader, pkg = loadProjPkgDef(projdir)
                assert pkg is not None

                backend = DaemonClientBackend(projdir)
                await backend.start()

                builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
                runner = TaskSetRunner(rundir=rundir, builder=builder, backend=backend, nproc=4)

                task = builder.mkTaskNode("test_daemon_chain.report")
                result = await runner.run(task)

                assert runner.status == 0

                # Verify downstream task ran
                report_files = []
                for root, dirs, files in os.walk(rundir):
                    for f in files:
                        if f == "report.txt":
                            report_files.append(os.path.join(root, f))
                assert len(report_files) > 0, "report.txt not found"
                with open(report_files[0]) as f:
                    assert "got inputs" in f.read()

                await backend.stop()
            finally:
                await daemon.shutdown()
                await asyncio.sleep(0.2)
                dtask.cancel()
                try:
                    await dtask
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())

    def test_daemon_status_while_running(self, tmp_path):
        """Verify daemon status RPC returns meaningful data."""
        projdir = str(tmp_path / "proj")
        os.makedirs(projdir)

        _write_flow(projdir, """
package:
  name: test_status
  tasks:
  - name: noop
    uses: std.Message
    with:
      msg: "status check"
""")

        async def run():
            daemon = Daemon(project_root=projdir, config=RunnerConfig())
            dtask = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.3)

            try:
                # Check status via Unix socket
                reader, writer = await asyncio.open_unix_connection(daemon.socket_path)
                msg = json.dumps({"method": "status.get", "id": "s1"}) + "\n"
                writer.write(msg.encode())
                await writer.drain()

                resp_line = await reader.readline()
                resp = json.loads(resp_line.decode())

                assert "result" in resp
                assert resp["result"]["pid"] == os.getpid()
                assert isinstance(resp["result"]["workers"], list)
                assert "pending_tasks" in resp["result"]

                writer.close()
                await writer.wait_closed()
            finally:
                await daemon.shutdown()
                await asyncio.sleep(0.2)
                dtask.cancel()
                try:
                    await dtask
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())

    def test_local_without_daemon(self, tmp_path):
        """Verify local execution still works when no daemon is running."""
        projdir = str(tmp_path / "proj")
        os.makedirs(projdir)
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir)

        _write_flow(projdir, """
package:
  name: test_local
  tasks:
  - name: hello
    scope: root
    uses: std.Message
    with:
      msg: "local only"
""")

        loader, pkg = loadProjPkgDef(projdir)
        assert pkg is not None

        # No daemon, no backend -- should run locally
        builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
        runner = TaskSetRunner(rundir=rundir, builder=builder, nproc=2)

        task = builder.mkTaskNode("test_local.hello")
        result = asyncio.run(runner.run(task))

        assert runner.status == 0
        assert result is not None

    def test_multi_output_via_daemon(self, tmp_path):
        """A pytask producing multiple output items (e.g. two FileSets)
        must have all items reach downstream tasks without dedup loss.

        Regression test for a bug where all FileSet outputs from a remote
        task got the same (src=None, seq=-1) key, causing get_in_params
        to drop all but the first."""
        projdir = str(tmp_path / "proj")
        os.makedirs(projdir)
        rundir = str(tmp_path / "rundir")
        os.makedirs(rundir)

        _write_flow(projdir, """
package:
  name: test_multi_out
  tasks:
  - name: producer
    shell: pytask
    run: test_multi_out_impl.produce

  - name: consumer
    scope: root
    needs: [producer]
    shell: pytask
    run: test_multi_out_impl.consume
""", extra_files={
            "test_multi_out_impl.py": """
from dv_flow.mgr import TaskDataResult, FileSet

async def produce(ctxt, input):
    return TaskDataResult(
        status=0,
        changed=True,
        output=[
            FileSet(filetype="verilogIncDir", basedir="/incdir_a"),
            FileSet(filetype="simLib", basedir="/lib_b"),
            FileSet(filetype="verilogSource", basedir="/src_c", files=["x.sv"]),
        ],
    )

async def consume(ctxt, input):
    types = sorted(getattr(item, "filetype", "?") for item in input.inputs)
    # Write the types seen so the test can verify
    import os
    with open(os.path.join(input.rundir, "seen.txt"), "w") as f:
        f.write(",".join(types))
    return TaskDataResult(status=0, changed=True, output=[])
"""
        })

        async def run():
            daemon = Daemon(project_root=projdir, config=RunnerConfig())
            dtask = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.3)

            try:
                loader, pkg = loadProjPkgDef(projdir)
                assert pkg is not None

                backend = DaemonClientBackend(projdir)
                await backend.start()

                builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
                runner = TaskSetRunner(
                    rundir=rundir, builder=builder, backend=backend, nproc=4
                )

                task = builder.mkTaskNode("test_multi_out.consumer")
                result = await runner.run(task)

                assert runner.status == 0

                # Find the seen.txt written by the consumer
                seen_files = []
                for root, dirs, files in os.walk(rundir):
                    for f in files:
                        if f == "seen.txt":
                            seen_files.append(os.path.join(root, f))
                assert len(seen_files) > 0, "seen.txt not found in rundir"

                with open(seen_files[0]) as f:
                    seen = f.read().strip()
                types = seen.split(",")

                # All three FileSet types must be present
                assert "simLib" in types, (
                    "simLib FileSet was lost (dedup bug); got: %s" % types
                )
                assert "verilogIncDir" in types, (
                    "verilogIncDir missing; got: %s" % types
                )
                assert "verilogSource" in types, (
                    "verilogSource missing; got: %s" % types
                )
                assert len(types) == 3, (
                    "Expected 3 items, got %d: %s" % (len(types), types)
                )

                await backend.stop()
            finally:
                await daemon.shutdown()
                await asyncio.sleep(0.2)
                dtask.cancel()
                try:
                    await dtask
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())
