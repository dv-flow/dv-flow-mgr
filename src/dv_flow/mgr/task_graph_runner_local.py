#****************************************************************************
#* task_graph_runner_local.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
import asyncio
import os
import yaml
import dataclasses as dc
from typing import Any, Callable, ClassVar, Dict, List, Union
from .fragment_def import FragmentDef
from .package import Package
from .pkg_rgy import PkgRgy
from .package_def import PackageDef, PackageSpec
from .task import Task, TaskSpec, TaskCtor
from .task_data import TaskData
from .task_graph_runner import TaskGraphRunner

@dc.dataclass
class TaskGraphRunnerLocal(TaskGraphRunner):
    """Session manages execution of a task graph"""

    rundir : str
    nproc : int = -1
    _workers : List = dc.field(default_factory=list)

    _inst : ClassVar['TaskGraphRunner'] = None

    # Search path for .dfs files
    create_subprocess : Callable = asyncio.create_subprocess_exec
    _root_dir : str = None

    def __post_init__(self):
        if self.nproc == -1:
            self.nproc = os.cpu_count()
        for _ in range(self.nproc):
            self._workers.append(LocalRunnerWorker(self))


    async def exec(self, *args, **kwargs):
        return await self.create_subprocess(*args, **kwargs)

    async def run(self, task : Union[Task,List[Task]]) -> List['TaskData']:
        if isinstance(task, Task):
            unwrap = True
            task = [task]
        else:
            unwrap = False
        
        run_o = list(t.do_run() for t in task)

        ret = await asyncio.gather(*run_o)

        if unwrap:
            return ret[0]
        else:
            return ret
    
    async def runTask(self, task : Task) -> 'TaskData':
        return await task.do_run()
    
    def queueTask(self, task : Task):
        """Queue a task for execution"""
        pass

@dc.dataclass
class LocalRunnerWorker(object):
    runner : TaskGraphRunnerLocal
    pass


