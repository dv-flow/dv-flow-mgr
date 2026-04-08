#****************************************************************************
#* runner_backend_local.py
#*
#* Local runner backend wrapping the existing jobserver.
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
from .task_data import TaskDataResult


class LocalBackend(RunnerBackend):
    """Execute tasks locally using the existing jobserver.

    For LocalBackend, TaskNodeLeaf._run_task continues to call the
    callable directly (no serialization overhead). The backend is only
    consulted for slot acquisition.
    """

    _log: ClassVar = logging.getLogger("LocalBackend")

    def __init__(self, jobserver: Optional['JobServer'] = None):
        self._jobserver = jobserver

    async def start(self) -> None:
        """No-op for local execution."""
        pass

    async def stop(self) -> None:
        """No-op for local execution."""
        pass

    async def execute_task(self, request: TaskExecRequest) -> TaskDataResult:
        """LocalBackend uses in-process execution; this should not be called.

        The local path goes through TaskNodeLeaf._run_task directly.
        """
        raise NotImplementedError(
            "LocalBackend uses in-process execution via TaskNodeLeaf._run_task"
        )

    async def acquire_slot(self) -> None:
        """Acquire a jobserver token."""
        if self._jobserver is not None:
            await self._jobserver.acquire()

    async def release_slot(self) -> None:
        """Release a jobserver token."""
        if self._jobserver is not None:
            self._jobserver.release()

    @property
    def is_remote(self) -> bool:
        return False
