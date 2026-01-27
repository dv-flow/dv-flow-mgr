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
from pydantic import BaseModel, ConfigDict, Field, AliasChoices, field_validator, model_validator
from typing import Any, Dict, List, Union, Tuple
from .param_def import ParamDef
from .srcinfo import SrcInfo
from .task_output import TaskOutput
from .cache_provider import CompressionType

@dc.dataclass
class TaskSpec(object):
    name : str

@dc.dataclass
class NeedSpec(object):
    name : str
    block : bool = False
    srcinfo : SrcInfo = None

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

class GenerateSpec(BaseModel):
    shell: Union[str, None] = dc.Field(
        default=None,
        description="Shell to use for running the generate command. Defaults to 'bash'")
    run: str = dc.Field(
        description="Shell command to execute. Must output valid YAML task definitions to stdout")

class StrategyDef(BaseModel):
    chain: Union[bool, None] = dc.Field(
        default=None,
        description="Enable chain strategy: run body tasks sequentially with each consuming output of previous task")
    generate: Union[GenerateSpec, None] = dc.Field(
        default=None,
        description="Enable generate strategy: dynamically create tasks by running a shell command that outputs task definitions")
    matrix : Union[Dict[str,List[Any]],None] = dc.Field(
        default=None,
        description="Matrix of parameter values to explore. Creates one task instance per combination of values")
    body: List['TaskDef'] = dc.Field(
        default_factory=list,
        description="Body tasks for strategy execution. Used with chain and matrix strategies")

class CacheDef(BaseModel):
    """Cache configuration for a task"""
    model_config = ConfigDict(extra='forbid')
    
    enabled: bool = dc.Field(
        default=True,
        description="Whether caching is enabled for this task")
    
    hash: List[str] = dc.Field(
        default_factory=list,
        description="Extra hash expressions to include in cache key")
    
    compression: CompressionType = dc.Field(
        default=CompressionType.No,
        description="Compression type for cached artifacts")

class TaskBodyDef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pytask : Union[str, None] = dc.Field(
        default=None,
        description="Python method to execute to implement this task",
        )
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
    model_config = ConfigDict(extra='forbid')
    name : Union[str, None] = dc.Field(
        title="Task Name",
        description="The name of the task",
        default=None)
    root : Union[str, None] = dc.Field(
        title="Root Task Name",
        description="The name of the task (marked as root scope)",
        default=None)
    export : Union[str, None] = dc.Field(
        title="Export Task Name",
        description="The name of the task (marked as export scope)",
        default=None)
    local : Union[str, None] = dc.Field(
        title="Local Task Name",
        description="The name of the task (marked as local scope)",
        default=None)
    override : Union[str, None] = dc.Field(
        title="Overide Name",
        description="The name of the task to override",
        default=None)
    uses : str = dc.Field(
        default=None,
        title="Base type",
        description="Task from which this task is derived")
    scope : Union[str, List[str], None] = dc.Field(
        default=None,
        title="Task visibility scope",
        description="Visibility scope: 'root' (executable), 'export' (visible outside package), 'local' (fragment-only)")
    body: List['TaskDef'] = Field(
        default_factory=list,
        validation_alias=AliasChoices('body', 'tasks'),
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
    feeds : List[Union[str]] = dc.Field(
        default_factory=list,
        description="List of tasks that depend on this task (inverse of needs)")
    params: Dict[str,Union[str,list,int,bool,dict]] = dc.Field(
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
    uptodate : Union[bool, str, None] = dc.Field(
        default=None,
        description="Up-to-date check: false=always run, string=Python method, None=use default check")
    cache : Union[CacheDef, bool, None] = dc.Field(
        default=None,
        description="Cache configuration. True=enabled with defaults, False=disabled, CacheDef=custom config")
    tags : List[Union[str, Dict[str, Any]]] = dc.Field(
        default_factory=list,
        description="Tags as type references with optional parameter overrides")
    srcinfo : SrcInfo = dc.Field(default=None)
    
    @model_validator(mode='before')
    @classmethod
    def consolidate_name_and_scope(cls, data):
        """Consolidate inline scope markers (root, export, local) into name and scope fields"""
        if not isinstance(data, dict):
            return data
        
        # Normalize cache field: convert bool to CacheDef
        if 'cache' in data and isinstance(data['cache'], bool):
            data['cache'] = {'enabled': data['cache']}
        
        # Count how many name-defining fields are set in the input
        name_fields = []
        for field in ['name', 'root', 'export', 'local', 'override']:
            if field in data and data[field] is not None:
                name_fields.append((field, data[field]))
        
        if len(name_fields) == 0:
            # No name specified - this is valid for some contexts
            return data
        
        if len(name_fields) > 1:
            field_names = ', '.join([f"'{field}'" for field, _ in name_fields])
            raise ValueError(f"Only one of name/root/export/local/override can be specified, got: {field_names}")
        
        field, value = name_fields[0]
        
        # Set the name from whichever field was used
        if field != 'override':
            data['name'] = value
        
        # If inline scope marker was used, set the appropriate scope
        if field in ['root', 'export', 'local']:
            # Get existing scope
            existing_scope = data.get('scope')
            
            if existing_scope is None:
                data['scope'] = field
            elif isinstance(existing_scope, list):
                if field not in existing_scope:
                    existing_scope.append(field)
            elif existing_scope != field:
                data['scope'] = [existing_scope, field]
        
        return data

TaskDef.model_rebuild()
