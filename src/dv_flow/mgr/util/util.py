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
import logging
import os
import yaml
from ..package_loader import PackageLoader
from ..task_data import TaskMarker, TaskMarkerLoc, SeverityE

_log = logging.getLogger("util")

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

def loadProjPkgDef(path, listener=None, parameter_overrides=None, config: str | None = None):
    """Locates the project's flow spec and returns the PackageDef"""

    _log.debug("--> loadProjPkgDef %s" % path)

    ret = None
    if os.path.isfile(path):
        dir = os.path.dirname(path)
        rootfile = path
    else:
        dir = path
        rootfile = None

        while dir != "/" and dir != "" and os.path.isdir(dir):
            for name in ("flow.dv", "flow.yaml", "flow.yml", "flow.toml"):
                fpath = os.path.join(dir, name)
                _log.debug("Trying path %s (%s)" % (
                    fpath, ("exists" if os.path.exists(fpath) else "doesn't exist")))
                if os.path.exists(fpath):
                    rootfile = fpath
                    break
            if rootfile is not None:
                break
            else:
                dir = os.path.dirname(dir)

        if rootfile is None:
            _log.debug("Failed to find flow.dv/flow.yaml/flow.toml")
            if listener:
                listener(TaskMarker(
                    msg="Failed to find a 'flow.dv/flow.yaml/flow.toml' file that defines a package in %s or its parent directories" % path,
                    severity=SeverityE.Error))
    loader = None
    ret = None

    if rootfile is not None:
        _log.debug("Loading rootfile: %s" % rootfile)
        try:
            listeners = [listener] if listener is not None else []
            loader = PackageLoader(
                marker_listeners=listeners,
                param_overrides=(parameter_overrides or {}))
            ret = loader.load(rootfile, config=config)
        except Exception:
            print("Fatal Error: while parsing %s" % rootfile)
            raise

    _log.debug("<-- loadProjPkgDef %s" % path)
    
    return loader, ret
