#****************************************************************************
#* runner_backend.py
#*
#* Abstract runner backend interface for task execution.
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
import dataclasses as dc
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


@dc.dataclass
class ResourceReq:
    """Resource requirements extracted from task tags and config."""
    cores: int = 1
    memory: str = "1G"
    queue: str = ""
    walltime_minutes: int = 60
    project: str = ""
    resource_select: List[str] = dc.field(default_factory=list)
    extra: Dict[str, Any] = dc.field(default_factory=dict)


@dc.dataclass
class TaskExecRequest:
    """Serializable description of a task to execute remotely."""
    name: str = ""
    callable_spec: str = ""
    shell: str = "pytask"
    body: Optional[str] = None
    srcdir: str = ""
    rundir: str = ""
    pythonpath: List[str] = dc.field(default_factory=list)
    params: Dict[str, Any] = dc.field(default_factory=dict)
    inputs: List[Dict[str, Any]] = dc.field(default_factory=list)
    env: Dict[str, str] = dc.field(default_factory=dict)
    memento: Optional[Any] = None
    resource_req: ResourceReq = dc.field(default_factory=ResourceReq)


class RunnerBackend(ABC):
    """Abstract execution backend.

    Implementations provide different strategies for executing tasks:
    local (in-process via jobserver), LSF, SLURM, etc.
    """

    @abstractmethod
    async def start(self) -> None:
        """Initialize backend (connect to daemon, start pool, etc.)."""

    @abstractmethod
    async def stop(self) -> None:
        """Shutdown backend (drain workers, release resources)."""

    @abstractmethod
    async def execute_task(self, request: TaskExecRequest) -> 'TaskDataResult':
        """Execute a single task. Blocks until the task completes.

        The backend is responsible for:
        - Selecting or launching an appropriate worker
        - Transmitting the request
        - Waiting for and returning the result
        - Handling worker failures (retry on a different worker)
        """

    @abstractmethod
    async def acquire_slot(self) -> None:
        """Acquire an execution slot (analogous to jobserver token).

        Blocks if the backend is at capacity.
        """

    @abstractmethod
    async def release_slot(self) -> None:
        """Release an execution slot."""

    async def cancel_inflight(self) -> None:
        """Cancel all tasks currently in flight.

        Called during cleanup (e.g. SIGINT) to inform the backend that
        any outstanding tasks should be aborted.  The default is a no-op;
        remote backends override this to notify the daemon.
        """
        pass

    @property
    def is_remote(self) -> bool:
        """True if this backend dispatches tasks to remote workers."""
        return False
