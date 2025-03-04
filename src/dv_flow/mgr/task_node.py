import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
from typing import Any, Callable, ClassVar, Dict, List
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_params_ctor import TaskParamsCtor
from .param_ref_eval import ParamRefEval
from .param import Param

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
    passthrough : bool = False
    needs : List['TaskNode'] = dc.field(default_factory=list)
    rundir : str = dc.field(default=None)
    output : TaskDataOutput = dc.field(default=None)
    result : TaskDataResult = dc.field(default=None)

    _log : ClassVar = logging.getLogger("TaskNode")

    def __post_init__(self):
        if self.needs is None:
            self.needs = []

    async def do_run(self, 
                  runner,
                  rundir,
                  memento : Any = None) -> 'TaskDataResult':
        changed = False
        for dep in self.needs:
            changed |= dep.changed

        # TODO: Form dep-map from inputs
        # TODO: Order param sets according to dep-map
        in_params = []
        for need in self.needs:
            in_params.extend(need.output.output)

        # Create an evaluator for substituting param values
        eval = ParamRefEval()

        eval.setVar("in", in_params)

        for name,field in self.params.model_fields.items():
            value = getattr(self.params, name)
            if type(value) == str:
                if value.find("${{") != -1:
                    new_val = eval.eval(value)
                    setattr(self.params, name, new_val)
            elif isinstance(value, list):
                for i,elem in enumerate(value):
                    if elem.find("${{") != -1:
                        new_val = eval.eval(elem)
                        value[i] = new_val
            else:
                raise Exception("Unhandled param type: %s" % str(value))

        input = TaskDataInput(
            name=self.name,
            changed=changed,
            srcdir=self.srcdir,
            rundir=rundir,
            params=self.params,
            memento=memento)

        # TODO: notify of task start
        self.result : TaskDataResult = await self.task(self, input)
        # TODO: notify of task complete

        # TODO: form a dep map from the outgoing param sets
        dep_m = {}

        # Store the result
        self.output = TaskDataOutput(
            changed=self.result.changed,
            dep_m=dep_m,
            output=self.result.output.copy())

        # TODO: 

        return self.result

    def __hash__(self):
        return id(self)
    

@dc.dataclass
class TaskNodeCtor(object):
    """
    Factory for a specific task type
    - Produces a task parameters object, applying value-setting instructions
    - Produces a TaskNode
    """
    name : str
    srcdir : str
    paramT : Any
    passthrough : bool

    def getNeeds(self) -> List[str]:
        return []

    def mkTaskNode(self,
                   params,
                   srcdir=None,
                   name=None,
                   needs=None) -> TaskNode:
        raise NotImplementedError("mkTaskNode in type %s" % str(type(self)))

    def mkTaskParams(self, params : Dict = None) -> Any:
        obj = self.paramT()

        # Apply user-specified params
        if params is not None:
            for key,value in params.items():
                if not hasattr(obj, key):
                    raise Exception("Parameters class %s does not contain field %s" % (
                        str(type(obj)),
                        key))
                else:
                    if isinstance(value, Param):
                        if value.append is not None:
                            ex_value = getattr(obj, key, [])
                            ex_value.extend(value.append)
                            setattr(obj, key, ex_value)
                        elif value.prepend is not None:
                            ex_value = getattr(obj, key, [])
                            value = value.copy()
                            value.extend(ex_value)
                            setattr(obj, key, value)
                            pass
                        else:
                            raise Exception("Unhandled value spec: %s" % str(value))
                    else:
                        setattr(obj, key, value)
        return obj

@dc.dataclass
class TaskNodeCtorDefBase(TaskNodeCtor):
    """Task defines its own needs, that will need to be filled in"""
    needs : List['str']

    def __post_init__(self):
        if self.needs is None:
            self.needs = []

    def getNeeds(self) -> List[str]:
        return self.needs

@dc.dataclass
class TaskNodeCtorProxy(TaskNodeCtorDefBase):
    """Task has a 'uses' clause, so we delegate creation of the node"""
    uses : TaskNodeCtor

    def mkTaskNode(self, params, srcdir=None, name=None, needs=None) -> TaskNode:
        if srcdir is None:
            srcdir = self.srcdir
        node = self.uses.mkTaskNode(params=params, srcdir=srcdir, name=name, needs=needs)
        node.passthrough = self.passthrough
        return node
    
@dc.dataclass
class TaskNodeCtorTask(TaskNodeCtorDefBase):
    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult']

    def mkTaskNode(self, params, srcdir=None, name=None, needs=None) -> TaskNode:
        if srcdir is None:
            srcdir = self.srcdir

        node = TaskNode(name, srcdir, params, self.task, needs=needs)
        node.passthrough = self.passthrough
        node.task = self.task

        return node

@dc.dataclass
class TaskNodeCtorWrapper(TaskNodeCtor):
    T : Any

    def __call__(self, 
                 name=None,
                 srcdir=None,
                 params=None,
                 needs=None,
                 passthrough=None,
                 **kwargs):
        """Convenience method for direct creation of tasks"""
        if params is None:
            params = self.mkTaskParams(kwargs)
        
        node = self.mkTaskNode(
            srcdir=srcdir, 
            params=params, 
            name=name, 
            needs=needs)
        if passthrough is not None:
            node.passthrough = passthrough
        else:
            node.passthrough = self.passthrough

        return node

    def mkTaskNode(self, params, srcdir=None, name=None, needs=None) -> TaskNode:
        node = TaskNode(name, srcdir, params, self.T, needs=needs)
        node.passthrough = self.passthrough
        return node

    def mkTaskParams(self, params : Dict = None) -> Any:
        obj = self.paramT()

        # Apply user-specified params
        for key,value in params.items():
            if not hasattr(obj, key):
                raise Exception("Parameters class %s does not contain field %s" % (
                    str(type(obj)),
                    key))
            else:
                if isinstance(value, Param):
                    if value.append is not None:
                        ex_value = getattr(obj, key, [])
                        ex_value.extend(value.append)
                        setattr(obj, key, ex_value)
                    elif value.prepend is not None:
                        ex_value = getattr(obj, key, [])
                        value = value.copy()
                        value.extend(ex_value)
                        setattr(obj, key, value)
                        pass
                    else:
                        raise Exception("Unhandled value spec: %s" % str(value))
                else:
                    setattr(obj, key, value)
        return obj

def task(paramT,passthrough=False):
    """Decorator to wrap a task method as a TaskNodeCtor"""
    def wrapper(T):
        task_mname = T.__module__
        task_module = sys.modules[task_mname]
        ctor = TaskNodeCtorWrapper(
            name=T.__name__, 
            srcdir=os.path.dirname(os.path.abspath(task_module.__file__)), 
            paramT=paramT,
            passthrough=passthrough,
            T=T)
        return ctor
    return wrapper


