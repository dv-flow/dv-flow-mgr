import dataclasses as dc
import logging
from typing import Any, ClassVar, Dict, List, Optional
from .loader_scope import LoaderScope
from .package import Package
from .package_provider import PackageProvider
from .task import Task
from .type import Type
from .symbol_scope import SymbolScope

@dc.dataclass(kw_only=True)
class PackageScope(SymbolScope):
    pkg : Package
    loader : Optional[LoaderScope] = None
    _scope_s : List[SymbolScope] = dc.field(default_factory=list)
    _log : ClassVar = logging.getLogger("PackageScope")

    def add(self, task, name):
        if len(self._scope_s):
            self._scope_s[-1].add(task, name)
        else:
            super().add(task, name)

    def addType(self, type, name):
        if len(self._scope_s):
            self._scope_s[-1].addType(type, name)
        else:
            super().addType(type, name)
        
    def push_scope(self, scope):
        self._scope_s.append(scope)

    def pop_scope(self):
        self._scope_s.pop()

    def findTask(self, name) -> Task:
        self._log.debug("--> %s::findTask %s" % (self.pkg.name, name))
        ret = None
        for i in range(len(self._scope_s)-1, -1, -1):
            scope = self._scope_s[i]
            ret = scope.findTask(name)
            if ret is not None:
                break

        if ret is None:
            ret = super().findTask(name)

        if ret is None and name in self.pkg.task_m.keys():
            ret = self.pkg.task_m[name]

        if ret is None:
            for pkg in self.pkg.pkg_m.values():
                self._log.debug("Searching pkg %s for %s" % (pkg.name, name))
                if name in pkg.task_m.keys():
                    ret = pkg.task_m[name]
                    break

        if ret is None:
            self._log.debug("Searching loader for %s" % name)
            ret = self.loader.findTask(name)

        self._log.debug("<-- %s::findTask %s (%s)" % (self.pkg.name, name, ("found" if ret is not None else "not found")))
        return ret

    def findType(self, name) -> Type:
        self._log.debug("--> %s::findType %s" % (self.pkg.name, name))
        ret = None
        for i in range(len(self._scope_s)-1, -1, -1):
            scope = self._scope_s[i]
            ret = scope.findType(name)
            if ret is not None:
                break

        if ret is None:
            ret = super().findType(name)

        if ret is None and name in self.pkg.type_m.keys():
            ret = self.pkg.type_m[name]

        if ret is None:
            for pkg in self.pkg.pkg_m.values():
                self._log.debug("Searching pkg %s for %s" % (pkg.name, name))
                if name in pkg.type_m.keys():
                    ret = pkg.type_m[name]
                    break

        if ret is None:
            self._log.debug("Searching loader for %s" % name)
            ret = self.loader.findType(name)

        self._log.debug("<-- %s::findType %s (%s)" % (self.pkg.name, name, ("found" if ret is not None else "not found")))
        return ret
    
    def resolve_variable(self, name):
        self._log.debug("--> %s::resolve_variable %s" % (self.pkg.name, name))
        ret = None
        if name in self.pkg.paramT.model_fields.keys():
            ret = self.pkg.paramT.model_fields[name].default
        self._log.debug("<-- %s::resolve_variable %s -> %s" % (self.pkg.name, name, ret))
        return ret

    def getScopeFullname(self, leaf=None) -> str:
        path = self.name
        if len(self._scope_s):
            path +=  "."
            path += ".".join([s.name for s in self._scope_s])

        if leaf is not None:
            path += "." + leaf
        return path