#****************************************************************************
#* task_graph_runner.py
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
import dataclasses as dc
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task import Task
from .task_data import TaskData
from .task_runner import TaskRunner

@dc.dataclass
class TaskGraphRunner(TaskRunner):
    """Session manages execution of a task graph"""

    _inst : ClassVar['TaskGraphRunner'] = None


    # Search path for .dfs files
    create_subprocess : Callable = asyncio.create_subprocess_exec
    _root_dir : str = None

    async def exec(self, *args, **kwargs):
        return self.create_subprocess(*args, **kwargs)

    # def load(self):
    #     if not os.path.isdir(self.srcdir):
    #         raise Exception("Root directory %s does not exist" % self.srcdir)

    #     if not os.path.isfile(os.path.join(self.srcdir, "flow.dv")):
    #         raise Exception("No root flow file")

    #     self._root_dir = os.path.dirname(self.srcdir)
    #     self.package = PackageDef.load(os.path.join(self.srcdir, "flow.dv"), [])

    #     return self.package


    async def run(self, task : str) -> 'TaskData':
        impl = self.mkTaskGraph(task)
        return await impl.do_run()
    
    async def runTask(self, task : Task) -> 'TaskData':
        return await task.do_run()
    
    def queueTask(self, task : Task):
        """Queue a task for execution"""
        pass




