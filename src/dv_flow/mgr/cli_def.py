#****************************************************************************
#* cli_def.py
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
#****************************************************************************
"""Schema for a task's `cli:` block -- its first-class command-line arguments.

Every field except `name` defaults from the parameter the argument targets, so
the common case is a one-liner:

    cli:
      args:
      - name: seed
"""

from typing import Any, List, Union

from pydantic import BaseModel, ConfigDict
import pydantic.dataclasses as dc


class CliArgDef(BaseModel):
    """One command-line argument of a task."""
    model_config = ConfigDict(extra='forbid')

    name : str = dc.Field(
        description="Long-option name, without the leading '--' (e.g. 'seed' -> --seed)")
    param : Union[str, None] = dc.Field(
        default=None,
        description="Task parameter this argument sets. Defaults to 'name'.")
    short : Union[str, None] = dc.Field(
        default=None,
        description="Single-character short option, without the leading '-'")
    help : Union[str, None] = dc.Field(
        default=None,
        description="Help text. Defaults to the parameter's desc/doc.")
    type : Union[str, None] = dc.Field(
        default=None,
        description="Argument type ('str', 'int', 'bool', 'list'). Defaults to "
                    "the parameter's declared type.")
    default : Any = dc.Field(
        default=None,
        description="Default value. Defaults to the parameter's value.")
    choices : Union[List[Any], None] = dc.Field(
        default=None,
        description="Restrict the argument to these values")
    action : Union[str, None] = dc.Field(
        default=None,
        description="argparse action ('store_true', 'append', 'count'). "
                    "Defaults from the parameter's type.")


class CliDef(BaseModel):
    """The `cli:` block: a task's command-line interface."""
    model_config = ConfigDict(extra='forbid')

    args : List[CliArgDef] = dc.Field(
        default_factory=list,
        description="Command-line arguments this task accepts under 'dfm run'")
