#****************************************************************************
#* task_runner.py
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
import asyncio
import json
import os
import re
import dataclasses as dc
import logging
from datetime import datetime
from toposort import toposort
from typing import Any, Callable, ClassVar, Dict, List, Set, Tuple, Union
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_node import TaskNode, RundirE

@dc.dataclass
class TaskRunner(object):
    rundir : str

    # List of [Listener:Callable[Task],Recurisve:bool]
    listeners : List[Tuple[Callable['Task','Reason'], bool]] = dc.field(default_factory=list)

    _log : ClassVar = logging.getLogger("TaskRunner")

    def add_listener(self, l, recursive=False):
        self.listeners.append((l, recursive))

    def _notify(self, task : 'Task', reason : 'Reason'):
        for listener in self.listeners:
            listener[0](task, reason)

    async def do_run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        return await self.run(task, memento)

    async def run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        pass

@dc.dataclass
class TaskSetRunner(TaskRunner):
    builder : 'TaskGraphBuilder' = None
    nproc : int = -1
    status : int = 0

    _anon_tid : int = 1

    _log : ClassVar = logging.getLogger("TaskSetRunner")

    def __post_init__(self):
        if self.nproc == -1:
            self.nproc = os.cpu_count()

    async def run(self, task : Union[TaskNode,List[TaskNode]]):
        # Ensure that the rundir exists or can be created

        if not os.path.isdir(self.rundir):
            os.makedirs(self.rundir)

        if not os.path.isdir(os.path.join(self.rundir, "cache")):
            os.makedirs(os.path.join(self.rundir, "cache"))

        src_memento = None
        dst_memento = {}
        if os.path.isfile(os.path.join(self.rundir, "cache", "mementos.json")):
            try:
                with open(os.path.join(self.rundir, "cache", "mementos.json"), "r") as f:
                    src_memento = json.load(f)
            except Exception as e:
                src_memento = {}
        else:
            src_memento = {}


        # First, build a depedency map
        dep_m = self.buildDepMap(task)

        if self._log.isEnabledFor(logging.DEBUG):
            self._log.debug("Deps:")
            for t,value in dep_m.items():
                self._log.debug("  Task: %s", str(t.name))
                for v in value:
                    self._log.debug("  - %s", str(v.name))

        order = list(toposort(dep_m))

        if self._log.isEnabledFor(logging.DEBUG):
            self._log.debug("Order:")
            for active_s in order:
                self._log.debug("- {%s}", ",".join(str(t.name) for t in active_s))

        active_task_l = []
        done_task_s = set()
        self.status = 0
        for active_s in order:
            done = True
            for t in active_s:
                while len(active_task_l) >= self.nproc and t not in done_task_s:
                    # Wait for at least one job to complete
                    done, pending = await asyncio.wait([at[1] for at in active_task_l])
                    self._completeTasks(active_task_l, done_task_s, done, dst_memento)

                if self.status == 0 and t not in done_task_s:
                    memento = src_memento.get(t.name, None)
#                    dirname = t.name
                    invalid_chars_pattern = r'[\/:*?"<>|#%&{}\$\\!\'`;=@+]'

                    # TaskNode rundir is a list of path elements relative
                    # to the root rundir
                    rundir = ""

                    for i, rundir_e in enumerate(t.rundir):
                        if i:
                            rundir_e = re.sub(invalid_chars_pattern, '_', rundir_e)
                            rundir = os.path.join(rundir, rundir_e)
                        else:
                            rundir = rundir_e

                    # if t.rundir_t == RundirE.Unique:
                    #     # Replace invalid characters with the replacement string.
                    #     dirname = re.sub(invalid_chars_pattern, '_', dirname)

                    #     rundir = os.path.join(self.rundir, dirname)
                    # else:
                    #     rundir = self.rundir

                    if not os.path.isdir(rundir):
                        os.makedirs(rundir, exist_ok=True)

                    self._log.debug("start task %s" % t.name)
                    self._notify(t, "enter")
                    t.start = datetime.now()
                    coro = asyncio.Task(t.do_run(
                        self,
                        rundir,
                        memento)) 
                    active_task_l.append((t, coro))

                if self.status != 0:
                    self._log.debug("Exiting due to status: %d", self.status)
                    break
               
            # All pending tasks in the task-group have been launched
            # Wait for them to all complete
            while len(active_task_l):
                # TODO: Shouldn't gather here -- reach to each completion
                done, pending = await asyncio.wait([at[1] for at in active_task_l])
                self._completeTasks(active_task_l, done_task_s, done, dst_memento)
            
            if self.status != 0:
                self._log.debug("Exiting due to status: %d", self.status)
                break

        with open(os.path.join(self.rundir, "cache", "mementos.json"), "w") as f:
            json.dump(dst_memento, f)

        if self.status == 0:
            if isinstance(task, list):
                for t in task:
                    if t.output is None:
                        raise Exception("Task %s did not produce output" % t.name)
                return list(t.output for t in task)
            else:
                if task.output is None:
                    raise Exception("Task %s did not produce output" % task.name)
                return task.output
        else:
            return None
        
    def mkDataItem(self, type, **kwargs):
        if self.builder is None:
            raise Exception("TaskSetRunner.mkDataItem() requires a builder")
        return self.builder.mkDataItem(type, **kwargs)
        
    def _completeTasks(self, active_task_l, done_task_s, done_l, dst_memento):
        for d in done_l:
            for i in range(len(active_task_l)):
                if active_task_l[i][1] == d:
                    tt = active_task_l[i][0]
                    tt.end = datetime.now()
                    self._log.debug("complete task %s" % tt.name)
                    if tt.result is None:
                        raise Exception("Task %s did not produce a result" % tt.name)
                    if tt.result.memento is not None:
                        dst_memento[tt.name] = tt.result.memento.model_dump()
                    else:
                        dst_memento[tt.name] = None
                    self.status |= tt.result.status 
                    if self.status:
                        self._log.debug("Task %s failed with status %d" % (tt.name, tt.result.status))
                    self._notify(tt, "leave")
                    done_task_s.add(tt)
                    active_task_l.pop(i)
                    break
    pass
        
    def buildDepMap(self, task : Union[TaskNode, List[TaskNode]]) -> Dict[TaskNode, Set[TaskNode]]:
        tasks = task if isinstance(task, list) else [task]
        dep_m = {}
        self._anon_tid = 1
        for t in tasks:
            self._buildDepMap(dep_m, t)

        return dep_m

    def _buildDepMap(self, dep_m, task : TaskNode):
        if task.name is None:
            task.name = "anon_%d" % self._anon_tid
            self._anon_tid += 1

        if task not in dep_m.keys():
            dep_m[task] = set(task[0] for task in task.needs)
            for need,block in task.needs:
                self._buildDepMap(dep_m, need)

@dc.dataclass
class SingleTaskRunner(TaskRunner):

    async def run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        changed = False
        for dep,_ in task.needs:
            changed |= dep.changed

        # TODO: create an evaluator for substituting param values
        eval = None

#        for field in dc.fields(task.params):
#            print("Field: %s" % field.name)

        input = TaskDataInput(
            name=task.name,
            changed=changed,
            srcdir=task.srcdir,
            rundir=self.rundir,
            params=task.params,
            inputs=[],
            memento=memento)

        # TODO: notify of task start
        ret : TaskDataResult = await task.task(self, input)
        # TODO: notify of task complete

        # Store the result
        task.output = TaskDataOutput(
            changed=ret.changed,
            output=ret.output.copy())

        # # By definition, none of this have run, since we just ran        
        # for dep in task.dependents:
        #     is_sat = True
        #     for need in dep.needs:
        #         if need.output is None:
        #             is_sat = False
        #             break
            
        #     if is_sat:
        #         # TODO: queue task for evaluation
        #     pass
        # TODO: 

        return ret
