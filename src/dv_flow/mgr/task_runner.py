import dataclasses as dc
from .task_data import TaskDataInput, TaskDataResult
from typing import Any, Callable, List, Tuple

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
class SingleTaskRunner(TaskRunner):

    async def run(self, 
                  task : 'Task',
                  memento : Any = None) -> 'TaskDataResult':
        changed = False
        for dep in task.needs:
            changed |= dep.changed

        # TODO: create an evaluator for substituting param values
        eval = None

        params = task.params.mk(eval)

        input = TaskDataInput(
            changed=changed,
            srcdir=task.srcdir,
            rundir=self.rundir,
            params=params,
            memento=memento)
        
        ret = await task.run(self, input)

        return ret
