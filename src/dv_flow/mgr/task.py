import dataclasses as dc
from typing import Any, Callable, Dict, List, Tuple, Union
from .srcinfo import SrcInfo
from .task_def import TaskDef, RundirE, PassthroughE, ConsumesE

@dc.dataclass
class Need(object):
    task : 'Task'
    cond : str = None

@dc.dataclass
class StrategyGenerate(object):
    shell : str = "pytask"
    run : str = None

@dc.dataclass
class Strategy(object):
    generate : StrategyGenerate = None
    matrix : Dict[str, List[Any]] = dc.field(default_factory=dict)

@dc.dataclass
class Task(object):
    """
    Type information about a task, linking it into the package
    to which it belongs.

    Needs in the Task class point to the resolved name. Overrides
    are applied when constructing a TaskNode DAG from tasks
    """
    name : str
    desc: str = ""
    doc : str = ""
    paramT : Any = None
    uses : 'Task' = None
    package : 'Package' = None
    iff : str = None
    needs : List[str] = dc.field(default_factory=list)
    consumes : Union[ConsumesE, List[Dict[str, Any]]] = dc.field(default=None)
    passthrough : Union[PassthroughE, List[Dict[str, Any]]] = dc.field(default=None)
    rundir : RundirE = None
    # TODO: strategy / matrix
    subtasks : List['Task'] = dc.field(default_factory=list)
    strategy : Strategy = dc.field(default=None)
    run : str = None
    shell : str = "bash"
    srcinfo : SrcInfo = None
    taskdef : 'TaskDef' = None

    @property
    def leafname(self):
        return self.name[self.name.rfind(".")+1:]

    def __post_init__(self):
        if self.name is None:
            self.name = self.task_def.name

    def dump(self):
        task = {
            "name": self.name,
            "paramT": str(type(self.paramT)),
            "rundir": str(self.rundir),
        }

        if self.uses is not None:
            task["uses"] = self.uses.name
        if self.needs is not None and len(self.needs):
            task["needs"] = [n.name for n in self.needs]
        if self.subtasks is not None and len(self.subtasks):
            task["subtasks"] = [t.dump() for t in self.subtasks]
        if self.run is not None:
            task["run"] = self.run
        if self.shell is not None:
            task["shell"] = self.shell
        if self.srcinfo is not None:
            task["srcinfo"] = self.srcinfo.dump()

        return task

    def __hash__(self):
        return id(self)

