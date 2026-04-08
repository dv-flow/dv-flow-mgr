#****************************************************************************
#* slurm_backend.py
#*
#* SLURM runner backend stub. Not yet implemented.
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
from .runner_backend import RunnerBackend, TaskExecRequest
from .task_data import TaskDataResult


class SlurmBackend(RunnerBackend):
    """SLURM runner backend (placeholder).

    The architecture is identical to LsfBackend -- daemon-managed worker
    pool with sbatch/squeue/scancel instead of bsub/bjobs/bkill.

    See LSF_SUPPORT_DESIGN.md for the design that applies to both
    LSF and SLURM backends.
    """

    async def start(self) -> None:
        raise NotImplementedError(
            "SLURM backend is not yet implemented. "
            "See LSF_SUPPORT_DESIGN.md for the design plan."
        )

    async def stop(self) -> None:
        pass

    async def execute_task(self, request: TaskExecRequest) -> TaskDataResult:
        raise NotImplementedError("SLURM backend is not yet implemented.")

    async def acquire_slot(self) -> None:
        pass

    async def release_slot(self) -> None:
        pass

    @property
    def is_remote(self) -> bool:
        return True
