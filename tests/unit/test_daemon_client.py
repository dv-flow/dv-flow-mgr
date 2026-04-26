"""Tests for DaemonClientBackend: discovery, connection, proxy."""
import asyncio
import json
import os
import pytest
from dv_flow.mgr.daemon_client import DaemonClientBackend
from dv_flow.mgr.daemon import Daemon, DAEMON_STATE_FILE
from dv_flow.mgr.runner_config import RunnerConfig


class TestDiscovery:
    def test_no_daemon_json(self, tmp_path):
        """No daemon.json -> discover returns None."""
        client = DaemonClientBackend.discover(str(tmp_path))
        assert client is None

    def test_daemon_json_our_pid(self, tmp_path):
        """daemon.json with alive PID -> discover returns client."""
        dfm_dir = tmp_path / ".dfm"
        dfm_dir.mkdir()
        state = {"pid": os.getpid(), "socket": str(dfm_dir / "daemon.sock")}
        (dfm_dir / DAEMON_STATE_FILE).write_text(json.dumps(state))

        client = DaemonClientBackend.discover(str(tmp_path))
        assert client is not None

    def test_daemon_json_dead_pid(self, tmp_path):
        """daemon.json with dead PID -> discover returns None, stale file removed."""
        dfm_dir = tmp_path / ".dfm"
        dfm_dir.mkdir()
        state = {"pid": 99999999, "socket": str(dfm_dir / "daemon.sock")}
        state_path = dfm_dir / DAEMON_STATE_FILE
        state_path.write_text(json.dumps(state))

        client = DaemonClientBackend.discover(str(tmp_path))
        assert client is None
        assert not state_path.exists()  # stale file removed


class TestConnection:
    def test_start_no_daemon(self, tmp_path):
        """start() raises when no daemon is running."""
        client = DaemonClientBackend(str(tmp_path))
        with pytest.raises(RuntimeError, match="No daemon found"):
            asyncio.run(client.start())

    def test_start_stale_daemon(self, tmp_path):
        """start() raises and removes stale file."""
        dfm_dir = tmp_path / ".dfm"
        dfm_dir.mkdir()
        state = {"pid": 99999999, "socket": str(dfm_dir / "daemon.sock")}
        state_path = dfm_dir / DAEMON_STATE_FILE
        state_path.write_text(json.dumps(state))

        client = DaemonClientBackend(str(tmp_path))
        with pytest.raises(RuntimeError, match="Stale"):
            asyncio.run(client.start())
        assert not state_path.exists()

    def test_connect_to_live_daemon(self, tmp_path):
        """Connect to a real in-process daemon."""

        async def run():
            daemon = Daemon(project_root=str(tmp_path), config=RunnerConfig())
            dtask = asyncio.create_task(daemon.run())
            await asyncio.sleep(0.2)

            client = DaemonClientBackend(str(tmp_path))
            await client.start()
            assert client._connected is True

            await client.stop()
            await daemon.shutdown()
            dtask.cancel()
            try:
                await dtask
            except asyncio.CancelledError:
                pass

        asyncio.run(run())

    def test_is_remote(self, tmp_path):
        client = DaemonClientBackend(str(tmp_path))
        assert client.is_remote is True
