#****************************************************************************
#* daemon_client.py
#*
#* DaemonClientBackend: discovers a running daemon and proxies
#* task execution over the Unix socket.
#*
#* Uses a single background reader task to multiplex responses from the
#* daemon, routing each response to the correct caller by message id.
#* This allows multiple execute_task() calls to be in flight concurrently.
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Optional

from .runner_backend import RunnerBackend, TaskExecRequest
from .daemon import DAEMON_STATE_FILE, is_daemon_alive
from .task_data import TaskDataResult


_log = logging.getLogger("DaemonClient")


class DaemonClientBackend(RunnerBackend):
    """Runner backend that proxies task execution to a running daemon.

    A single background reader coroutine owns the StreamReader and
    dispatches incoming responses to the correct waiting Future by
    matching the ``id`` field.  This avoids the "readuntil() called
    while another coroutine is already waiting" error when multiple
    tasks are in flight concurrently.

    Writes are serialized with an asyncio.Lock since multiple
    coroutines may call execute_task() at the same time.
    """

    def __init__(self, project_root: str):
        self._project_root = project_root
        self._state_path = os.path.join(project_root, ".dfm", DAEMON_STATE_FILE)
        self._socket_path: Optional[str] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

        # Multiplexing state
        self._pending: Dict[str, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._write_lock: asyncio.Lock = asyncio.Lock()

    @property
    def is_remote(self) -> bool:
        return True

    async def start(self) -> None:
        """Discover and connect to a running daemon."""
        if not os.path.isfile(self._state_path):
            raise RuntimeError(
                "No daemon found (no %s). Start one with: dfm daemon start"
                % self._state_path
            )

        if not is_daemon_alive(self._state_path):
            _log.warning("Stale daemon.json (PID not alive), removing")
            try:
                os.unlink(self._state_path)
            except OSError:
                pass
            raise RuntimeError(
                "Stale daemon state file removed. "
                "Start a new daemon with: dfm daemon start"
            )

        with open(self._state_path) as f:
            state = json.load(f)
        self._socket_path = state.get("socket", "")
        if not self._socket_path:
            raise RuntimeError("daemon.json missing socket path")

        try:
            self._reader, self._writer = await asyncio.open_unix_connection(
                self._socket_path
            )
        except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
            raise RuntimeError(
                "Cannot connect to daemon socket %s: %s"
                % (self._socket_path, e)
            )

        # Ping/pong handshake (single request before the reader loop starts)
        ping = json.dumps({"method": "ping", "id": "init"}) + "\n"
        self._writer.write(ping.encode())
        await self._writer.drain()

        resp_line = await self._reader.readline()
        if not resp_line:
            raise RuntimeError("Daemon closed connection during handshake")
        resp = json.loads(resp_line.decode())
        if resp.get("result") != "pong":
            raise RuntimeError("Unexpected handshake response: %s" % resp)

        # Start the background reader that routes responses by id
        self._reader_task = asyncio.create_task(self._reader_loop())

        self._connected = True
        _log.info("Connected to daemon at %s", self._socket_path)

    async def stop(self) -> None:
        """Disconnect from the daemon, cancelling all inflight tasks first."""
        self._connected = False

        # Tell the daemon to cancel every request we're still waiting on.
        # This must happen before we tear down the reader/writer so the
        # daemon can route the cancel to workers.
        await self._cancel_inflight()

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Fail any still-pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("Client disconnected"))
        self._pending.clear()

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

    async def _cancel_inflight(self):
        """Send task.cancel for every pending request to the daemon."""
        if not self._writer:
            return
        pending_ids = list(self._pending.keys())
        if not pending_ids:
            return
        _log.info("Cancelling %d inflight task(s)", len(pending_ids))
        try:
            for rid in pending_ids:
                cancel_msg = json.dumps({
                    "method": "task.cancel",
                    "id": "cancel_%s" % rid,
                    "params": {"request_id": rid},
                }) + "\n"
                async with self._write_lock:
                    self._writer.write(cancel_msg.encode())
                    await self._writer.drain()
        except Exception as e:
            _log.warning("Error sending cancel messages: %s", e)

    async def execute_task(self, request: TaskExecRequest) -> TaskDataResult:
        """Submit a task to the daemon and wait for the result."""
        if not self._connected:
            raise RuntimeError("Not connected to daemon")

        request_id = uuid.uuid4().hex[:12]

        # Register a future for this request
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        # Build and send the request (serialized via write lock)
        submit = {
            "method": "task.submit",
            "id": request_id,
            "params": {
                "request_id": request_id,
                "name": request.name,
                "callable_spec": request.callable_spec,
                "shell": request.shell,
                "body": request.body,
                "srcdir": request.srcdir,
                "rundir": request.rundir,
                "pythonpath": request.pythonpath,
                "params": request.params,
                "inputs": request.inputs,
                "env": request.env,
                "resource_class": request.resource_req.queue or "",
            },
        }

        async with self._write_lock:
            self._writer.write((json.dumps(submit) + "\n").encode())
            await self._writer.drain()

        # Wait for the background reader to deliver our response
        try:
            resp = await future
        finally:
            self._pending.pop(request_id, None)

        if isinstance(resp, dict) and "error" in resp:
            raise RuntimeError("Daemon error: %s" % resp["error"])

        result_data = resp.get("result", {}) if isinstance(resp, dict) else {}

        from .task_exec_serialize import deserialize_result
        return deserialize_result(result_data)

    async def acquire_slot(self) -> None:
        pass

    async def release_slot(self) -> None:
        pass

    async def cancel_inflight(self) -> None:
        """Cancel all tasks currently in flight on the daemon."""
        await self._cancel_inflight()

    # -- background reader --

    async def _reader_loop(self):
        """Read lines from the daemon and route each to the matching Future."""
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    _log.warning("Daemon closed connection")
                    break

                try:
                    msg = json.loads(line.decode())
                except json.JSONDecodeError:
                    _log.warning("Bad JSON from daemon: %s", line[:80])
                    continue

                msg_id = msg.get("id")
                if msg_id and msg_id in self._pending:
                    fut = self._pending[msg_id]
                    if not fut.done():
                        fut.set_result(msg)
                else:
                    _log.debug(
                        "Unmatched response (id=%s): %s",
                        msg_id, str(msg)[:120],
                    )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            _log.error("Reader loop error: %s", e)
        finally:
            # Fail any pending futures so callers don't hang
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(
                        RuntimeError("Daemon connection lost")
                    )

    # -- static discovery --

    @staticmethod
    def discover(project_root: str) -> Optional['DaemonClientBackend']:
        """Try to discover a running daemon. Returns None if not found."""
        state_path = os.path.join(project_root, ".dfm", DAEMON_STATE_FILE)
        if not os.path.isfile(state_path):
            return None
        if not is_daemon_alive(state_path):
            try:
                os.unlink(state_path)
            except OSError:
                pass
            return None
        return DaemonClientBackend(project_root)
