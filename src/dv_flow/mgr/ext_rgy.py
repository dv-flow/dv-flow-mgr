#****************************************************************************
#* ext_rgy.py
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
import dataclasses as dc
import os
import logging
import sys
from typing import Callable, ClassVar, Dict, Tuple
from .exec_callable import ExecCallable
from .pytask_callable import PytaskCallable
from .shell_callable import ShellCallable

@dc.dataclass
class ExtRgy(object):
    _inst : ClassVar = None

    def __init__(self):
        self._pkgpath = []
        self._pkg_m : Dict[str, str] = {}
        self._shell_m : Dict[str, Callable] = {}
        self._log = logging.getLogger(type(self).__name__)
        self._override_m : Dict[str,str] = {}

    def addOverride(self, key, value):
        self._override_m[key] = value

    def getOverrides(self):
        return self._override_m

    def hasPackage(self, name, search_path=True):
        if name in self._pkg_m.keys():
            return True
        elif search_path and self._findOnPath(name) is not None:
            return True
        else:
            return False
        
    def findShell(self, name) -> Callable:
        if name in self._shell_m.keys():
            return self._shell_m[name]
        
    def findPackagePath(self, name) -> str:
        ret = None
        self._log.debug("--> findPackagePath(%s)" % name)
        if name in self._pkg_m.keys():
            ret = self._pkg_m[name]
        else:
            ret = self._findOnPath(name)
        self._log.debug("<-- findPackagePath(%s)" % name)
        return ret
        
    def _findOnPath(self, name):
        name_s = name.split('.')
        name_dir = "/".join(name_s)
        if len(name_s) > 1:
            name_pref = "/".join(name_s[:-1])
        else:
            name_pref = None

        ret = None

        for path in self._pkgpath:
            if os.path.isfile(os.path.join(path, name_dir, "flow.dv")):
                ret = os.path.join(path, name_dir, "flow.dv")
            elif name_pref is not None and os.path.isfile(os.path.join(path, name_pref, name_s[-1] + ".dv")):
                ret = os.path.join(path, name_pref, name_s[-1] + ".dv")
            elif os.path.isfile(os.path.join(path, name + ".dv")):
                ret = os.path.join(path, name + ".dv")

            if ret is not None:
                self._pkg_m[name] = ret
                break

        return ret

    def _discover_plugins(self):
        self._log.debug("--> discover_plugins")
        # Register built-in package
        self._pkg_m["std"] = os.path.join(os.path.dirname(__file__), "std/flow.dv")

        # Register built-in shells
        self._shell_m["shell"] = ShellCallable
        self._shell_m["pytask"] = ExecCallable


        if "DV_FLOW_PATH" in os.environ.keys() and os.environ["DV_FLOW_PATH"] != "":
            paths = os.environ["DV_FLOW_PATH"].split(':')
            self._pkgpath.extend(paths)

        if sys.version_info < (3,10):
            from importlib_metadata import entry_points
        else:
            from importlib.metadata import entry_points

        discovered_plugins = entry_points(group='dv_flow.mgr')
        self._log.debug("discovered_plugins: %s" % str(discovered_plugins))
        for p in discovered_plugins:
            try:
                mod = p.load()

                if hasattr(mod, "dvfm_packages"):
                    pkg_m = mod.dvfm_packages()
                    
                    for name,path in pkg_m.items():
                        self._log.debug("Registering package %s: %s" % (name, path))
                        if name in self._pkg_m.keys() and self._pkg_m[name][0] != path:
                            self._log.debug("Package %s already registered using path %s. Conflicting path: %s" % (
                                name, self._pkg_m[name][0], path))
                        else:
                            self._pkg_m[name] = path
                if hasattr(mod, "dvfm_shells"):
                    shell_m = mod.dvfm_shells()
                    for name, shell in shell_m.items():
                        self._log.debug("Registering shell %s" % name)
                        if name in self._shell_m.keys():
                            self._log.debug("Shell %s already registered" % name)
                        else:
                            self._shell_m[name] = shell
            except Exception as e:
                self._log.critical("Error loading plugin %s: %s" % (p.name, str(e)))
                raise e

        # self._pkgs = {}
        # for pkg in self._load_pkg_list():
        #     self._pkgs[pkg.name] = pkg
        self._log.debug("<-- discover_plugins")

    def copy(self):
        ret = ExtRgy()
        ret._pkgpath = self._pkgpath.copy()
        ret._pkg_m = self._pkg_m.copy()
        return ret

    @classmethod
    def inst(cls):
        if cls._inst is None:
            cls._inst = cls()
            cls._inst._discover_plugins()
        return cls._inst
