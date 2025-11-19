#****************************************************************************
#* util.py
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
import difflib
import os
import yaml
from ..package_loader import PackageLoader
from ..task_data import TaskMarker, TaskMarkerLoc, SeverityE

def parse_parameter_overrides(def_list):
    """Parses ['name=value', ...] into a dict of parameter overrides."""
    ov = {}
    if not def_list:
        return ov
    for item in def_list:
        # Accept raw 'name=value' values (regardless of how '-D' was passed)
        s = item.strip()
        if s.startswith("-D"):
            s = s[2:]
        if "=" not in s:
            continue
        name, value = s.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            ov[name] = value
    return ov

def loadProjPkgDef(path, listener=None, parameter_overrides=None):
    """Locates the project's flow spec and returns the PackageDef"""

    dir = path
    ret = None
    loader = None
    found = False
    while dir != "/" and dir != "" and os.path.isdir(dir):
        for name in ("flow.dv", "flow.yaml", "flow.yml", "flow.toml"):
            fpath = os.path.join(dir, name)
            if os.path.exists(fpath):
                try:
                    listeners = [listener] if listener is not None else []
                    loader = PackageLoader(
                        marker_listeners=listeners,
                        param_overrides=(parameter_overrides or {}))
                    ret = loader.load(fpath)
                    found = True
                    break
                except Exception:
                    # Try next candidate up the tree
                    pass
        if found:
            break
        dir = os.path.dirname(dir)
    
    if not found:
        if listener:
            listener(TaskMarker(
                msg="Failed to find a 'flow.dv/flow.yaml/flow.toml' file that defines a package in %s or its parent directories" % path,
                severity=SeverityE.Error))
    
    return loader, ret
