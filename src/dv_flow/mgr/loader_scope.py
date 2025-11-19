
import dataclasses as dc
import logging
import os
from typing import Any, ClassVar, Dict, List, Optional
from .package import Package
from .package_loader_p import PackageLoaderP
from .package_provider import PackageProvider
from .task import Task
from .type import Type
from .symbol_scope import SymbolScope

@dc.dataclass
class LoaderScope(SymbolScope):
    loader : Optional[PackageLoaderP] = None
    _log : ClassVar = logging.getLogger("LoaderScope")

    def add(self, task, name):
        raise NotImplementedError("LoaderScope.add() not implemented")

    def addType(self, task, name):
        raise NotImplementedError("LoaderScope.addType() not implemented")
    
    def findTask(self, name) -> Task:
        self._log.debug("--> findTask: %s" % name)

        ret = None
        pkg = None

        # Split the name into elements
        name_elems = name.split('.')

        def find_pkg(pkg_name):
            assert self.loader is not None
            pkg : Package = self.loader.findPackage(pkg_name)

            # if pkg_name in self.loader._pkg_m.keys():
            #     pkg = self.loader._pkg_m[pkg_name]
            # else:
            #     self.loader._findPackage(pkg_name)
            #     path = self.loader.pkg_rgy.findPackagePath(pkg_name)
            #     if path is not None:
            #         path = os.path.normpath(path)
            #         pkg = self.loader._loadPackage(path)
            #         self.loader._pkg_m[pkg_name] = pkg
            if pkg is not None:
                self._log.debug("Found pkg %s (%s)" % (pkg_name, str(pkg.task_m.keys())))
            else:
                self._log.debug("Failed to find pkg %s" % pkg_name)
            
            return pkg

        if len(name_elems) > 1:
            for i in range(len(name_elems)-1, -1, -1):
                pkg_name = ".".join(name_elems[:i+1])

                pkg = find_pkg(pkg_name)
                if pkg is not None:
                    break

        if pkg is not None:
            self._log.debug("Found package %s" % pkg.name)
            if name in pkg.task_m.keys():
                self._log.debug("Found task %s" % name)
                ret = pkg.task_m[name]
            else:
                self._log.debug("Didn't find task %s in package %s" % (name, pkg.name))
        else:
            self._log.debug("Did not find a package for %s" % name)

        self._log.debug("<-- findTask: %s (%s)" % (name, ("Found" if ret is not None else "NotFound")))
        
        return ret

    def findType(self, name) -> Type:
        self._log.debug("--> findType: %s" % name)
        ret = None
        pkg = None
        last_dot = name.rfind('.')
        if last_dot != -1:
            pkg_name = name[:last_dot]
            assert self.loader is not None

            pkg = self.loader.findPackage(pkg_name)

            if pkg is not None and name in pkg.type_m.keys():
                ret = pkg.type_m[name]

        self._log.debug("<-- findType: %s (%s)" % (name, str(ret)))

        return ret
