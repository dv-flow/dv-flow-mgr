#****************************************************************************
#* worker.py
#*
#* Worker process: connects to daemon, receives and executes tasks.
#*
#* The daemon sends a task as JSON with:
#*   - callable_spec: dotted path to the Python function (pytask)
#*   - shell/body: shell type and script text (shell tasks)
#*   - params: dict of task parameters
#*   - inputs: list of serialized input data items
#*   - pythonpath: extra sys.path entries
#*   - srcdir, rundir, env, memento
#*
#* The worker imports the callable, wraps params/inputs in
#* SimpleNamespace for attribute access, and calls the function.
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
import importlib
import json
import logging
import os
import platform
import sys
import types
import uuid
from typing import Any, Dict, Optional

from .worker_protocol import (
    METHOD_TASK_EXECUTE,
    METHOD_TASK_CANCEL,
    METHOD_WORKER_SHUTDOWN,
    build_worker_register,
    build_task_result,
    build_worker_heartbeat,
    encode_message,
    parse_message,
    ProtocolError,
)
from .task_data import TaskDataResult


class _WorkerRunnerShim:
    """Minimal runner-like object for worker-side TaskRunCtxt.

    Provides mkDataItem so task callables that call ctxt.mkDataItem()
    work correctly inside the worker process.  Uses the ExtRgy and
    PackageLoader to find types from installed packages.
    """

    def __init__(self):
        self._builder = None

    def _ensure_builder(self):
        if self._builder is None:
            from .ext_rgy import ExtRgy
            from .package_loader import PackageLoader
            rgy = ExtRgy.inst()
            loader = PackageLoader(rgy)
            # Create a real TaskGraphBuilder with a working loader
            from .task_graph_builder import TaskGraphBuilder
            self._builder = TaskGraphBuilder.__new__(TaskGraphBuilder)
            self._builder._loader = loader
            self._builder._type_m = {}
            self._builder._type_node_m = {}
            self._builder._rgy = rgy
            self._builder._log = logging.getLogger("WorkerBuilder")
            # Alias so mkDataItem can call self.loader
            self._builder.loader = loader

    def mkDataItem(self, type, **kwargs):
        self._ensure_builder()
        return self._builder.mkDataItem(type, **kwargs)


_log = logging.getLogger("Worker")

HEARTBEAT_INTERVAL = 10.0


def _dict_to_ns(d: dict) -> types.SimpleNamespace:
    """Wrap a dict in a SimpleNamespace for dotted attribute access.

    Also adds a model_dump() shim so code that calls it still works.
    """
    ns = types.SimpleNamespace(**d)
    ns.model_dump = lambda mode="python": d
    return ns


def _resolve_callable(spec: str):
    """Import and return a callable from a dotted path like
    'dv_flow.mgr.std.fileset.FileSet'."""
    last_dot = spec.rfind(".")
    if last_dot < 0:
        raise ImportError("Invalid callable spec: %s" % spec)
    mod_path = spec[:last_dot]
    attr_name = spec[last_dot + 1:]
    mod = importlib.import_module(mod_path)
    return getattr(mod, attr_name)


async def execute_request(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single task described by a task.execute message.

    Returns a dict with status, changed, output, markers, memento.
    """
    name = params.get("name", "")
    _log.info("Executing task: %s", name)

    # Adjust sys.path with extra entries the orchestrator provided
    for p in params.get("pythonpath", []):
        if p and p not in sys.path:
            sys.path.insert(0, p)

    rundir = params.get("rundir", "")
    srcdir = params.get("srcdir", "")
    if rundir:
        os.makedirs(rundir, exist_ok=True)

    shell = params.get("shell", "pytask")
    callable_spec = params.get("callable_spec", "")
    body = params.get("body")

    try:
        if shell == "pytask":
            # Import the target function (e.g. dv_flow.mgr.std.fileset.FileSet)
            if not callable_spec:
                raise ValueError("pytask requires callable_spec")
            callable_fn = _resolve_callable(callable_spec)

            # Wrap params dict in SimpleNamespace for attribute access
            params_dict = params.get("params", {})
            params_obj = _dict_to_ns(params_dict)

            # Wrap each input item the same way
            input_items = [
                _dict_to_ns(item) if isinstance(item, dict) else item
                for item in params.get("inputs", [])
            ]

            from .task_data import TaskDataInput
            task_input = TaskDataInput(
                name=name,
                changed=True,
                srcdir=srcdir,
                rundir=rundir,
                params=params_obj,
                inputs=input_items,
                memento=params.get("memento"),
            )

            # Build TaskRunCtxt with a worker-local jobserver scoped to
            # this worker's available cores.
            from .task_run_ctxt import TaskRunCtxt
            shim = _WorkerRunnerShim()
            ctxt = TaskRunCtxt(
                runner=shim,
                ctxt=None,
                rundir=rundir,
            )

            result = await callable_fn(ctxt, task_input)
            if result is None:
                result = TaskDataResult()

        else:
            # Shell task: use ShellCallable so ${{ }} references are
            # expanded and logging/script files are handled properly.
            if not body:
                raise ValueError("Shell task '%s' has no body" % name)

            from .shell_callable import ShellCallable
            shell_callable = ShellCallable(
                body=body,
                srcdir=srcdir,
                shell=shell,
            )

            params_dict = params.get("params", {})
            params_obj = _dict_to_ns(params_dict)
            input_items = [
                _dict_to_ns(item) if isinstance(item, dict) else item
                for item in params.get("inputs", [])
            ]

            from .task_data import TaskDataInput
            task_input = TaskDataInput(
                name=name,
                changed=True,
                srcdir=srcdir,
                rundir=rundir,
                params=params_obj,
                inputs=input_items,
                memento=params.get("memento"),
            )

            from .task_run_ctxt import TaskRunCtxt
            shim = _WorkerRunnerShim()
            ctxt = TaskRunCtxt(
                runner=shim,
                ctxt=None,
                rundir=rundir,
            )

            result = await shell_callable(ctxt, task_input)
            if result is None:
                result = TaskDataResult()

        # Serialize result for transmission back to daemon
        output = []
        for item in result.output:
            if hasattr(item, "model_dump"):
                output.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                output.append(item)

        markers = []
        for m in result.markers:
            if hasattr(m, "model_dump"):
                markers.append(m.model_dump(mode="json"))
            elif isinstance(m, dict):
                markers.append(m)

        memento = None
        if result.memento is not None:
            if hasattr(result.memento, "model_dump"):
                memento = result.memento.model_dump(mode="json")
            else:
                memento = result.memento

        return {
            "status": result.status,
            "changed": result.changed,
            "output": output,
            "markers": markers,
            "memento": memento,
        }

    except Exception as e:
        _log.error("Task '%s' failed: %s", name, e, exc_info=True)
        return {
            "status": 1,
            "changed": False,
            "output": [],
            "markers": [{"msg": str(e), "severity": "error"}],
            "memento": None,
        }


async def run_worker(
    connect_addr: str,
    worker_id: Optional[str] = None,
    resource_class: str = "",
    lsf_job_id: str = "",
):
    """Main worker loop: connect, register, receive tasks, report results.

    The message reader runs concurrently with task execution so that
    ``task.cancel`` messages are handled even while a task is running.
    """
    # Auto-detect LSF job ID from environment if not explicitly provided
    if not lsf_job_id:
        lsf_job_id = os.environ.get("LSB_JOBID", "")

    if worker_id is None:
        worker_id = uuid.uuid4().hex[:12]

    host, port_str = connect_addr.rsplit(":", 1)
    port = int(port_str)
    hostname = platform.node()
    pid = os.getpid()

    _log.info("Worker %s connecting to %s:%d", worker_id, host, port)

    # Retry connection with backoff; LSF workers may start before the
    # daemon port is reachable from the compute node.
    max_retries = 10
    reader = writer = None
    for attempt in range(1, max_retries + 1):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            break
        except (ConnectionRefusedError, OSError) as e:
            if attempt == max_retries:
                _log.error("Failed to connect to daemon at %s:%d after %d attempts: %s",
                           host, port, max_retries, e)
                return
            delay = min(2 ** attempt, 30)
            _log.warning("Connect attempt %d/%d to %s:%d failed (%s), retrying in %ds",
                         attempt, max_retries, host, port, e, delay)
            await asyncio.sleep(delay)

    _log.info("Connected. Sending registration.")

    reg_msg = build_worker_register(
        worker_id=worker_id,
        hostname=hostname,
        pid=pid,
        resource_class=resource_class,
        lsf_job_id=lsf_job_id,
    )
    writer.write(encode_message(reg_msg))
    await writer.drain()

    heartbeat_task = asyncio.create_task(_heartbeat_loop(writer, worker_id))

    # Current running task; accessed by both the reader and the
    # execution path.  Only one task runs at a time.
    current_exec: Optional[asyncio.Task] = None
    current_request_id: Optional[str] = None
    should_exit = False

    async def _read_messages():
        """Read daemon messages and dispatch them.

        task.execute: start the task as a background asyncio.Task.
        task.cancel: cancel the running task.
        worker.shutdown: request exit.
        """
        nonlocal current_exec, current_request_id, should_exit
        try:
            while True:
                line_bytes = await reader.readline()
                if not line_bytes:
                    _log.info("Connection closed by daemon")
                    should_exit = True
                    break

                line = line_bytes.decode("utf-8").rstrip("\n")
                if not line:
                    continue

                try:
                    msg = parse_message(line)
                except ProtocolError as e:
                    _log.warning("Protocol error: %s", e)
                    continue

                method = msg["method"]
                params = msg["params"]

                if method == METHOD_TASK_EXECUTE:
                    request_id = params.get("request_id", "")
                    _log.info("Received task: %s (request_id=%s)",
                              params.get("name", ""), request_id)
                    current_request_id = request_id
                    current_exec = asyncio.create_task(
                        _run_and_report(params, request_id, writer))

                elif method == METHOD_TASK_CANCEL:
                    cancel_rid = params.get("request_id", "")
                    _log.info("Cancel requested for %s", cancel_rid)
                    if (current_exec is not None
                            and current_request_id == cancel_rid
                            and not current_exec.done()):
                        current_exec.cancel()

                elif method == METHOD_WORKER_SHUTDOWN:
                    _log.info("Shutdown requested by daemon")
                    should_exit = True
                    # Cancel any running task on shutdown
                    if current_exec is not None and not current_exec.done():
                        current_exec.cancel()
                    break

                else:
                    _log.info("Ignoring unknown method: %s", method)

        except (ConnectionResetError, BrokenPipeError):
            _log.warning("Connection lost")
            should_exit = True

    async def _run_and_report(params, request_id, wr):
        """Execute the task and send the result back to the daemon."""
        nonlocal current_exec, current_request_id
        try:
            result_data = await execute_request(params)
        except asyncio.CancelledError:
            _log.info("Task %s cancelled", request_id)
            result_data = {
                "status": 1,
                "changed": False,
                "output": [],
                "markers": [{"msg": "Task cancelled", "severity": "warning"}],
                "memento": None,
            }
        finally:
            current_exec = None
            current_request_id = None

        try:
            result_msg = build_task_result(request_id=request_id, **result_data)
            wr.write(encode_message(result_msg))
            await wr.drain()
        except Exception as e:
            _log.warning("Failed to send result for %s: %s", request_id, e)

    try:
        await _read_messages()
        # Wait for a running task to finish after the reader exits
        if current_exec is not None and not current_exec.done():
            await current_exec
    except (ConnectionResetError, BrokenPipeError):
        _log.warning("Connection lost")
    finally:
        # Cancel any still-running task
        if current_exec is not None and not current_exec.done():
            current_exec.cancel()
            try:
                await current_exec
            except asyncio.CancelledError:
                pass
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        _log.info("Worker %s exiting", worker_id)


async def _heartbeat_loop(writer: asyncio.StreamWriter, worker_id: str):
    """Periodically send heartbeat messages to the daemon."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            msg = build_worker_heartbeat(worker_id)
            writer.write(encode_message(msg))
            await writer.drain()
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass
