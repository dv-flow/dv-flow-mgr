#****************************************************************************
#* task_data.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
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
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, Set, List, Tuple
from .fileset import FileSet
from toposort import toposort

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

class TaskData(BaseModel):
    src : str = None
    params : Dict[str,TaskDataParam] = dc.Field(default_factory=dict)
    deps : Dict[str,Set[str]] = dc.Field(default_factory=dict)
    filesets : List[FileSet] = dc.Field(default_factory=list)
    changed : bool = False

    def hasParam(self, name: str) -> bool:
        return name in self.params
    
    def getParam(self, name: str) -> Any:
        return self.params[name]
    
    def setParam(self, name: str, value: Any):
        self.params[name] = value

    def addFileSet(self, fs : FileSet):
        self.filesets.append(fs)

    def getFileSets(self, type=None, order=True) -> List[FileSet]:
        ret = []

        if order:
            # The deps map specifies task dependencies

            candidate_fs = []
            for fs in self.filesets:
                if type is None or fs.type in type:
                    candidate_fs.append(fs)

            order = toposort(self.deps)

            for order_s in order:
                for fs in candidate_fs:
                    if fs.src in order_s:
                            ret.append(fs)
        else:
            for fs in self.filesets:
                if type is None or fs.type in type:
                    ret.append(fs)
        
        return ret

    def copy(self) -> 'TaskData':
        ret = TaskData()
        ret.src = self.src
        ret.params = self.params.copy()
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
