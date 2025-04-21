#****************************************************************************
#* task_node_compound.py
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
import dataclasses as dc
from pydantic import BaseModel
from .task_def import ConsumesE, PassthroughE, PassthroughE, PassthroughE, PassthroughE
from .task_node import TaskNode
from .task_node_leaf import TaskNodeLeaf
from .task_data import TaskDataResult, TaskDataInput, TaskDataOutput
from .task_runner import TaskRunner
from typing import Any, List

class NullParams(BaseModel):
    pass

@dc.dataclass
class TaskNodeCompound(TaskNode):
    """A Compound task node is the 'out' node in the subgraph"""
    tasks : List[TaskNode] = dc.field(default_factory=list)
    input : TaskNode = None

    def __post_init__(self):
        async def null_run(runner, input):
            return TaskDataResult()
        
        self.input = TaskNodeLeaf(
            name=self.name + ".in",
            srcdir=self.srcdir,
            params=NullParams(),
            ctxt=self.ctxt,
            consumes=ConsumesE.No,
            passthrough=PassthroughE.All)
        self.input.task = null_run
        self.tasks.append(self.input)

        return super().__post_init__()

    @property
    def first(self):
        return self.input
    
    async def do_run(self, 
                     ctxt : TaskRunner, 
                     rundir, 
                     memento : Any=None) -> TaskDataResult:
        self._log.debug("Compound task %s (%d)" % (self.name, len(self.needs)))

        add_s = set()
        output = []
        status = 0
        changed = False

        for n in self.needs:
            status |= n[0].result.status
            changed |= n[0].output.changed
            for o in n[0].output.output:
                o_id = (o.src, o.seq)
                if not o_id in add_s:
                    if self.consumes is not None or self.consumes == ConsumesE.All:
                        add_s.add(o_id)
                        output.append(o)
                    elif isinstance(self.consumes, list) and self._matches(o, self.consumes):
                        add_s.add(o_id)
                        output.append(o)

        self.result = TaskDataResult(
            status=status,
            changed=changed,
            output=output
        )

        # TODO: Handle passthrough and deps

        self.output = TaskDataOutput(
            changed=changed,
            output=output,
            dep_m={})
        
#        if self.save_exec_data:
#            self._save_exec_data(rundir, ctxt, self.input.input)

        return 0

    def __hash__(self):
        return id(self)
    
