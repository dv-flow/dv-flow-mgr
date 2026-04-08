#****************************************************************************
#* daemon_events.py
#*
#* Event type definitions shared between daemon and monitor.
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
from typing import Any, Dict, List, Optional


# Event method constants
EVENT_WORKER_STATE = "worker.state"
EVENT_TASK_DISPATCHED = "task.dispatched"
EVENT_TASK_COMPLETED = "task.completed"
EVENT_POOL_SCALED = "pool.scaled"
EVENT_CLIENT_CONNECTED = "client.connected"
EVENT_LOG = "log"

_KNOWN_EVENTS = {
    EVENT_WORKER_STATE,
    EVENT_TASK_DISPATCHED,
    EVENT_TASK_COMPLETED,
    EVENT_POOL_SCALED,
    EVENT_CLIENT_CONNECTED,
    EVENT_LOG,
}


def make_event(method: str, params: Dict[str, Any]) -> str:
    """Build a JSON event string for transmission to monitors."""
    return json.dumps({"method": method, "params": params})


def parse_event(line: str) -> Optional[Dict[str, Any]]:
    """Parse an event line from the daemon.

    Returns dict with 'method' and 'params', or None for unknown/invalid events.
    """
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    method = data.get("method", "")
    params = data.get("params", {})
    return {"method": method, "params": params}


def is_known_event(method: str) -> bool:
    """Check if an event method is a known type."""
    return method in _KNOWN_EVENTS
