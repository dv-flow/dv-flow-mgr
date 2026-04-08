#****************************************************************************
#* lsf_backend.py
#*
#* LSF runner backend: manages an LSF worker pool via bsub/bjobs/bkill.
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
import logging
from typing import ClassVar, Optional

from .runner_backend import RunnerBackend, TaskExecRequest
from .runner_config import RunnerConfig
from .task_data import TaskDataResult
from .daemon_client import DaemonClientBackend


_log = logging.getLogger("LsfBackend")


class LsfBackend(RunnerBackend):
    """LSF runner backend.

    Connects to a running daemon (DaemonClientBackend) to dispatch
    tasks to LSF workers. The daemon handles the actual bsub/bjobs/bkill
    mechanics via the pool manager.
    """

    def __init__(self, config: Optional[RunnerConfig] = None, project_root: str = ""):
        self._config = config or RunnerConfig()
        self._project_root = project_root
        self._delegate: Optional[DaemonClientBackend] = None

    @property
    def is_remote(self) -> bool:
        return True

    async def start(self) -> None:
        """Connect to a running daemon.

        Raises RuntimeError if no daemon is found.
        """
        self._delegate = DaemonClientBackend(self._project_root)
        await self._delegate.start()
        _log.info("LSF backend connected to daemon")

    async def stop(self) -> None:
        """Disconnect from the daemon."""
        if self._delegate:
            await self._delegate.stop()

    async def execute_task(self, request: TaskExecRequest) -> TaskDataResult:
        """Dispatch task to daemon -> LSF worker pool."""
        if self._delegate is None:
            raise RuntimeError(
                "LSF backend not started. Run 'dfm daemon start' first."
            )
        return await self._delegate.execute_task(request)

    async def cancel_inflight(self) -> None:
        """Cancel all inflight tasks via the daemon."""
        if self._delegate:
            await self._delegate.cancel_inflight()

    async def acquire_slot(self) -> None:
        """No-op: daemon manages slots."""
        pass

    async def release_slot(self) -> None:
        """No-op: daemon manages slots."""
        pass
