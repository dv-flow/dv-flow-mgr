"""Tests for the Daemon: in-process start/stop, state file, client protocol."""
import asyncio
import json
import os
import pytest
from dv_flow.mgr.daemon import Daemon, is_daemon_alive, DAEMON_STATE_FILE
from dv_flow.mgr.runner_config import RunnerConfig


class TestDaemonLifecycle:
    def test_state_file_written_and_removed(self, tmp_path):
        """Start daemon, verify state file, stop, verify removed."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            # Start in background
            task = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)  # let it start

            # Verify state file
            state_path = os.path.join(str(tmp_path), ".dfm", DAEMON_STATE_FILE)
            assert os.path.isfile(state_path)
            with open(state_path) as f:
                state = json.load(f)
            assert state["pid"] == os.getpid()
            assert "socket" in state
            assert "worker_port" in state

            # Stop
            await daemon.shutdown()
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # State file should be removed
            assert not os.path.isfile(state_path)

        asyncio.run(run())

    def test_client_ping_pong(self, tmp_path):
        """Connect client, send ping, receive pong."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            task = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)

            # Connect via Unix socket
            socket_path = daemon.socket_path
            reader, writer = await asyncio.open_unix_connection(socket_path)

            # Send ping
            msg = json.dumps({"method": "ping", "id": "1"}) + "\n"
            writer.write(msg.encode())
            await writer.drain()

            resp_line = await reader.readline()
            resp = json.loads(resp_line.decode())
            assert resp["result"] == "pong"
            assert resp["id"] == "1"

            writer.close()
            await writer.wait_closed()

            await daemon.shutdown()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())

    def test_client_status_get(self, tmp_path):
        """Get status from daemon."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            task = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)

            reader, writer = await asyncio.open_unix_connection(daemon.socket_path)

            msg = json.dumps({"method": "status.get", "id": "s1"}) + "\n"
            writer.write(msg.encode())
            await writer.drain()

            resp_line = await reader.readline()
            resp = json.loads(resp_line.decode())
            assert "result" in resp
            assert resp["result"]["pid"] == os.getpid()
            assert isinstance(resp["result"]["workers"], list)

            writer.close()
            await writer.wait_closed()

            await daemon.shutdown()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())

    def test_client_shutdown_command(self, tmp_path):
        """Send shutdown via client, daemon stops."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            task = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)

            reader, writer = await asyncio.open_unix_connection(daemon.socket_path)

            msg = json.dumps({"method": "shutdown", "id": "x1"}) + "\n"
            writer.write(msg.encode())
            await writer.drain()

            resp_line = await reader.readline()
            resp = json.loads(resp_line.decode())
            assert resp["result"] == "shutting_down"

            writer.close()
            await writer.wait_closed()

            # Wait for daemon to actually stop
            await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())


class TestIsDaemonAlive:
    def test_no_file(self, tmp_path):
        assert is_daemon_alive(str(tmp_path / "nonexistent.json")) is False

    def test_our_pid(self, tmp_path):
        state_path = tmp_path / "daemon.json"
        state_path.write_text(json.dumps({"pid": os.getpid()}))
        assert is_daemon_alive(str(state_path)) is True

    def test_dead_pid(self, tmp_path):
        state_path = tmp_path / "daemon.json"
        # Use a PID that almost certainly doesn't exist
        state_path.write_text(json.dumps({"pid": 99999999}))
        assert is_daemon_alive(str(state_path)) is False

    def test_invalid_json(self, tmp_path):
        state_path = tmp_path / "daemon.json"
        state_path.write_text("not json")
        assert is_daemon_alive(str(state_path)) is False


class TestDaemonCancellation:
    def test_cancel_pending_task(self, tmp_path):
        """Client sends task.cancel for a pending task."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            task = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)

            reader, writer = await asyncio.open_unix_connection(daemon.socket_path)

            # Submit a task (no workers, so it will pend)
            submit = json.dumps({
                "method": "task.submit",
                "id": "s1",
                "params": {"request_id": "req42", "name": "my_task"},
            }) + "\n"
            writer.write(submit.encode())
            await writer.drain()
            await asyncio.sleep(0.1)

            assert daemon.pool.pending_count == 1

            # Cancel it
            cancel = json.dumps({
                "method": "task.cancel",
                "id": "c1",
                "params": {"request_id": "req42"},
            }) + "\n"
            writer.write(cancel.encode())
            await writer.drain()

            resp_line = await reader.readline()
            resp = json.loads(resp_line.decode())
            assert resp.get("result") == "cancelled"

            assert daemon.pool.pending_count == 0

            writer.close()
            await writer.wait_closed()
            await daemon.shutdown()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())

    def test_client_disconnect_cancels_inflight(self, tmp_path):
        """Client disconnecting cancels all its inflight tasks."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            task = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)

            reader, writer = await asyncio.open_unix_connection(daemon.socket_path)

            # Submit a task
            submit = json.dumps({
                "method": "task.submit",
                "id": "s1",
                "params": {"request_id": "req99", "name": "task_will_cancel"},
            }) + "\n"
            writer.write(submit.encode())
            await writer.drain()
            await asyncio.sleep(0.1)

            assert daemon.pool.pending_count == 1

            # Close the client connection abruptly
            writer.close()
            await writer.wait_closed()
            await asyncio.sleep(0.3)

            # Daemon should have auto-cancelled the pending task
            assert daemon.pool.pending_count == 0

            await daemon.shutdown()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
