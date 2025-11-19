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
import os
import logging
import sys
from typing import Callable, ClassVar, Dict, List, Optional, Tuple
from .exec_callable import ExecCallable
from .marker_listener import MarkerListener
from .package import Package
from .package_loader_p import PackageLoaderP
from .package_provider import PackageProvider
from .package_provider_yaml import PackageProviderYaml
from .package_provider import Package
from .pytask_callable import PytaskCallable
from .shell_callable import ShellCallable

class ExtRgy(PackageProvider):
    _inst : ClassVar = None
    _log : ClassVar[logging.Logger] = logging.getLogger("ExtRgy")

    def __init__(self):
        self._pkgpath = []
        self._pkg_m : Dict[str, str] = {}
        self._shell_m : Dict[str, Callable] = {}
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
        
    def findShell(self, name) -> Optional[Callable]:
        if name in self._shell_m.keys():
            return self._shell_m[name]
        return None
        
    def getPackageNames(self, loader : PackageLoaderP) -> List[str]:
        return list(self._pkg_m.keys())

    def getPackage(self, name : str, loader : PackageLoaderP) -> Package:
        if name not in self._pkg_m.keys():
            raise Exception("Package %s does not exist" % name)
        return self._pkg_m[name].getPackage(name, loader)
    
    def findPackage(self, name : str, loader : PackageLoaderP) -> Optional[Package]:
        if name in self._pkg_m.keys():
            return self._pkg_m[name].findPackage(name, loader)
        return None
        
    def findPackagePath(self, name) -> str:
        ret = None
        self._log.debug("--> findPackagePath(%s) (%s)" % (
            name, ",".join(self._pkg_m.keys())))
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
        self._pkg_m["std"] = PackageProviderYaml(
            path=os.path.join(os.path.dirname(__file__), "std/flow.dv"))

        # Register built-in shells
        self._shell_m["shell"] = ShellCallable
        self._shell_m["bash"] = ShellCallable
        self._shell_m["csh"] = ShellCallable
        self._shell_m["tcsh"] = ShellCallable
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

                if hasattr(mod, "dvfm_packages") or hasattr(mod, "dfm_packages"):
                    if hasattr(mod, "dvfm_packages"):
                        pkg_m = mod.dvfm_packages()
                    else:
                        pkg_m = mod.dfm_packages()
                    
                    for name,path in pkg_m.items():
                        self._log.debug("Registering package %s: %s" % (name, path))
                        if name in self._pkg_m.keys() and self._pkg_m[name][0] != path:
                            self._log.debug("Package %s already registered using path %s. Conflicting path: %s" % (
                                name, self._pkg_m[name][0], path))
                        else:
                            self._pkg_m[name] = PackageProviderYaml(path=path)
                if hasattr(mod, "dvfm_shells") or hasattr(mod, "dfm_shells"):
                    if hasattr(mod, "dvfm_shells"):
                        shell_m = mod.dvfm_shells()
                    else:
                        shell_m = mod.dfm_shells()

                    for name, shell in shell_m.items():
                        self._log.debug("Registering shell %s" % name)
                        if name in self._shell_m.keys():
                            self._log.debug("Shell %s already registered" % name)
                        else:
                            self._shell_m[name] = shell
            except Exception as e:
                self._log.critical("Error loading plugin %s: %s" % (p.name, str(e)))
                raise e
            
        self._log.debug("Registered packages: %s" % str(",".join(self._pkg_m.keys())))

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
