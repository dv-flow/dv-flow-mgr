#****************************************************************************
#* task_data.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import enum
import logging
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, ClassVar, Dict, Set, List, Tuple
from .fileset import FileSet
from toposort import toposort

class SeverityE(enum.Enum):
    Info = "info"
    Warning = "warning"
    Error = "error"

class TaskMarkerLoc(BaseModel):
    """
    Captures the source location of a marker
    """
    path : str
    line : int = dc.Field(default=-1)
    pos : int = dc.Field(default=-1)

class TaskMarker(BaseModel):
    """
    Captures marker data produced by a task.
    """
    msg : str
    severity : SeverityE
    loc : TaskMarkerLoc = dc.Field(default=None)

class TaskDataInput(BaseModel):
    """
    Input data to a task:

    * name - name of the task
    * changed - indicates whether any of this task's dependencies have changed
    * rundir - directory in which the task is to be run
    * params - parameters to the task
    * inputs - list of `TaskDataItem` that are consumed' by this task
    * memento - memento data previously returned by this task. None if no memento is available
    """
    name : str
    changed : bool
    srcdir : str
    rundir : str
    params : Any
    inputs : List[Any]
    memento : Any

class TaskDataResult(BaseModel):
    """
    Result data from a task:

    * changed - indicates whether the task modified its result data
    * output - list of output parameter sets
    * memento - memento data to be passed to the next invocation of the task
    * markers - list of markers produced by the task
    * status - status code (0=success, non-zero=failure)
    """
    changed : bool = dc.Field(default=True)
    output : List[Any] = dc.Field(default_factory=list)
    memento : Any = dc.Field(default=None)
    markers : List[TaskMarker] = dc.Field(default_factory=list)
    status : int = dc.Field(default=0)

class TaskDataOutput(BaseModel):
    changed : bool = True
    output : List[Any] = dc.Field(default_factory=list)
    dep_m : Dict[str,List[str]] = dc.Field(default_factory=dict)

class TaskDataParamOpE(enum.Enum):
    Set = enum.auto()
    Append = enum.auto()
    Prepend = enum.auto()
    PathAppend = enum.auto()
    PathPrepend = enum.auto()

class TaskDataParamKindE(enum.Enum):
    String = enum.auto()
    FilePath = enum.auto()
    SearchPath = enum.auto()
    List = enum.auto()

class TaskDataParamOp(BaseModel):
    op : TaskDataParamOpE
    value : Any

class TaskDataParam(BaseModel):
    kind : TaskDataParamKindE
    ops : List[TaskDataParamOp] = dc.Field(default_factory=list)

class TaskDataItem(BaseModel):
    """
    Base class for task data items

    * type - Name of the data item type
    * src - Name of the task that produced this item
    * seq - Sequence number of the item within the task
    """
    type : str
    src : str = None
    seq : int = -1

class TaskData(BaseModel):
    src : str = None
    deps : Dict[str,Set[str]] = dc.Field(default_factory=dict)
    changed : bool = False
    data : List[TaskDataItem] = dc.Field(default_factory=list)

    _log : ClassVar = logging.getLogger("TaskData")

    def addData(self, item : TaskDataItem):
        item.src = self.src
        self.data.append(item)

    def getFileSets(self, type=None, order=True) -> List[FileSet]:
        ret = []

        self._log.debug("getFileSets: filesets=%s" % str(self.filesets))

        if order:
            # The deps map specifies task dependencies

            filesets = filter(lambda x: x.type == "std.FileSet", self.data)

            candidate_fs = []
            for fs in filesets:
                self._log.debug("fs: %s" % str(fs))
                if type is None or fs.type in type:
                    candidate_fs.append(fs)
            self._log.debug("self.deps: %s" % str(self.deps))
            order = toposort(self.deps)

            self._log.debug("order: %s" % str(order))

            for order_s in order:
                self._log.debug("order_s: %s" % str(order_s))
                i = 0
                while i < len(candidate_fs):
                    fs = candidate_fs[i]
                    self._log.debug("fs.src: %s" % fs.src)
                    if fs.src in order_s:
                            self._log.debug("Add fileset")
                            ret.append(fs)
                            candidate_fs.pop(i)
                    else:
                        i += 1
            ret.extend(candidate_fs)
        else:
            for fs in self.filesets:
                if type is None or fs.type in type:
                    ret.append(fs)
        
        return ret

    def copy(self) -> 'TaskData':
        ret = TaskData()
        ret.src = self.src
        ret.basedir = self.basedir
        ret.params = self.params.copy()
        ret.filesets = self.filesets.copy()
        for d in self.deps:
            ret.deps.append(d.clone())
        ret.changed = self.changed
        return ret
    
    def setParamVal(self, name: str, kind : TaskDataParamKindE, value: Any):
        if name not in self.params:
            self.params[name] = TaskDataParam(kind=kind)
        self.params[name].ops.append(TaskDataParamOp(op=TaskDataParamOpE.Set, value=value))
    
    def getParamVal(self, name: str) -> Any:
        if name not in self.params.keys():
            raise Exception("No such parameter: %s" % name)
        param = self.params[name]
        value = param.ops[0].value

        if len(param.ops) > 1:
            for op in param.ops[1:]:
                if op.op == TaskDataParamOpE.Append:
                    if isinstance(value, list):
                        value.extend(op.value)
                    else:
                        value += op.value
                elif op.op == TaskDataParamOpE.Prepend:
                    if isinstance(value, list):
                        for nv in op.value:
                            value.insert(0, nv)
                    else:
                        value = op.value + value
                elif op.op == TaskDataParamOpE.PathAppend:
                    if isinstance(value, list):
                        value = ":".join(value)
                    value = value + ":" + op.value
                elif op.op == TaskDataParamOpE.PathPrepend:
                    if isinstance(value, list):
                        value = ":".join(value)
                    value = op.value + ":" + value

        return value

    @staticmethod    
    def merge(incoming : List['TaskData'], local : 'TaskData' = None) -> 'TaskData':
        """Merges incoming data with local settings and produces an output"""

        # Deal with the dependency trees first
        output = TaskData()

        # First, merge the dep maps of all the inputs
        output.deps = incoming[0].deps.copy()
        for deps in map(lambda i: i.deps, incoming[1:]):
            for k,v in deps.items():
                if k not in output.deps:
                    output.deps[k] = []
                for vi in v:
                    if vi not in output.deps[k]:
                        output.deps[k].append(v)

        # Process filesets
        for inp in incoming:
            for fs in inp.filesets:
                exists = False
                for fs_o in output.filesets:
                    if fs_o.name == fs.name and fs_o.src == fs.src:
                        exists = True
                        break
                if not exists:
                    output.addFileSet(fs.model_copy())

        # Now, deal with parameters
        # Find collisions first
        colliding_keys = set()
        passthrough_keys = set()

        for i in incoming:
            for k in i.params.keys():
                if k in passthrough_keys:
                    colliding_keys.add(k)
                else:
                    passthrough_keys.add(k)

        # Now, removes those that are locally set
        local_set_params = set()
        if local is not None:
            for k,v in local.params.items():
                if len(v.ops) == 1 and v.ops[0].op == TaskDataParamOpE.Set:
                    local_set_params.add(k)
                    # If are setting locally, it's not passthrough
                    passthrough_keys.remove(k)
                    if k in colliding_keys:
                        colliding_keys.remove(k)
        
        # Construct the passthrough set by removing 
        # colliding entries and those that we will set locally
        for k in colliding_keys:
            if k in passthrough_keys:
                passthrough_keys.remove(k)

        # For the remaining keys, check for conflicts by
        # confirming that the last 'set' in each incoming parameter
        # are equal
        for k in colliding_keys:
            value = None
            for i,inp in enumerate(incoming):
                value_i = None
                param = inp.params[k]
                if len(param.ops) == 1:
                    value_i = param.ops[0].value
                else:
                    # Iterate in reverse over the operations
                    for op in param.ops[::-1]:
                        if op.op == TaskDataParamOpE.Set:
                            value_i = op.value
                            break
                if not i:
                    value = value_i
                else:
                    if value != value_i:
                        raise Exception("Parameter %s has conflicting values (%s %s)" % (
                            k,
                            str(value),
                            value(value_i)))


        # Now, we need to construct the result
        # - copy over passthrough parameters
        # - add locally-set parameters
        # - for others
        #   - Apply full list for first input
        #   - Apply all beyond the last 'set' operation for others
        for k in passthrough_keys:
            # Find an input that has the parameter
            for inp in incoming:
                if k in inp.params:
                    break
            # Find the value of the param
            param = inp.params[k]

            if len(param.ops) == 1:
                output.params[k] = TaskDataParam(kind=param.kind)
                output.params[k].ops.append(param.ops[0])
            else:
                for op in param.ops[::-1]:
                    if op.op == TaskDataParamOpE.Set:
                        output.params[k] = TaskDataParam(kind=param.kind)
                        output.params[k].ops.append(op)
                        break
        for k in local_set_params:
            output.params[k] = local.params[k].model_copy()

        for k in colliding_keys:
            value = None
            for i,inp in enumerate(incoming):
                # Find the last location that performs a 'set' 
                last_set_i = -1
                param = inp.params[k]
                if len(param.ops) == 1:
                    last_set_i = 0
                else:
                    # Iterate in reverse over the operations
                    for j,op in enumerate(param.ops[::-1]):
                        if op.op == TaskDataParamOpE.Set:
                            last_set_i = j
                            break
                
                if not i:
                    # Copy the full list, including the last 'set'
                    output.params[k].ops = param.param[last_set_i:].copy()
                else:
                    # append any additional directives
                    if last_set_i+1 < len(param.ops):
                        output.params[k].extend(param.ops[last_set_i+1:])

        return output
