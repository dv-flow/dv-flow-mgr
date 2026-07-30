#****************************************************************************
#* param_def.py
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
import logging as _logging
from typing import Annotated, Any, Dict, List, Union
from pydantic import (BaseModel, ConfigDict, Field, WithJsonSchema,
                      field_validator, model_validator)

class ValueDef(BaseModel):
    """One member of a parameter's value set."""
    value : Any = Field(
        description="The accepted value")
    desc : str = Field(
        default=None,
        description="What selecting this value means. Shown in help.")

class ValueSet(BaseModel):
    """The set of values a parameter accepts.

    Authored either as a plain list (closed set) or as `{of: [...], open: true}`.
    An *open* set is a set of **known** values: it drives help and completion,
    but an unlisted value warns instead of failing -- which is what a downstream
    site adding, say, a simulator backend to a library's list needs.
    """
    of : List[ValueDef] = Field(
        default_factory=list,
        description="The accepted values")
    open : bool = Field(
        default=False,
        description="When true, an unlisted value warns rather than errors")

    def values(self) -> List[Any]:
        return [v.value for v in self.of]

    def describe(self) -> str:
        """'quiet, normal, full' -- the value list as it appears in messages."""
        text = ", ".join(str(v.value) for v in self.of)
        return (text + ", ...") if self.open else text

class ListType(BaseModel):
    item : Union[str, Any]

class MapType(BaseModel):
    key : Union[str, Any]
    val : Union[str, Any]

class ComplexType(BaseModel):
    list : Union[ListType, None] = None
    map : Union[MapType, None] = None

class CliOpt(BaseModel):
    """How a parameter appears on the command line.

    Authored as `cli: true` (the common case -- the parameter's own name becomes
    the long option) or as a map when the flag needs a short option, a different
    name, or must stay out of help.
    """
    model_config = ConfigDict(extra='forbid')

    name : Union[str, None] = Field(
        default=None,
        description="Long-option name, without the leading '--'. Defaults to "
                    "the parameter's own name ('build' -> --build).")
    short : Union[str, None] = Field(
        default=None,
        description="Single-character short option, without the leading '-'")
    hidden : bool = Field(
        default=False,
        description="Accept the option but omit it from help and completion")

class ParamDef(BaseModel):
    doc : str = Field(
        default=None,
        description="Full documentation for this parameter")
    desc : str = Field(
        default=None,
        description="Short description of this parameter")
    type : Union[str, 'ComplexType'] = Field(
        default=None,
        description="Parameter type (e.g., 'str', 'int', 'bool', 'list', 'map', or a complex type definition)")
    value : Union[Any, None] = Field(
        default=None,
        description="Default value for this parameter")
    append : Union[Any, None] = Field(
        default=None,
        description="Value to append to list-type parameters")
    prepend : Union[Any, None] = Field(
        default=None,
        description="Value to prepend to list-type parameters")
    path_append : Union[Any, None] = Field(
        alias="path-append", 
        default=None,
        description="Path to append to path-type parameters (OS-specific separator)")
    path_prepend : Union[Any, None] = Field(
        alias="path-prepend", 
        default=None,
        description="Path to prepend to path-type parameters (OS-specific separator)")
    # The annotation is the *stored* shape (always a ValueSet -- see the
    # normalizing validator below), but a flow may author either form, so the
    # published JSON schema has to describe both or an editor will flag the
    # short one.
    values : Annotated[Union[ValueSet, None], WithJsonSchema({
        "anyOf": [
            {"type": "array",
             "description": "Closed set: the accepted values, each either a "
                            "bare value or {value: v, desc: ...}"},
            {"type": "object",
             "properties": {
                 "of": {"type": "array"},
                 "open": {"type": "boolean"},
             },
             "required": ["of"],
             "description": "{of: [...], open: true} -- an open set warns on an "
                            "unlisted value instead of failing"},
            {"type": "null"},
        ],
        "default": None,
    })] = Field(
        default=None,
        description="The set of values this parameter accepts. Either a plain "
                    "list ([a, b, c] -- closed) or {of: [...], open: true}. "
                    "List elements may be bare values or {value: v, desc: ...}.")
    # Stored as CliOpt (exposed) | False (explicitly not exposed) | None (no
    # statement -- inherit). The published schema has to describe the authored
    # forms, not the stored one, or an editor flags `cli: true`.
    cli : Annotated[Union[CliOpt, bool, None], WithJsonSchema({
        "anyOf": [
            {"type": "boolean",
             "description": "true exposes the parameter as --<name>; false "
                            "removes a flag inherited via `uses:`"},
            {"type": "object",
             "properties": {
                 "name": {"type": "string"},
                 "short": {"type": "string"},
                 "hidden": {"type": "boolean"},
             },
             "description": "{name, short, hidden} -- rename the flag, add a "
                            "short option, or keep it out of help"},
            {"type": "null"},
        ],
        "default": None,
    })] = Field(
        default=None,
        description="Expose this parameter as a command-line option under "
                    "'dfm run'. `true` uses the parameter's own name "
                    "('build' -> --build); the map form adds a short option, "
                    "renames the flag, or hides it. `false` removes a flag "
                    "inherited from a base task. Type, default, help and "
                    "accepted values all come from this declaration, so there "
                    "is nothing to restate.")
    srcinfo : Union[str, None] = Field(alias="srcinfo", default=None)

    @field_validator('cli', mode='before')
    @classmethod
    def _normalize_cli(cls, v):
        """`cli: true` -> an empty CliOpt; `cli: false` and absence stay
        distinguishable, because they mean opposite things under inheritance:
        absence inherits a base's flag, `false` removes it."""
        if v is True:
            return CliOpt()
        return v

    @field_validator('values', mode='before')
    @classmethod
    def _normalize_values(cls, v):
        """Accept every authoring form and store one shape.

        Normalizing here rather than at each read site is what lets the rest of
        the engine -- validation, help, completion, the JSON schema -- see a
        single `ValueSet` regardless of how terse the declaration was.
        """
        if v is None or isinstance(v, ValueSet):
            return v

        def _entries(seq):
            out = []
            for e in seq:
                if isinstance(e, ValueDef):
                    out.append(e)
                elif isinstance(e, dict) and 'value' in e:
                    out.append(ValueDef(**e))
                else:
                    out.append(ValueDef(value=e))
            return out

        if isinstance(v, (list, tuple)):
            return ValueSet(of=_entries(v))
        if isinstance(v, dict):
            if 'of' not in v:
                raise ValueError(
                    "a 'values' map must have an 'of' key listing the values "
                    "(got keys: %s)" % sorted(v.keys()))
            return ValueSet(of=_entries(v['of']), open=bool(v.get('open', False)))
        raise ValueError(
            "'values' must be a list of values or a {of: [...], open: bool} "
            "map, not %s" % type(v).__name__)

    def value_set(self) -> Union[ValueSet, None]:
        """This declaration's value set, if it declares one."""
        return self.values

    def resolve_value(self, base_value):
        """Apply value/prepend/append/path-prepend/path-append against
        *base_value*.

        When 'value' is set, it replaces base_value as the starting point.
        Then the list ops are layered on top:
            result = path_prepend + prepend + (value or base) + append + path_append

        For list-typed params (the common case: `plusargs`, `incdirs`, ...) the
        path-* ops add elements just like prepend/append. (OS-path-separator
        *string* join for scalar PATH-like params is a documented follow-up in
        docs/proposals/list_manipulation.md; no current flow relies on it.)
        """
        def _as_items(v):
            return v if isinstance(v, list) else [v]

        if self.value is not None:
            result = list(self.value) if isinstance(self.value, list) \
                     else [self.value]
        else:
            result = list(base_value) if isinstance(base_value, list) \
                     else ([base_value] if base_value else [])
        if self.prepend is not None:
            result = _as_items(self.prepend) + result
        if self.append is not None:
            result = result + _as_items(self.append)
        if self.path_prepend is not None:
            result = _as_items(self.path_prepend) + result
        if self.path_append is not None:
            result = result + _as_items(self.path_append)
        # If only value was set (no list op), return as-is (preserve scalars).
        if not self.has_list_op() and self.value is not None:
            return self.value
        return result

    def has_list_op(self) -> bool:
        """True when this ParamDef carries a list op (append/prepend or their
        path-* variants)."""
        return (self.append is not None or self.prepend is not None
                or self.path_append is not None or self.path_prepend is not None)

