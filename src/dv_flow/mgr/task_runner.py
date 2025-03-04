import asyncio
import json
import os
import re
import dataclasses as dc
import logging
from toposort import toposort
from typing import Any, Callable, ClassVar, List, Tuple, Union
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_node import TaskNode

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
    nproc : int = 8

    _anon_tid : int = 1

    _log : ClassVar = logging.getLogger("TaskSetRunner")

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
        tasks = task if isinstance(task, list) else [task]
        dep_m = {}
        self._anon_tid = 1
        for t in tasks:
            self._buildDepMap(dep_m, t)

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
                self._log.debug("- {%s}", ",".join(t.name for t in active_s))

        active_task_l = []
        done_task_s = set()
        for active_s in order:
            done = True
            for t in active_s:
                while len(active_task_l) >= self.nproc and t not in done_task_s:
                    # Wait for at least one job to complete
                    done, pending = await asyncio.wait(at[1] for at in active_task_l)
                    for d in done:
                        for i in range(len(active_task_l)):
                            if active_task_l[i][1] == d:
                                tt = active_task_l[i][0]
                                if tt.result.memento is not None:
                                    dst_memento[tt.name] = tt.result.memento.model_dump()
                                else:
                                    dst_memento[tt.name] = None
                                self._notify(tt, "leave")
                                done_task_s.add(tt)
                                active_task_l.pop(i)
                                break
                if t not in done_task_s:
                    memento = src_memento.get(t.name, None)
                    dirname = t.name
                    invalid_chars_pattern = r'[\/:*?"<>|#%&{}\$\\!\'`;=@+]'
                    # Replace invalid characters with the replacement string.
                    dirname = re.sub(invalid_chars_pattern, '_', dirname)

                    rundir = os.path.join(self.rundir, dirname)

                    if not os.path.isdir(rundir):
                        os.makedirs(rundir, exist_ok=True)

                    self._notify(t, "enter")
                    coro = asyncio.Task(t.do_run(
                        self,
                        rundir,
                        memento)) 
                    active_task_l.append((t, coro))
               
            # Now, wait for tasks to complete
            if len(active_task_l):
                # TODO: Shouldn't gather here -- reach to each completion
                coros = list(at[1] for at in active_task_l)
                res = await asyncio.gather(*coros)
                for tt in active_task_l:
                    if tt[0].result.memento is not None:
                        dst_memento[tt[0].name] = tt[0].result.memento.model_dump()
                    else:
                        dst_memento[tt[0].name] = None
                    self._notify(tt[0], "leave")
                active_task_l.clear()

        with open(os.path.join(self.rundir, "cache", "mementos.json"), "w") as f:
            json.dump(dst_memento, f)

        if isinstance(task, list):
            return list(t.output for t in task)
        else:
            return task.output



        pass

    def _buildDepMap(self, dep_m, task : TaskNode):
        if task.name is None:
            task.name = "anon_%d" % self._anon_tid
            self._anon_tid += 1

        if task not in dep_m.keys():
            dep_m[task] = set(task.needs)
            for need in task.needs:
                self._buildDepMap(dep_m, need)

@dc.dataclass
class SingleTaskRunner(TaskRunner):

    async def run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        changed = False
        for dep in task.needs:
            changed |= dep.changed

        # TODO: create an evaluator for substituting param values
        eval = None

#        for field in dc.fields(task.params):
#            print("Field: %s" % field.name)

        input = TaskDataInput(
            changed=changed,
            srcdir=task.srcdir,
            rundir=self.rundir,
            params=task.params,
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
