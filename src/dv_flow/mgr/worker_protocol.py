#****************************************************************************
#* worker_protocol.py
#*
#* JSON-RPC message builders and parsers for worker <-> daemon protocol.
#* Newline-delimited JSON framing.
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
import json
import logging
from typing import Any, Dict, List, Optional


_log = logging.getLogger("WorkerProtocol")

# --- Message type constants ---
METHOD_WORKER_REGISTER = "worker.register"
METHOD_TASK_EXECUTE = "task.execute"
METHOD_TASK_RESULT = "task.result"
METHOD_WORKER_HEARTBEAT = "worker.heartbeat"
METHOD_WORKER_SHUTDOWN = "worker.shutdown"
METHOD_TASK_CANCEL = "task.cancel"

_KNOWN_METHODS = {
    METHOD_WORKER_REGISTER,
    METHOD_TASK_EXECUTE,
    METHOD_TASK_RESULT,
    METHOD_WORKER_HEARTBEAT,
    METHOD_WORKER_SHUTDOWN,
    METHOD_TASK_CANCEL,
}

# Required fields per message type
_REQUIRED_FIELDS = {
    METHOD_WORKER_REGISTER: {"worker_id"},
    METHOD_TASK_EXECUTE: {"request_id", "name"},
    METHOD_TASK_RESULT: {"request_id", "status"},
    METHOD_WORKER_HEARTBEAT: {"worker_id"},
    METHOD_WORKER_SHUTDOWN: set(),
    METHOD_TASK_CANCEL: {"request_id"},
}


class ProtocolError(Exception):
    """Raised when a protocol message is invalid."""
    pass


# --- Builders ---

def build_worker_register(
    worker_id: str,
    hostname: str = "",
    pid: int = 0,
    resource_class: str = "",
    lsf_job_id: str = "",
) -> str:
    """Build a worker.register message (worker -> daemon)."""
    msg = {
        "method": METHOD_WORKER_REGISTER,
        "params": {
            "worker_id": worker_id,
            "hostname": hostname,
            "pid": pid,
            "resource_class": resource_class,
            "lsf_job_id": lsf_job_id,
        },
    }
    return json.dumps(msg)


def build_task_execute(
    request_id: str,
    name: str,
    callable_spec: str = "",
    shell: str = "pytask",
    body: Optional[str] = None,
    srcdir: str = "",
    rundir: str = "",
    pythonpath: Optional[List[str]] = None,
    params: Optional[Dict[str, Any]] = None,
    inputs: Optional[List[Dict[str, Any]]] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """Build a task.execute message (daemon -> worker)."""
    msg = {
        "method": METHOD_TASK_EXECUTE,
        "params": {
            "request_id": request_id,
            "name": name,
            "callable_spec": callable_spec,
            "shell": shell,
            "srcdir": srcdir,
            "rundir": rundir,
            "pythonpath": pythonpath or [],
            "params": params or {},
            "inputs": inputs or [],
            "env": env or {},
        },
    }
    if body is not None:
        msg["params"]["body"] = body
    return json.dumps(msg)


def build_task_result(
    request_id: str,
    status: int = 0,
    changed: bool = False,
    output: Optional[List[Dict[str, Any]]] = None,
    markers: Optional[List[Dict[str, Any]]] = None,
    memento: Any = None,
) -> str:
    """Build a task.result message (worker -> daemon)."""
    msg = {
        "method": METHOD_TASK_RESULT,
        "params": {
            "request_id": request_id,
            "status": status,
            "changed": changed,
            "output": output or [],
            "markers": markers or [],
            "memento": memento,
        },
    }
    return json.dumps(msg)


def build_worker_heartbeat(worker_id: str) -> str:
    """Build a worker.heartbeat message (worker -> daemon)."""
    msg = {
        "method": METHOD_WORKER_HEARTBEAT,
        "params": {"worker_id": worker_id},
    }
    return json.dumps(msg)


def build_worker_shutdown() -> str:
    """Build a worker.shutdown message (daemon -> worker)."""
    msg = {
        "method": METHOD_WORKER_SHUTDOWN,
        "params": {},
    }
    return json.dumps(msg)


def build_task_cancel(request_id: str) -> str:
    """Build a task.cancel message (daemon -> worker)."""
    msg = {
        "method": METHOD_TASK_CANCEL,
        "params": {"request_id": request_id},
    }
    return json.dumps(msg)


# --- Parsers ---

def parse_message(line: str) -> Dict[str, Any]:
    """Parse a single newline-delimited JSON message.

    Returns dict with 'method' and 'params' keys.

    Raises:
        ProtocolError: If JSON is invalid or required fields are missing.
    """
    line = line.strip()
    if not line:
        raise ProtocolError("Empty message")

    try:
        msg = json.loads(line)
    except json.JSONDecodeError as e:
        raise ProtocolError("Invalid JSON: %s" % str(e))

    if not isinstance(msg, dict):
        raise ProtocolError("Message must be a JSON object, got %s" % type(msg).__name__)

    method = msg.get("method")
    if not method or not isinstance(method, str):
        raise ProtocolError("Missing or invalid 'method' field")

    params = msg.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError("'params' must be a JSON object")

    # Validate required fields for known methods
    if method in _REQUIRED_FIELDS:
        missing = _REQUIRED_FIELDS[method] - set(params.keys())
        if missing:
            raise ProtocolError(
                "Method '%s' missing required params: %s" % (method, ", ".join(sorted(missing)))
            )

    # Unknown methods are logged but not rejected
    if method not in _KNOWN_METHODS:
        _log.info("Unknown method '%s' -- ignoring", method)

    return {"method": method, "params": params}


def encode_message(msg_str: str) -> bytes:
    """Encode a message string for transmission (append newline)."""
    return (msg_str + "\n").encode("utf-8")


def decode_line(data: bytes) -> str:
    """Decode a raw line from the wire."""
    return data.decode("utf-8").rstrip("\n")
