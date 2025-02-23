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
import logging
from toposort import toposort
from typing import Any, Callable, ClassVar, Coroutine, Dict, List, Tuple, Union
from .fragment_def import FragmentDef
from .package import Package
from .pkg_rgy import PkgRgy
from .package_def import PackageDef, PackageSpec
from .task import Task
from .task_data import TaskData
from .task_graph_runner import TaskGraphRunner

@dc.dataclass
class TaskGraphRunnerLocal(TaskGraphRunner):
    """Session manages execution of a task graph"""

    rundir : str
    nproc : int = 4
    done_task_m : Dict = dc.field(default_factory=dict)
    _workers : List = dc.field(default_factory=list)

    _inst : ClassVar['TaskGraphRunner'] = None

    # Search path for .dfs files
    create_subprocess : Callable = asyncio.create_subprocess_exec
    _root_dir : str = None
    _log : ClassVar = logging.getLogger("TaskGraphRunnerLocal")

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

        dep_m = {}
        task_m = {}

        for t in task:
            self._mkDeps(dep_m, task_m, t)

        self._log.debug("dep_m: %s" % str(dep_m))

        order = list(toposort(dep_m))
        
        self._log.debug("order: %s" % str(order))

        active_task_l : List[Tuple[Task,Coroutine]]= []
        # Now, iterate over the concurrent sets
        for active_s in order:

            # Check to see if all tasks are complete
            done = True
            for t in active_s:
                while len(active_task_l) >= self.nproc and t not in self.done_task_m.keys():
                    # Wait for at least one job to complete
                    done, pending = await asyncio.wait(at[1] for at in active_task_l)
                    for d in done:
                        for i in range(len(active_task_l)):
                            if active_task_l[i][1] == d:
                                tt = active_task_l[i][0]
                                self.done_task_m[tt.name] = tt
                                active_task_l.pop(i)
                                break
                if t not in self.done_task_m.keys():
                    task_t = task_m[t]
                    coro = asyncio.Task(task_t.do_run(self))
                    active_task_l.append((task_t, coro))
               
            # Now, wait for tasks to complete
            if len(active_task_l):
                coros = list(at[1] for at in active_task_l)
                res = await asyncio.gather(*coros)

#        print("order: %s" % str(order))
#        
#        run_o = list(t.do_run() for t in task)

#        ret = await asyncio.gather(*run_o)
        ret = None

        if unwrap:
            return task[0].output
        else:
            return list(t.output for t in task)
        
    def _mkDeps(self, dep_m, task_m, task):
        if task.name not in dep_m.keys():
            task_m[task.name] = task
            dep_m[task.name] = set(t.name for t in task.depends)
            for d in task.depends:
                self._mkDeps(dep_m, task_m, d)
    
    async def runTask(self, task : Task) -> 'TaskData':
        return await task.do_run()
    
    def queueTask(self, task : Task):
        """Queue a task for execution"""
        pass

@dc.dataclass
class LocalRunnerWorker(object):
    runner : TaskGraphRunnerLocal
    task_s : List = dc.field(default_factory=list)



