import os
import sys
import dataclasses as dc
import pydantic.dataclasses as pdc
import logging
import toposort
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
    consumes : List[Any] = dc.field(default_factory=list)
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
        self._log.debug("--> do_run: %s" % self.name)
        changed = False
        for dep in self.needs:
            changed |= dep.changed

        # TODO: Form dep-map from inputs

        dep_m = {}
        for need in self.needs:
            self._log.debug("dep %s dep_m: %s" % (need.name, str(dep_m)))
            for subdep in need.output.dep_m.keys():
                if subdep not in dep_m.keys():
                    dep_m[subdep] = []
                dep_m[subdep].extend(need.output.dep_m[subdep])

        self._log.debug("input dep_m: %s" % str(dep_m))
        sorted = toposort.toposort(dep_m)

        in_params_m = {}
        for need in self.needs:
            for p in need.output.output:
                if p.src not in in_params_m.keys():
                    in_params_m[p.src] = []
                in_params_m[p.src].append(p)

        # in_params holds parameter sets ordered by dependency
        in_params = []
        for sorted_s in sorted:
            self._log.debug("sorted_s: %s" % str(sorted_s))
            for dep in sorted_s:
                if dep in in_params_m.keys():
                    self._log.debug("(%s) Extend with: %s" % (dep, str(in_params_m[dep])))
                    in_params.extend(in_params_m[dep])

        self._log.debug("in_params[1]: %s" % ",".join(p.src for p in in_params))

        # Create an evaluator for substituting param values
        eval = ParamRefEval()

        self._log.debug("in_params[2]: %s" % ",".join(p.src for p in in_params))
        eval.setVar("in", in_params)

        for name,field in self.params.model_fields.items():
            value = getattr(self.params, name)
            if type(value) == str:
                if value.find("${{") != -1:
                    new_val = eval.eval(value)
                    self._log.debug("Param %s: Evaluate expression \"%s\" => \"%s\"" % (name, value, new_val))
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

        self._log.debug("--> Call task method %s" % str(self.task))
        self.result : TaskDataResult = await self.task(self, input)
        self._log.debug("<-- Call task method %s" % str(self.task))

        output=self.result.output.copy()
        for out in output:
            out.src = self.name

        self._log.debug("output[1]: %s" % str(output))

        if self.passthrough:
            self._log.debug("passthrough: %s" % self.name)
            # Add an entry for ourselves
            dep_m[self.name] = list(need.name for need in self.needs)

            if self.consumes is None and len(self.consumes):
                self._log.debug("Propagating all input parameters to output")
                for need in self.needs:
                    output.extend(need.output.output)
            else:
                # Filter out parameter sets that were consumed
                self._log.debug("Propagating non-consumed input parameters to output")
                for need in self.needs:
                    for out in need.output.output:
                        consumed = False
                        for c in self.consumes:
                            match = False
                            for k,v in c.items():
                                if hasattr(out, k) and getattr(out, k) == v:
                                    match = True
                                    break
                            if match:
                                consumed = True
                                break
                        
                        if not consumed:
                            self._log.debug("Propagating type %s from %s" % (
                                getattr(out, "type", "<unknown>"),
                                getattr(out, "src", "<unknown>")))
                            output.append(out)
        else:
            # empty dependency map
            dep_m = {
                self.name : []
            }

        self._log.debug("output dep_m: %s" % str(dep_m))
        self._log.debug("output[2]: %s" % str(output))

        # Store the result
        self.output = TaskDataOutput(
            changed=self.result.changed,
            dep_m=dep_m,
            output=output)

        # TODO: 
        self._log.debug("<-- do_run: %s" % self.name)

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
    consumes : List[Any]

    def __call__(self, 
                 name=None,
                 srcdir=None,
                 params=None,
                 needs=None,
                 passthrough=None,
                 consumes=None,
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
        if consumes is not None:
            if node.consumes is None:
                node.consumes = consumes
            else:
                node.consumes.extend(consumes)
        else:
            if node.consumes is None:
                node.consumes = self.consumes
            else:
                node.consumes.extend(consumes)

        return node

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
        node.consumes = self.consumes
        return node
    
@dc.dataclass
class TaskNodeCtorTask(TaskNodeCtorDefBase):
    task : Callable[['TaskRunner','TaskDataInput'],'TaskDataResult']

    def mkTaskNode(self, params, srcdir=None, name=None, needs=None) -> TaskNode:
        if srcdir is None:
            srcdir = self.srcdir

        node = TaskNode(name, srcdir, params, self.task, needs=needs)
        node.passthrough = self.passthrough
        node.consumes = self.consumes
        node.task = self.task

        return node

@dc.dataclass
class TaskNodeCtorWrapper(TaskNodeCtor):
    T : Any



    def mkTaskNode(self, params, srcdir=None, name=None, needs=None) -> TaskNode:
        node = TaskNode(name, srcdir, params, self.T, needs=needs)
        node.passthrough = self.passthrough
        node.consumes = self.consumes
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

def task(paramT,passthrough=False,consumes=None):
    """Decorator to wrap a task method as a TaskNodeCtor"""
    def wrapper(T):
        task_mname = T.__module__
        task_module = sys.modules[task_mname]
        ctor = TaskNodeCtorWrapper(
            name=T.__name__, 
            srcdir=os.path.dirname(os.path.abspath(task_module.__file__)), 
            paramT=paramT,
            passthrough=passthrough,
            consumes=consumes,
            T=T)
        return ctor
    return wrapper


