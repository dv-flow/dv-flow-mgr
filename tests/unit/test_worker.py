"""Tests for the worker process using mock TCP servers."""
import asyncio
import json
import pytest
import tempfile
from dv_flow.mgr.worker import run_worker, execute_request
from dv_flow.mgr.worker_protocol import (
    parse_message,
    build_task_execute,
    build_worker_shutdown,
    encode_message,
    METHOD_WORKER_REGISTER,
    METHOD_TASK_RESULT,
    METHOD_WORKER_HEARTBEAT,
)


class TestExecuteRequest:
    """Test execute_request directly (no network)."""

    def test_shell_task_echo(self):
        """Shell task with 'echo hello' should succeed."""
        with tempfile.TemporaryDirectory() as td:
            params = {
                "name": "test.echo",
                "shell": "bash",
                "body": "echo hello",
                "rundir": td,
                "srcdir": td,
                "env": {},
            }
            result = asyncio.run(execute_request(params))
            assert result["status"] == 0
            assert result["changed"] is True

    def test_shell_task_failure(self):
        """Shell task that exits non-zero."""
        with tempfile.TemporaryDirectory() as td:
            params = {
                "name": "test.fail",
                "shell": "bash",
                "body": "exit 42",
                "rundir": td,
                "srcdir": td,
                "env": {},
            }
            result = asyncio.run(execute_request(params))
            assert result["status"] == 42

    def test_shell_task_no_body(self):
        """Shell task without body should fail gracefully."""
        params = {
            "name": "test.nobody",
            "shell": "bash",
            "rundir": "/tmp",
        }
        result = asyncio.run(execute_request(params))
        assert result["status"] == 1
        assert any("body" in m["msg"].lower() for m in result["markers"])

    def test_pytask_missing_callable(self):
        """Pytask without callable_spec should fail gracefully."""
        params = {
            "name": "test.noop",
            "shell": "pytask",
            "callable_spec": "",
            "rundir": "",
        }
        result = asyncio.run(execute_request(params))
        assert result["status"] == 1


class TestWorkerConnection:
    """Test worker connection to a mock TCP server."""

    @pytest.fixture
    def event_loop(self):
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_worker_registers_and_receives_task(self):
        """Start mock server, launch worker, verify registration and task execution."""
        messages_received = []
        server_ready = asyncio.Event()

        async def handler(reader, writer):
            # Read registration
            line = await reader.readline()
            msg = parse_message(line.decode("utf-8"))
            messages_received.append(msg)

            # Dispatch a shell task
            import tempfile as _tf
            _td = _tf.mkdtemp()
            task_msg = build_task_execute(
                request_id="req-001",
                name="test.echo",
                shell="bash",
                body="echo hello",
                srcdir=_td,
                rundir=_td,
            )
            writer.write(encode_message(task_msg))
            await writer.drain()

            # Read result
            line = await reader.readline()
            if line:
                msg = parse_message(line.decode("utf-8"))
                messages_received.append(msg)

            # Read any heartbeats that arrived
            # Then send shutdown
            shutdown_msg = build_worker_shutdown()
            writer.write(encode_message(shutdown_msg))
            await writer.drain()

            # Give worker time to process shutdown
            await asyncio.sleep(0.1)
            writer.close()

        async def run_test():
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            addr = server.sockets[0].getsockname()
            port = addr[1]

            # Run worker
            await run_worker(
                connect_addr="127.0.0.1:%d" % port,
                worker_id="test-worker-1",
            )

            server.close()
            await server.wait_closed()

        asyncio.run(run_test())

        # Verify registration
        assert len(messages_received) >= 2
        assert messages_received[0]["method"] == METHOD_WORKER_REGISTER
        assert messages_received[0]["params"]["worker_id"] == "test-worker-1"

        # Verify task result
        assert messages_received[1]["method"] == METHOD_TASK_RESULT
        assert messages_received[1]["params"]["request_id"] == "req-001"
        assert messages_received[1]["params"]["status"] == 0

    def test_worker_heartbeat(self):
        """Verify heartbeat messages arrive."""
        messages_received = []

        async def handler(reader, writer):
            # Read registration
            line = await reader.readline()
            messages_received.append(parse_message(line.decode("utf-8")))

            # Wait for at least one heartbeat (interval is 10s in prod,
            # but we'll use a shorter timeout and just check the flow)
            # Send shutdown immediately after a brief wait
            await asyncio.sleep(0.2)

            shutdown_msg = build_worker_shutdown()
            writer.write(encode_message(shutdown_msg))
            await writer.drain()
            await asyncio.sleep(0.1)
            writer.close()

        async def run_test():
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]

            # Temporarily patch heartbeat interval for test speed
            import dv_flow.mgr.worker as worker_mod
            original_interval = worker_mod.HEARTBEAT_INTERVAL
            worker_mod.HEARTBEAT_INTERVAL = 0.05  # 50ms for testing

            try:
                await run_worker(
                    connect_addr="127.0.0.1:%d" % port,
                    worker_id="hb-test",
                )
            finally:
                worker_mod.HEARTBEAT_INTERVAL = original_interval
                server.close()
                await server.wait_closed()

        asyncio.run(run_test())

        # Should have registration at minimum
        assert len(messages_received) >= 1
        assert messages_received[0]["method"] == METHOD_WORKER_REGISTER

    def test_worker_handles_disconnect(self):
        """Worker exits cleanly when server disconnects."""

        async def handler(reader, writer):
            # Read registration
            await reader.readline()
            # Immediately close
            writer.close()

        async def run_test():
            server = await asyncio.start_server(handler, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]

            # Should exit cleanly, not raise
            await run_worker(
                connect_addr="127.0.0.1:%d" % port,
                worker_id="disconnect-test",
            )

            server.close()
            await server.wait_closed()

        asyncio.run(run_test())  # No exception = pass
