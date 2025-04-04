import dataclasses as dc
from typing import Any, List, Tuple
from .task_def import TaskDef
from .task_node_ctor import TaskNodeCtor

@dc.dataclass
class Need(object):
    task : 'Task'
    cond : str = None

@dc.dataclass
class Task(object):
    """
    Type information about a task, linking it into the package
    to which it belongs.

    Needs in the Task class point to the resolved name. Overrides
    are applied when constructing a TaskNode DAG from tasks
    """
    name : str
    ctor : TaskNodeCtor = None
    paramT : Any = None
    uses : 'Task' = None
    needs : List[str] = dc.field(default_factory=list)
    subtasks : List['Task'] = dc.field(default_factory=list)
    srcinfo : Any = None

    @property
    def leafname(self):
        return self.name[self.name.rfind(".")+1:]

    def __post_init__(self):
        if self.name is None:
            self.name = self.task_def.name

