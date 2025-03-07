#****************************************************************************
#* pkg_rgy.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
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
import os
import logging
import sys
from typing import Dict, Tuple
from .package_def import PackageDef

class PkgRgy(object):
    _inst = None

    def __init__(self):
        self._pkgpath = []
        self._pkg_m : Dict[str, Tuple[str,PackageDef]] = {}
        self._log = logging.getLogger(type(self).__name__)

    def hasPackage(self, name, search_path=True):
        if name in self._pkg_m.keys():
            return True
        elif search_path and self._findOnPath(name) is not None:
            return True
        else:
            return False
    
    def getPackage(self, name):
        self._log.debug("--> getPackage(%s)" % name)
        if name in self._pkg_m.keys():
            if self._pkg_m[name][1] is None:
                pkg_def = PackageDef.load(self._pkg_m[name][0])
                # Load the package
                self._pkg_m[name] = (
                    self._pkg_m[name][0],
                    pkg_def
                )
            ret = self._pkg_m[name][1]
        else:
            ret = self._findOnPath(name)
        self._log.debug("<-- getPackage(%s)" % name)
        return ret
        
    def _findOnPath(self, name):
        name_s = name.split('.')
        name_dir = "/".join(name_s)
        if len(name_s) > 1:
            name_pref = "/".join(name_s[:-1])
        else:
            name_pref = None

        pkg = None

        for path in self._pkgpath:
            if os.path.isfile(os.path.join(path, name_dir, "flow.dv")):
                pkg = PackageDef.load(os.path.join(path, name_dir, "flow.dv"))
            elif name_pref is not None and os.path.isfile(os.path.join(path, name_pref, name_s[-1] + ".dv")):
                pkg = PackageDef.load(os.path.join(path, name_pref, name_s[-1] + ".dv"))
            elif os.path.isfile(os.path.join(path, name + ".dv")):
                pkg = PackageDef.load(os.path.join(path, name + ".dv"))

            if pkg is not None:
                self._pkg_m[name] = (pkg.name, pkg)
                break

        return pkg

    def registerPackage(self, pkg_def):
        self._log.debug("--> registerPackage %s" % pkg_def.name)
        if pkg_def.name in self._pkg_m.keys():
            raise Exception("Duplicate package %s" % pkg_def.name)
        self._pkg_m[pkg_def.name] = (pkg_def.basedir, pkg_def)
        self._log.debug("<-- registerPackage %s" % pkg_def.name)

    def _discover_plugins(self):
        # Register built-in package
        self._pkg_m["std"] = (os.path.join(os.path.dirname(__file__), "std/flow.dv"), None)

        if "DV_FLOW_PATH" in os.environ.keys() and os.environ["DV_FLOW_PATH"] != "":
            paths = os.environ["DV_FLOW_PATH"].split(':')
            self._pkgpath.extend(paths)

        if sys.version_info < (3,10):
            from importlib_metadata import entry_points
        else:
            from importlib.metadata import entry_points

        discovered_plugins = entry_points(group='dv_flow.mgr')
        for p in discovered_plugins:
            try:
                mod = p.load()

                if hasattr(mod, "dvfm_packages"):
                    pkg_m = mod.dvfm_packages()
                    
                    for name,path in pkg_m.items():
                        if name in self._pkg_m.keys():
                            raise Exception("Package %s already registered using path %s. Conflicting path: %s" % (
                                name, self._pkg_m[name][0], path))
                        self._pkg_m[name] = (path, None)
            except Exception as e:
                self._log.critical("Error loading plugin %s: %s" % (p.name, str(e)))
                raise e

        # self._pkgs = {}
        # for pkg in self._load_pkg_list():
        #     self._pkgs[pkg.name] = pkg

    def copy(self):
        ret = PkgRgy()
        ret._pkgpath = self._pkgpath.copy()
        ret._pkg_m = self._pkg_m.copy()
        return ret

    @classmethod
    def inst(cls):
        if cls._inst is None:
            cls._inst = cls()
            cls._inst._discover_plugins()
        return cls._inst
