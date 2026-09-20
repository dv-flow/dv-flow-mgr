#****************************************************************************
#* hash_provider.py
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
import inspect
import os
from pathlib import Path
from typing import Any, Iterable, List, Optional, Protocol
from .fileset import FileSet


# Filetypes whose `include search path can span filesets. An incdir declared on
# one of these is a property of the COMPILATION, not of the fileset that
# declares it: the UVM library fileset carries `incdirs: ["src"]` so that every
# downstream fileset `include`ing uvm_macros.svh can resolve it. Hashing a
# fileset in isolation therefore has to be handed the incdirs of its siblings.
SEARCH_PATH_FILETYPES = (
    'systemVerilogSource',
    'verilogSource',
    'systemVerilogInclude',
    'verilogInclude',
    'verilogIncDir',
)

_INCLUDE_FILETYPES = ('systemVerilogInclude', 'verilogInclude', 'verilogIncDir')


def resolve_incdirs(fileset, rundir: str) -> List[str]:
    """Absolute incdirs declared by one fileset.

    Relative incdirs resolve against the fileset's BASEDIR -- the same rule the
    simulator-facing consumers use (libhdlsim's _addIncDirs joins basedir), and
    the only rule under which `FileSet(basedir=$UVM_HOME, incdirs=["src"])`
    names a real directory. Resolving them against the rundir instead silently
    yields paths that do not exist, so every include they were meant to satisfy
    goes unresolved and drops out of the hash.
    """
    basedir = getattr(fileset, 'basedir', '') or ''
    base = Path(basedir) if os.path.isabs(basedir) else Path(rundir) / basedir

    ret = []
    incdirs = getattr(fileset, 'incdirs', None) or []
    for incdir in incdirs:
        inc_path = Path(incdir)
        if not inc_path.is_absolute():
            inc_path = base / inc_path
        ret.append(str(inc_path.resolve()))

    # An include-only fileset with no explicit incdirs IS its basedir
    if not incdirs and getattr(fileset, 'filetype', '') in _INCLUDE_FILETYPES:
        if basedir.strip():
            ret.append(str(base.resolve()))

    return ret


def collect_incdirs(items: Iterable[Any], rundir: str) -> List[str]:
    """Union of the incdirs contributed by a task's input filesets.

    This is the search path the compile step will actually see, so it is the
    search path an include scan has to be run against. Order is preserved and
    duplicates dropped.
    """
    ret = []
    seen = set()
    for item in items:
        if getattr(item, 'type', None) != 'std.FileSet':
            continue
        if getattr(item, 'filetype', '') not in SEARCH_PATH_FILETYPES:
            continue
        for incdir in resolve_incdirs(item, rundir):
            if incdir not in seen:
                seen.add(incdir)
                ret.append(incdir)
    return ret


async def compute_hash(provider, fileset, rundir: str,
                       incdirs: Optional[List[str]] = None) -> str:
    """Invoke a hash provider, passing sibling incdirs when it accepts them.

    Providers are pluggable and may be supplied out-of-tree, so the widened
    signature is offered rather than required: one that predates `incdirs` is
    called the old way instead of failing.
    """
    if incdirs and _accepts_incdirs(provider.compute_hash):
        return await provider.compute_hash(fileset, rundir, incdirs=incdirs)
    return await provider.compute_hash(fileset, rundir)


_accepts_incdirs_m = {}


def _accepts_incdirs(fn) -> bool:
    key = (type(fn.__self__).__qualname__ if hasattr(fn, '__self__') else repr(fn))
    if key not in _accepts_incdirs_m:
        try:
            params = inspect.signature(fn).parameters
            _accepts_incdirs_m[key] = (
                'incdirs' in params
                or any(p.kind == p.VAR_KEYWORD for p in params.values()))
        except (TypeError, ValueError):
            _accepts_incdirs_m[key] = False
    return _accepts_incdirs_m[key]


class HashProvider(Protocol):
    """Protocol for hash providers that compute hashes for filesets.
    
    Hash providers are pluggable components that determine how to hash
    different file types. For example, a specialized provider for SystemVerilog
    files might hash not just the source files but also included files.
    """
    
    def supports(self, filetype: str) -> bool:
        """Check if this provider handles the given filetype.
        
        Args:
            filetype: The filetype string (e.g., 'systemVerilogSource', 'cSource')
            
        Returns:
            True if this provider can hash this filetype
        """
        ...
    
    async def compute_hash(self, fileset: FileSet, rundir: str,
                           incdirs: Optional[List[str]] = None) -> str:
        """Compute hash for the given fileset.

        Args:
            fileset: The fileset to hash
            rundir: The run directory (base path for resolving relative paths)
            incdirs: Absolute include directories contributed by the OTHER
                filesets the consuming task receives. A provider that follows
                `include directives must search these too, because the file
                being hashed is compiled against the union of the task's
                incdirs, not against its own fileset's incdirs alone.

        Returns:
            MD5 hash string (hex digest)
        """
        ...
