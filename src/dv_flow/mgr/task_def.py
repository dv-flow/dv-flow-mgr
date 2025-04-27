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
import pydantic
import pydantic.dataclasses as dc
import enum
from pydantic import BaseModel, ConfigDict
from typing import Any, Dict, List, Union, Tuple
from .param_def import ParamDef
from .srcinfo import SrcInfo
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
    chain: Union[bool, None] = dc.Field(default=None)
    matrix : Union[Dict[str,List[Any]],None] = dc.Field(
        default=None,
        description="Matrix of parameter values to explore")

class TaskBodyDef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pytask : Union[str, None] = dc.Field(
        default=None,
        description="Python method to execute to implement this task")
    tasks: Union[List['TaskDef'],None] = dc.Field(
        default_factory=list,
        description="Sub-tasks")
    shell: Union[str, None] = dc.Field(
        default=None,
        description="Specifies the shell to run")
    run: str = dc.Field(
        default=None,
        description="Shell command to execute for this task")
#    pydep  : Union[str, None] = dc.Field(
#        default=None,
#        description="Python method to check up-to-date status for this task")

class TasksBuilder(BaseModel):
    # TODO: control how much data this task is provided?
    srcinfo : SrcInfo = dc.Field(default=None)
    pydef : Union[str, None] = dc.Field(
        default=None,
        description="Python method to build the subgraph")

class Tasks(BaseModel):
    tasks: Union[List['TaskDef'], TasksBuilder] = dc.Field(
        default_factory=list,
        description="Sub-tasks")

class TaskDef(BaseModel):
    """Holds definition information (ie the YAML view) for a task"""
    name : Union[str, None] = dc.Field(
        title="Task Name",
        description="The name of the task",
        default=None)
    override : Union[str, None] = dc.Field(
        title="Overide Name",
        description="The name of the task to override",
        default=None)
    uses : str = dc.Field(
        default=None,
        title="Base type",
        description="Task from which this task is derived")
    body: List['TaskDef'] = dc.Field(
        default_factory=list,
        description="Sub-tasks")
    iff : Union[str, bool, Any] = dc.Field(
        default=None,
        title="Task enable condition",
        description="Condition that must be true for this task to run")
    pytask : str = dc.Field(
        default=None,
        description="Python-based implementation (deprecated)")
    run : str = dc.Field(
        default=None,
        description="Shell-based implementation")
    shell: str = dc.Field(
        default="bash",
        description="Shell to use for shell-based implementation")
    strategy : StrategyDef = dc.Field(
        default=None)
    desc : str = dc.Field(
        default="",
        title="Task description",
        description="Short description of the task's purpose")
    doc : str = dc.Field(
        default="",
        title="Task documentation",
        description="Full documentation of the task")
    needs : List[Union[str]] = dc.Field(
        default_factory=list, 
        description="List of tasks that this task depends on")
    params: Dict[str,Union[str,list,bool,ParamDef]] = dc.Field(
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
    srcinfo : SrcInfo = dc.Field(default=None)
    

TaskDef.model_rebuild()

