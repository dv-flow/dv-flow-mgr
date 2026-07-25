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
from .cli_def import CliDef
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
    matrix : Union[Dict[str,Union[str,List[Any]]],None] = dc.Field(
        default=None,
        description="Matrix of parameter values to explore. Creates one task instance per combination of values. An axis value may be a `${{ }}` expression that resolves to a list (e.g. `image: \"${{ images }}\"`), evaluated at graph-build.")
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

class ControlCaseDef(BaseModel):
    """Definition for a single case in a match control construct"""
    when: Union[str, None] = dc.Field(
        default=None,
        description="Condition expression for this case")
    default: Union[bool, None] = dc.Field(
        default=None,
        description="Mark this case as the default/fallback")
    body: List['TaskDef'] = dc.Field(
        default_factory=list,
        description="Tasks to execute if this case matches")

class ControlStateDef(BaseModel):
    """Definition for loop state management"""
    type: Union[str, None] = dc.Field(
        default=None,
        description="Type reference for state validation")
    init: Dict[str, Any] = dc.Field(
        default_factory=dict,
        description="Initial state values for first iteration")
    feedback: Union[str, None] = dc.Field(
        default=None,
        description="Expression to transform iteration output to next iteration input")

class ControlDef(BaseModel):
    """Runtime control flow definition"""
    type: str = dc.Field(
        description="Control flow type: if, match, while, do-while, or repeat")
    cond: Union[str, None] = dc.Field(
        default=None,
        description="Condition expression for if/while constructs")
    until: Union[str, None] = dc.Field(
        default=None,
        description="Early exit condition for do-while/repeat loops")
    max_iter: Union[int, None] = dc.Field(
        default=None,
        description="Maximum iteration count for loops (safety bound)")
    count: Union[int, None] = dc.Field(
        default=None,
        description="Exact iteration count for repeat loops")
    cases: List[ControlCaseDef] = dc.Field(
        default_factory=list,
        description="Cases for match construct")
    else_body: List['TaskDef'] = dc.Field(
        default_factory=list,
        alias="else",
        description="Tasks to execute for else branch of if construct")
    state: Union[ControlStateDef, None] = dc.Field(
        default=None,
        description="State management configuration for loops")
    
    @model_validator(mode='after')
    def validate_control_type(self):
        """Validate that required fields are present for each control type"""
        if self.type == 'if':
            if self.cond is None:
                raise ValueError("'if' control type requires 'cond' field")
        elif self.type == 'match':
            if not self.cases:
                raise ValueError("'match' control type requires at least one 'cases' entry")
        elif self.type == 'while':
            if self.cond is None:
                raise ValueError("'while' control type requires 'cond' field")
            if self.max_iter is None:
                raise ValueError("'while' control type requires 'max_iter' field")
        elif self.type == 'do-while':
            if self.until is None:
                raise ValueError("'do-while' control type requires 'until' field")
            if self.max_iter is None:
                raise ValueError("'do-while' control type requires 'max_iter' field")
        elif self.type == 'repeat':
            if self.count is None:
                raise ValueError("'repeat' control type requires 'count' field")
        else:
            raise ValueError(f"Unknown control type: {self.type}. Must be one of: if, match, while, do-while, repeat")
        return self

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

#: Keys allowed on a `set:` scope item (a list element that has a `set` key).
_SET_SCOPE_KEYS = ("uses", "path", "set")


def _validate_set_list(items, ctx="set"):
    """Validate the shape of a `set:` list (recursively). Each element is either:
      * an assignment map ({name: value, ...}) — rebinds scoped variables, or
      * a scope item ({uses?, path?, set: [...]}) — identified by a `set` key.
    Raises ValueError with a user-facing message on any malformed element."""
    if not isinstance(items, list):
        raise ValueError(
            "'%s' must be a list of assignment maps and/or scope items" % ctx)
    for i, elem in enumerate(items):
        where = "%s[%d]" % (ctx, i)
        if not isinstance(elem, dict):
            raise ValueError(
                "%s must be a map (assignment {name: value} or scope "
                "{uses/path, set: [...]}), got %s" % (where, type(elem).__name__))
        if "set" in elem:
            # Scope item. Its `set` value must be a list; a task parameter may
            # not be named 'set' (the key is reserved for nested scope items).
            if not isinstance(elem["set"], list):
                raise ValueError(
                    "%s: the 'set' key is reserved for nested scope items and "
                    "must be a list; a task parameter may not be named 'set'" % where)
            for k in elem.keys():
                if k not in _SET_SCOPE_KEYS:
                    raise ValueError(
                        "%s: unexpected key '%s' in a scope item; only %s are "
                        "allowed" % (where, k, "/".join(_SET_SCOPE_KEYS)))
            for mk in ("uses", "path"):
                if mk in elem and not isinstance(elem[mk], str):
                    raise ValueError(
                        "%s: '%s' matcher must be a string glob" % (where, mk))
            _validate_set_list(elem["set"], "%s.set" % where)
        else:
            # Assignment map — keys are variable/param names (strings).
            for k in elem.keys():
                if not isinstance(k, str):
                    raise ValueError(
                        "%s: assignment key %r must be a string name" % (where, k))
    return items


class SummaryDef(BaseModel):
    """Selects a framework-provided summary renderer."""
    model_config = ConfigDict(extra='forbid')
    builtin : str = dc.Field(
        description="Name of a built-in summary renderer. Currently: 'task-summary'")


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
    abstract : bool = dc.Field(
        default=False,
        description="Abstract task: may only be reached via 'uses:' or as an "
                    "override replacement, never invoked directly")
    elaborate : Union[str, None] = dc.Field(
        default=None,
        description="Python callable ('module:function') that elaborates this "
                    "task type at graph-build time, replacing the default node "
                    "interior. Signature: elaborate(ctxt, task, name) -> TaskNode. "
                    "Bound along the 'uses' chain (nearest declaration wins).")
    cli : Union[CliDef, None] = dc.Field(
        default=None,
        description="Command-line arguments this task accepts when run with "
                    "'dfm run'. Bound along the 'uses' chain (nearest "
                    "declaration wins, whole-block replacement).")
    summary : Union[str, SummaryDef, None] = dc.Field(
        default=None,
        description="End-of-run summary for this task when it is the task being "
                    "run. Either a Python callable ('module:function') receiving "
                    "a summary context and returning a renderable/str/None, or "
                    "{builtin: task-summary}. Bound along the 'uses' chain "
                    "(nearest declaration wins, whole-value replacement).")
    strategy : StrategyDef = dc.Field(
        default=None)
    control : Union[ControlDef, None] = dc.Field(
        default=None,
        description="Runtime control flow definition (mutually exclusive with strategy)")
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
    let: Dict[str,Union[str,int,bool,float,list,dict]] = dc.Field(
        default_factory=dict,
        alias="let",
        description="(DEPRECATED — use 'set') Scoped variables provided to this task's "
                    "subtree, read via resolve(). Does not set this task's own "
                    "parameters (see 'with').")
    set_defs: List[Any] = dc.Field(
        default_factory=list,
        alias="set",
        description="Scoped overrides applied to this task's subtree: a list whose "
                    "items are either assignment maps ({name: value}) that rebind "
                    "scoped variables read via ${{ pkg.var }}, or scope items "
                    "({uses?, path?, set: [...]}) that narrow/force by matcher. "
                    "Outer overrides inner; CLI (-D) is the ceiling.")
    rundir : RundirE = dc.Field(
        default=RundirE.Unique,
        description="Specifies handling of this tasks's run directory")
    passthrough: Union[PassthroughE, List[Any], None] = dc.Field(
        default=None,
        description="Specifies whether this task should pass its inputs to its output")
    consumes : Union[ConsumesE, List[Any], None] = dc.Field(
        default=None,
        description="Specifies matching patterns for parameter sets that this task consumes")
    produces : Union[List[Dict[str, Any]], None] = dc.Field(
        default=None,
        description="Specifies matching patterns for datasets that this task produces")
    uptodate : Union[bool, str, None] = dc.Field(
        default=None,
        description="Up-to-date check: false=always run, string=Python method, None=use default check")
    cache : Union[CacheDef, bool, None] = dc.Field(
        default=None,
        description="Cache configuration. True=enabled with defaults, False=disabled, CacheDef=custom config")
    tags : List[Union[str, Dict[str, Any]]] = dc.Field(
        default_factory=list,
        description="Tags as type references with optional parameter overrides")
    max_failures : int = dc.Field(
        default=-1,
        description="Max direct-subtask failures before independent subtasks are skipped. "
                    "-1 or 0 = run all; 1 = stop on first; N > 1 = stop after N.")
    on_error : Union[str, None] = dc.Field(
        default=None,
        description="Python callable (module:function) invoked as the compound's run hook "
                    "when all direct subtasks complete.")
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

        # 'provide' is a deprecated alias of 'set'.
        if 'provide' in data:
            if 'set' in data and data['set']:
                raise ValueError("Task cannot specify both 'set' and its deprecated "
                                 "alias 'provide'")
            data['set'] = data.pop('provide')
        
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
    
    @model_validator(mode='after')
    def validate_control_strategy_exclusion(self):
        """Ensure control and strategy are mutually exclusive"""
        if self.control is not None and self.strategy is not None:
            raise ValueError("Task cannot have both 'control' and 'strategy' fields. They are mutually exclusive.")
        if self.abstract and self.override is not None:
            raise ValueError("Task cannot have both 'abstract' and 'override' fields.")
        return self

    @model_validator(mode='after')
    def validate_set_defs(self):
        """Validate the shape of the `set:` scoped-override list."""
        if self.set_defs:
            _validate_set_list(self.set_defs, "set")
        return self

TaskDef.model_rebuild()
