
import dataclasses as dc
from typing import Any, List
from .task_node import TaskNode

@dc.dataclass
class TaskGenInputData(object):
    params : Any

@dc.dataclass
class TaskGenCtxt(object):
    rundir : str
    input : TaskNode
    builder : 'TaskGraphBuilder'
    body : List['Task'] = dc.field(default_factory=list)
    tasks : List['TaskNode'] = dc.field(default_factory=list)

    def mkTaskNode(self, type_t, name=None, srcdir=None, needs=None, **kwargs):
        return self.builder.mkTaskNode(type_t, name, srcdir, needs, **kwargs)

    def addTask(self, task : 'TaskNode'):
        if task is None:
            raise Exception("Task is None")
        self.tasks.append(task)

    def mkName(self, leaf):
        # TODO: add on context
        return leaf

    def marker(self, m):
        pass

    def error(self, msg):
        pass

