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
from .task_data import (
    CompoundRunInput, SubtaskSummary,
    TaskDataResult, TaskDataInput, TaskDataOutput,
    TaskFailure,
)
from .task_runner import TaskRunner
from .task_run_ctxt import TaskRunCtxt
from typing import Any, Callable, List

class NullParams(BaseModel):
    pass


async def _default_compound_run(ctxt, input: CompoundRunInput) -> TaskDataResult:
    """Default aggregator used when a compound declares no explicit run callable.

    OR-accumulates status from all std.TaskFailure items and passes all
    non-TaskFailure output items through unchanged.  This preserves the
    original compound behaviour so existing flows are unaffected.
    """
    status = 0
    output = []
    for item in input.inputs:
        if getattr(item, "type", None) == "std.TaskFailure":
            status |= item.status
        else:
            output.append(item)
    return TaskDataResult(status=status, output=output)


@dc.dataclass
class TaskNodeCompound(TaskNode):
    """A Compound task node is the 'out' node in the subgraph"""
    tasks        : List[TaskNode] = dc.field(default_factory=list)
    input        : TaskNode       = None
    max_failures : int            = -1   # -1 or 0: run all; 1: stop on first; N: stop after N
    run          : Callable       = None  # async (TaskRunCtxt, CompoundRunInput) -> TaskDataResult

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
                     runner : TaskRunner, 
                     rundir, 
                     memento : Any=None) -> TaskDataResult:
        self._log.debug("Compound task %s (%d)" % (self.name, len(self.needs)))

        add_s = set()
        output = []
        changed = False

        for n in self.needs:
            changed |= n[0].output.changed
            for o in n[0].output.output:
                if getattr(o, "type", None) == "std.Env":
                    continue
                o_id = (o.src, o.seq)
                if o_id not in add_s:
                    if self.consumes is not None or self.consumes == ConsumesE.All:
                        add_s.add(o_id)
                        output.append(o)
                    elif isinstance(self.consumes, list) and self._matches(o, self.consumes):
                        add_s.add(o_id)
                        output.append(o)

        # Build per-subtask summaries (exclude the internal .input sentinel).
        from .task_runner import TaskState
        subtasks = []
        for t in self.tasks:
            if t is self.input:
                continue
            t_status = t.result.status if t.result is not None else 0
            t_skipped = (
                getattr(runner, '_task_state', {}).get(t) == TaskState.SKIPPED
            )
            subtasks.append(SubtaskSummary(
                name=t.name,
                status=t_status,
                skipped=t_skipped,
            ))

        # Build CompoundRunInput for the run callable.
        ctxt = TaskRunCtxt(runner=runner, ctxt=self.ctxt, rundir=rundir)
        compound_input = CompoundRunInput(
            name=self.name,
            changed=changed,
            srcdir=self.srcdir,
            rundir=rundir,
            params=self.params,
            inputs=output,
            memento=memento,
            subtasks=subtasks,
        )

        run_fn = self.run if self.run is not None else _default_compound_run
        result = await run_fn(ctxt, compound_input)

        self.result = TaskDataResult(
            status=result.status,
            changed=result.changed if result.changed is not None else changed,
            output=result.output,
            markers=result.markers,
        )

        self.output = TaskDataOutput(
            changed=self.result.changed,
            output=self.result.output,
            dep_m={})

        return None

    def __hash__(self):
        return id(self)

