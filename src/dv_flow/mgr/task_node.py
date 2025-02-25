
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
from typing import Any, Callable, ClassVar, Dict, List
from .task_data import TaskDataInput, TaskDataOutput, TaskDataResult
from .task_params_ctor import TaskParamsCtor
from .param_ref_eval import ParamRefEval

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

        # TODO: create an evaluator for substituting param values
        eval = ParamRefEval()

        eval.setVar("in", in_params)

        for name,field in self.params.model_fields.items():
            value = getattr(self.params, name)
            if value.find("${{") != -1:
                new_val = eval.eval(value)
                setattr(self.params, name, new_val)
                print("TODO: expand")
            print("Field: %s %s" % (name, str(value)))
            pass

        input = TaskDataInput(
            changed=changed,
            srcdir=self.srcdir,
            rundir=rundir,
            params=self.params,
            memento=memento)

        # TODO: notify of task start
        ret : TaskDataResult = await self.task(self, input)
        # TODO: notify of task complete

        # TODO: form a dep map from the outgoing param sets
        dep_m = {}

        # Store the result
        self.output = TaskDataOutput(
            changed=ret.changed,
            dep_m=dep_m,
            output=ret.output.copy())

        # TODO: 

        return ret

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

        # Apply user-specified params
        for key,value in params.items():
            if not hasattr(obj, key):
                raise Exception("Parameters class %s does not contain field %s" % (
                    str(type(obj)),
                    key))
            else:
                setattr(obj, key, value)
        return obj
