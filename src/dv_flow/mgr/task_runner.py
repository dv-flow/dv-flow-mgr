import asyncio
import dataclasses as dc
from toposort import toposort
from typing import Any, Callable, List, Tuple, Union
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_node import TaskNode

@dc.dataclass
class TaskRunner(object):
    rundir : str

    # List of [Listener:Callable[Task],Recurisve:bool]
    listeners : List[Tuple[Callable['Task','Reason'], bool]] = dc.field(default_factory=list)

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

    async def run(self, task : Union[TaskNode,List[TaskNode]]):
        # First, build a depedency map
        tasks = task if isinstance(task, list) else [task]
        dep_m = {}
        for t in tasks:
            self._buildDepMap(dep_m, t)

        print("dep_m: %s" % str(dep_m))

        order = list(toposort(dep_m))

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
                                done_task_s.add(tt)
                                active_task_l.pop(i)
                                break
                if t not in done_task_s:
                    coro = asyncio.Task(t.do_run(
                        self,
                        self.rundir, # TODO
                        None)) # TODO: memento
                    active_task_l.append((t, coro))
               
            # Now, wait for tasks to complete
            if len(active_task_l):
                coros = list(at[1] for at in active_task_l)
                res = await asyncio.gather(*coros)


        pass

    def _buildDepMap(self, dep_m, task : TaskNode):
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

        for field in dc.fields(task.params):
            print("Field: %s" % field.name)

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
