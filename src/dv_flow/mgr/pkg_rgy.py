import os
import sys
from typing import Dict, Tuple
from .package_def import PackageDef

class PkgRgy(object):
    _inst = None

    def __init__(self):
        self._pkgpath = []
        self._pkg_m : Dict[str, Tuple[str,PackageDef]] = {}

    def hasPackage(self, name, search_path=False):
        if name in self._pkg_m.keys():
            return True
        elif search_path:
            for p in self._pkgpath:
                if os.path.exists(os.path.join(p, name)):
                    return True
        else:
            return False
    
    def getPackage(self, name):
        if name in self._pkg_m.keys():
            if self._pkg_m[name][1] is None:
                pkg_def = PackageDef.load(self._pkg_m[name][0])
                # Load the package
                self._pkg_m[name] = (
                    self._pkg_m[name][0],
                    pkg_def
                )
                pass
            return self._pkg_m[name][1]
        else:
            # Go search the package path
            return None

    def registerPackage(self, pkg_def):
        if pkg_def.name in self._pkg_m.keys():
            raise Exception("Duplicate package %s" % pkg_def.name)
        self._pkg_m[pkg_def.name] = pkg_def

    def _discover_plugins(self):
        # Register built-in package
        self._pkg_m["std"] = (os.path.join(os.path.dirname(__file__), "std/flow.dv"), None)

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
                print("Error loading plugin %s: %s" % (p.name, str(e)))
                raise e

        # self._pkgs = {}
        # for pkg in self._load_pkg_list():
        #     self._pkgs[pkg.name] = pkg

    @classmethod
    def inst(cls):
        if cls._inst is None:
            cls._inst = cls()
            cls._inst._discover_plugins()
        return cls._inst
