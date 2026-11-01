#****************************************************************************
#* roles.py -- artifact roles
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
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
"""The artifact role vocabulary, and a guess at a role from a FileSet's
``filetype`` for FileSets that don't say (dfm uses it when it synthesizes a
``std.TaskResult`` from a task's output)."""
import re

from .convert import attr_map, norm_role

ROLES = ("log", "report", "waves", "cov", "netlist", "checkpoint", "image",
         "data", "profile", "other")

# (pattern over filetype, role), first match wins. Case-insensitive.
_GUESS = [
    (r"log$", "log"),
    (r"cov(db|data)?$|coverage", "cov"),
    (r"trace$|waves?$|fst$|vcd$|fsdb$|cex$", "waves"),
    (r"report$|rpt$|summary$|html$", "report"),
    (r"netlist$", "netlist"),
    (r"checkpoint$|dcp$|odb$", "checkpoint"),
    (r"stats$|json$|data$", "data"),
    (r"prof", "profile"),
    (r"img$|image$|elf$|hex$|bin$|bitstream$", "image"),
]
_GUESS = [(re.compile(p, re.IGNORECASE), r) for p, r in _GUESS]


def guess_role(filetype: str) -> str:
    for pat, role in _GUESS:
        if filetype and pat.search(filetype):
            return role
    return "other"


def role_of(fs) -> str:
    """The FileSet's ``role=`` attribute (legacy names mapped), else a guess
    from its filetype."""
    attrs = attr_map(getattr(fs, "attributes", None) if not isinstance(fs, dict)
                     else fs.get("attributes"))
    if attrs.get("role"):
        return norm_role(attrs["role"])
    ft = getattr(fs, "filetype", None) if not isinstance(fs, dict) else fs.get("filetype")
    return guess_role(ft or "")
