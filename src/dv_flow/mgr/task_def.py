#****************************************************************************
#* task_def.py
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
import pydantic.dataclasses as dc
import enum
from pydantic import BaseModel
from typing import Any, Dict, List, Union, Tuple
from .param_def import ParamDef
from .task_output import TaskOutput

@dc.dataclass
class TaskSpec(object):
    name : str

@dc.dataclass
class NeedSpec(object):
    name : str
    block : bool = False

class RundirE(enum.Enum):
    Unique = "unique"
    Inherit = "inherit"

class ConsumesE(enum.Enum):
    No = "none"
    All = "all"

class PassthroughE(enum.Enum):
    No = "none"
    All = "all"
    Unused = "unused"


class StrategyDef(BaseModel):
    matrix : Dict[str,List[Any]] = dc.Field(
        default_factory=dict,
        description="Matrix of parameter values to explore")

class TaskDef(BaseModel):
    """Holds definition information (ie the YAML view) for a task"""
    name : str = dc.Field(
        title="Task Name",
        description="The name of the task")
    fullname : str = dc.Field(default=None)
#    type : Union[str,TaskSpec] = dc.Field(default_factory=list)
    uses : str = dc.Field(
        default=None,
        title="Base type",
        description="Task from which this task is derived")
    pytask : str = dc.Field(
        default=None,
        title="Python method name",
        description="Python method to execute to implement this task")
    strategy : StrategyDef = dc.Field(
        default=None)
    tasks: List['TaskDef'] = dc.Field(
        default_factory=list,
        description="Sub-tasks")
    desc : str = dc.Field(
        default="",
        title="Task description",
        description="Short description of the task's purpose")
    doc : str = dc.Field(
        default="",
        title="Task documentation",
        description="Full documentation of the task")
#    needs : List[Union[str,NeedSpec,TaskSpec]] = dc.Field(
    needs : List[Union[str]] = dc.Field(
        default_factory=list, 
        description="List of tasks that this task depends on")
    params: Dict[str,Union[str,list,ParamDef]] = dc.Field(
        default_factory=dict, 
        alias="with",
        description="Parameters for the task")
    rundir : RundirE = dc.Field(
        default=RundirE.Unique,
        description="Specifies handling of this tasks's run directory")
    passthrough: Union[PassthroughE, List[Any], None] = dc.Field(
        default=None,
        description="Specifies whether this task should pass its inputs to its output")
    consumes : Union[ConsumesE, List[Any], None] = dc.Field(
        default=None,
        description="Specifies matching patterns for parameter sets that this task consumes")

#    out: List[TaskOutput] = dc.Field(default_factory=list)

    def copy(self) -> 'TaskDef':
        ret = TaskDef(
            name=self.name,
            type=self.type,
            depends=self.depends.copy())
        return ret  

