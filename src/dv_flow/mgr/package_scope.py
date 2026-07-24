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

        # Try the package-qualified form. An unqualified reference to a
        # package-level task -- including tasks inherited/aliased from a used
        # package (keyed as "<pkg>.<name>") -- lives in task_m under its
        # fully-qualified name. Resolving this here, before descending into
        # sub-packages, makes the nearest enclosing namespace win: the current
        # package's own (possibly inherited) task shadows a same-named task in
        # a used/imported package.
        if ret is None and '.' not in name:
            qname = "%s.%s" % (self.pkg.name, name)
            if qname in self.pkg.task_m.keys():
                ret = self.pkg.task_m[qname]

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

        # Package-qualified fallback (see findTask): nearest enclosing namespace
        # wins over used/imported packages for an unqualified reference.
        if ret is None and '.' not in name:
            qname = "%s.%s" % (self.pkg.name, name)
            if qname in self.pkg.type_m.keys():
                ret = self.pkg.type_m[qname]

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
        """LOAD-time variable resolver: reads class-level
        `paramT.model_fields[...].default` (a -D override is baked into that
        default at load, so -D is honored) plus subpackage/alias-qualified
        `pkg.var`. There are no materialized param instances yet; the build-time
        counterpart NameResolutionContext.resolve_variable reads instances (for
        expanded/templated values) and owns the authoritative precedence ladder.
        This phase split is intentional -- see that method's docstring."""
        self._log.debug("--> %s::resolve_variable %s" % (self.pkg.name, name))
        ret = None
        # Support qualified lookup: foo.DEBUG
        if '.' in name:
            pkg_name, pname = name.split('.', 1)
            if pkg_name == self.pkg.name:
                if pname in self.pkg.paramT.model_fields.keys():
                    # Model fields hold defaults; actual values may be set on instance
                    ret = self.pkg.paramT.model_fields[pname].default
            else:
                # Check subpackages for qualified reference (resolve aliases)
                real_name = self.pkg.pkg_alias_m.get(pkg_name, pkg_name)
                if real_name in self.pkg.pkg_m.keys():
                    subpkg = self.pkg.pkg_m[real_name]
                    if pname in subpkg.paramT.model_fields.keys():
                        ret = subpkg.paramT.model_fields[pname].default
        else:
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