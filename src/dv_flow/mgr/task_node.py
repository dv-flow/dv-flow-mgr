
import dataclasses as dc
import logging
from typing import Any, Callable, ClassVar, Dict, List
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_params_ctor import TaskParamsCtor

@dc.dataclass
class TaskNode(object):
    """Executable view of a task"""
    # Ctor fields -- must specify on construction
    name : str
    srcdir : str
    # This can be the resolved parameters
    params : TaskParamsCtor 

    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult']

    # Runtime fields -- these get populated during execution
    changed : bool = False
    needs : List['TaskNode'] = dc.field(default_factory=list)
    rundir : str = dc.field(default=None)
    output : TaskDataOutput = dc.field(default=None)

    _log : ClassVar = logging.getLogger("TaskNode")

    def __hash__(self):
        return id(self)
    
@staticmethod
def task(paramT):
    def wrapper(T):
        ctor = TaskNodeCtorWrapper(T.__name__, T, paramT)
        return ctor
    return wrapper

@dc.dataclass
class TaskNodeCtor(object):
    """
    Factory for a specific task type
    - Produces a task parameters object, applying value-setting instructions
    - Produces a TaskNode
    """
    name : str


    def mkTaskNode(self, srcdir, params, name=None) -> TaskNode:
        raise NotImplementedError("mkTaskNode in type %s" % str(type(self)))

    def mkTaskParams(self, params : Dict) -> Any:
        raise NotImplementedError("mkTaskParams in type %s" % str(type(self)))

@dc.dataclass
class TaskNodeCtorWrapper(TaskNodeCtor):
    T : Any
    paramT : Any

    def __call__(self, 
                 srcdir, 
                 name=None, 
                 params=None, 
                 needs=None,
                 **kwargs):
        """Convenience method for direct creation of tasks"""
        if params is None:
            params = self.mkTaskParams(kwargs)
        
        node = self.mkTaskNode(srcdir, params, name)
        if needs is not None:
            node.needs.extend(needs)
        return node

    def mkTaskNode(self, srcdir, params, name=None) -> TaskNode:
        node = TaskNode(name, srcdir, params, self.T)
        return node

    def mkTaskParams(self, params : Dict) -> Any:
        obj = self.paramT()
        # TODO: apply user-specified params
        return obj
