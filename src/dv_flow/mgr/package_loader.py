import os
import dataclasses as dc
import difflib
import logging
import pydantic
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple, Union, TYPE_CHECKING
from .loader_scope import LoaderScope
from .marker_listener import MarkerListener
from .name_resolution import NameResolutionContext
from .package import Package
from .package_def import PackageDef
from .package_loader_p import PackageLoaderP
from .package_provider import PackageProvider
from .package_scope import PackageScope
from .param_ref_eval import ParamRefEval
from .ext_rgy import ExtRgy
from .srcinfo import SrcInfo
from .symbol_scope import SymbolScope
from .task import Task, Strategy, StrategyGenerate
from .task_def import TaskDef, PassthroughE, ConsumesE, RundirE
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
from .type import Type

class EmptyParams(pydantic.BaseModel):
    pass

@dc.dataclass
class PackageLoader(PackageLoaderP):
    pkg_rgy : Optional[ExtRgy] = dc.field(default=None)
    marker_listeners : List[Callable] = dc.field(default_factory=list)
    env : Optional[Dict[str, str]] = dc.field(default=None)
    param_overrides : Dict[str, Any] = dc.field(default_factory=dict)
    package_maps : List[str] = dc.field(default_factory=list)
    _log : ClassVar = logging.getLogger("PackageLoader")
    _file_s : List[str] = dc.field(default_factory=list)
    _pkg_m : Dict[str, Package] = dc.field(default_factory=dict)
    # Secondary cache keyed by normalized absolute path, so a package resolved
    # once (by name or by path) is not reparsed when reached the other way.
    _pkg_path_m : Dict[str, Package] = dc.field(default_factory=dict)
    _pkg_s : List[PackageScope] = dc.field(default_factory=list)
    _eval : ParamRefEval = dc.field(default_factory=ParamRefEval)
    _feeds_map : Dict[str, List["Task"]] = dc.field(default_factory=dict)
#    _eval_ctxt : NameResolutionContext = dc.field(default_factory=NameResolutionContext)
    _loader_scope : Optional[LoaderScope] = None
    _pkg_providers : List[PackageProvider] = dc.field(default_factory=list)
    _local_provider : Optional["_LocalBindingProvider"] = None

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = ExtRgy.inst()
        self._pkg_providers.append(self.pkg_rgy)

        if self.env is None:
            self.env = os.environ.copy()

        self._eval.set("env", self.env)
        # Preserve rundir for expansion during task execution
        self._eval.set("rundir", "${{ rundir }}")
        # Preserve runtime-only variables for Agent task
        self._eval.set("inputs", "${{ inputs }}")
        self._eval.set("name", "${{ name }}")
        self._eval.set("result_file", "${{ result_file }}")

        self._eval.set_name_resolution(self)

        self._loader_scope = LoaderScope(name=None, loader=self)
        # Seed loader-scope overrides from CLI parameter overrides
        self._loader_scope.override_m = dict(self.param_overrides) if self.param_overrides is not None else {}

        # Register CLI-supplied package maps (ahead of ExtRgy), then env maps.
        # Flow-file maps are registered later (front) during parse and so outrank these.
        for p in self.package_maps:
            if p:
                self.add_package_map(p)
        env_maps = self.env.get("DV_FLOW_PACKAGE_MAP", "")
        for p in env_maps.split(os.pathsep):
            if p:
                self.add_package_map(p)

    def load(self, root, config: Optional[str]=None) -> Package:
        self._log.debug("--> load %s (config=%s)" % (root, config))
        self.config_name = config
        root = os.path.normpath(root)
        self._eval.set("root", root)
        self._eval.set("rootdir", os.path.dirname(root))
        self._eval.set("srcdir", os.path.dirname(root))
        if root.endswith(".toml"):
            from .package_provider_toml import PackageProviderToml
            provider = PackageProviderToml(path=root)
        else:
            from .package_provider_yaml import PackageProviderYaml
            provider = PackageProviderYaml(path=root)
        ret = provider.getPackage(
            provider.getPackageNames(self)[0],
            self)
        self._log.debug("<-- load %s" % root)
        return ret
    
    def load_rgy(self, name) -> Package:
        self._log.debug("--> load_rgy %s" % name)
        pkg = Package(name="anonymous")
        pkg.pkg_def = PackageDef(name="anonymous")
        pkg.paramT = EmptyParams

        name = name if isinstance(name, list) else [name]

        for nn in name:
            pp_n : Package = self.getPackage(nn)
            pkg.pkg_m[pp_n.name] = pp_n
        self._log.debug("<-- load_rgy %s" % name)
        return pkg
    
    def getPackageNames(self):
        names = []
        for p in self._pkg_providers:
            for n in p.getPackageNames(self):
                if n not in names:
                    names.append(n)
        return names

    def getPackage(self, name) -> Package:
        pkg = self.findPackage(name)

        if not pkg:
            raise Exception("Failed to find package %s" % name)
        return pkg
    
    def findPackage(self, name) -> Optional[Package]:
        self._log.debug("--> findPackage %s" % name)
        pkg = None

        if name in self._pkg_m.keys():
            pkg = self._pkg_m[name]
        else:
            for p in self._pkg_providers:
                pkg = p.findPackage(name, self)
                if pkg:
                    self._cache_pkg(pkg, name)
                    break

        self._log.debug("<-- findPackage %s" % (
            (pkg.name if pkg is not None else "None"),))

        return pkg

    def canResolve(self, name) -> bool:
        """Cheaply test whether *name* is resolvable by some provider, without
        parsing the package. Used to report unresolved imports at load time
        while still deferring the actual parse (lazy imports)."""
        if name in self._pkg_m.keys():
            return True
        for p in self._pkg_providers:
            has = getattr(p, "hasPackage", None)
            if has is not None:
                try:
                    if has(name, self):
                        return True
                except TypeError:
                    # ExtRgy.hasPackage(name, search_path=True) has a different
                    # signature; fall back to the single-arg form.
                    if has(name):
                        return True
        return False

    def _cache_pkg(self, pkg : Package, name=None):
        """Record a resolved package in both the name- and path-keyed caches.

        Keying by normalized absolute path lets a package reachable both by
        map-name and by a file-path import be parsed once (design P0)."""
        if name is not None:
            self._pkg_m[name] = pkg
        if pkg is not None and pkg.name is not None:
            self._pkg_m.setdefault(pkg.name, pkg)
        if pkg is not None and pkg.srcinfo is not None and pkg.srcinfo.file is not None:
            self._pkg_path_m[os.path.normpath(pkg.srcinfo.file)] = pkg

    def findPackageByPath(self, path) -> Optional[Package]:
        """Return an already-resolved package for *path*, if one is cached."""
        return self._pkg_path_m.get(os.path.normpath(path))

    def register_local_package(self, name : str, abs_path : str) -> None:
        """Bind a package *name* to an explicit flow file (from an import's
        ``from:``). The binding is served by a provider at the front of the
        list, so it outranks maps and the registry."""
        from .package_provider_yaml import PackageProviderYaml
        if self._local_provider is None:
            self._local_provider = _LocalBindingProvider()
            self._pkg_providers.insert(0, self._local_provider)
        self._local_provider.bindings[name] = os.path.normpath(os.path.abspath(abs_path))

    def add_package_map(self, path : str, front : bool=False) -> None:
        """Register a package-map file as a provider.

        Precedence is list order. ``front=True`` inserts at the head (used for
        a project's own flow-file map, which must outrank CLI/env maps and the
        registry); otherwise the map is inserted just before ``ExtRgy`` (used
        for CLI/env maps, which outrank only the registry)."""
        from .package_map_provider import PackageMapProvider
        path = os.path.normpath(os.path.abspath(path))

        # Dedupe: skip if a map for this path is already registered
        for p in self._pkg_providers:
            if isinstance(p, PackageMapProvider) and \
                    os.path.normpath(os.path.abspath(p.path)) == path:
                return

        provider = PackageMapProvider(path=path)
        if front:
            self._pkg_providers.insert(0, provider)
        else:
            # Insert ahead of the registry (ExtRgy), which is appended last
            idx = self._pkg_providers.index(self.pkg_rgy) \
                if self.pkg_rgy in self._pkg_providers else len(self._pkg_providers)
            self._pkg_providers.insert(idx, provider)

    def _error(self, msg, elem):
        pass

    def _getLoc(self, elem):
        pass

    def findType(self, name):
        if len(self._pkg_s):
            return self._pkg_s[-1].findType(name)
        else:
            return self._loader_scope.findType(name)

    def findTask(self, name):
        ret = None
        if len(self._pkg_s):
            ret = self._pkg_s[-1].findTask(name)
        else:
            ret = self._loader_scope.findTask(name)
        return ret
        
    def findTaskOrType(self, name):
        self._log.debug("--> _findTaskOrType %s" % name)
        uses = self._findTask(name)

        if uses is None:
            uses = self._findType(name)
            if uses is not None and uses.typedef:
                self._elabType(uses)
                pass
        elif uses.taskdef:
            self._elabTask(uses)

        self._log.debug("<-- _findTaskOrType %s (%s)" % (name, ("found" if uses is not None else "not found")))
        return uses
    
    def pushPath(self, path):
        if path in self._file_s:
            raise Exception("Recursive file processing on %s (%s)" % (
                path,
                ", ".join(self._file_s)))
        self._file_s.append(path)

    def pathStack(self) -> List[str]:
        return self._file_s

    def popPath(self):
        self._file_s.pop()

    def rootDir(self) -> str:
        return self._file_s[0]

    def evalExpr(self, expr : str) -> str:
        if "${{" in expr:
            expr = self._eval.eval(expr)
        return expr

    def resolve_variable(self, name):
        self._log.debug("--> resolve_variable %s" % name)
        ret = None
        # Try qualified package parameter first (e.g. foo.DEBUG)
        last_dot = name.rfind('.')
        if last_dot != -1:
            pkg_name = name[:last_dot]
            param_name = name[last_dot+1:]
            pkg = self.findPackage(pkg_name)
            if pkg is not None:
                # Prefer attribute access; fall back to model_fields default
                if hasattr(pkg.paramT, param_name):
                    ret = getattr(pkg.paramT, param_name)
                elif param_name in pkg.paramT.model_fields.keys():
                    ret = pkg.paramT.model_fields[param_name].default
        
        if ret is None:
            if len(self._pkg_s):
                ret = self._pkg_s[-1].resolve_variable(name)
            else:
                ret = self._loader_scope.resolve_variable(name)

        self._log.debug("<-- resolve_variable %s -> %s" % (name, str(ret)))
        return ret
    
    def getSimilarNamesError(self, name, only_tasks=False):
        tasks = set()
        all = set()

        for pkg in self._pkg_m.values():
            for t in pkg.task_m.keys():
                tasks.add(t)
                all.add(t)
            for t in pkg.type_m.keys():
                all.add(t)

        similar = difflib.get_close_matches(
            name, 
            tasks if only_tasks else all)
        
        if len(similar) == 0 and len(self._pkg_s):
            similar = difflib.get_close_matches(
                "%s.%s" % (self._pkg_s[-1].pkg.name, name),
                tasks if only_tasks else all,
                cutoff=0.8)
        # Fallback: try qualifying with any loaded package names
        if len(similar) == 0 and len(self._pkg_m):
            for pkg in self._pkg_m.values():
                qname = f"{pkg.name}.{name}"
                similar = difflib.get_close_matches(
                    qname,
                    tasks if only_tasks else all,
                    cutoff=0.8)
                if len(similar):
                    break
        
        if len(similar) == 0:
            return ""
        else:
            return " Did you mean '%s'?" % ", ".join(similar)


    
    def error(self, msg, loc : SrcInfo =None):
        if loc is not None:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error,
                                loc=TaskMarkerLoc(path=loc.file, line=loc.lineno, pos=loc.linepos))
        else:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error)
        self.marker(marker)

    def marker(self, marker):
        for l in self.marker_listeners:
            l(marker)

    def pushEvalScope(self, vars : Dict[str,object], inherit=True):
        if not hasattr(self, "_eval_scope_s"):
            self._eval_scope_s = []
        # Save current variables snapshot
        self._eval_scope_s.append(self._eval.expr_eval.variables.copy())
        if not inherit:
            self._eval.expr_eval.variables = {}
        # Apply new vars
        for k, v in vars.items():
            self._eval.set(k, v)

    def popEvalScope(self):
        if hasattr(self, "_eval_scope_s") and len(self._eval_scope_s):
            prev = self._eval_scope_s.pop()
            self._eval.expr_eval.variables = prev

    def feedsMap(self) -> Dict[str, List[Task]]:
        return self._feeds_map

    def addFeed(self, task : Task, fed_name : str):
        if fed_name not in self._feeds_map.keys():
            self._feeds_map[fed_name] = []
        self._feeds_map[fed_name].append(task)


@dc.dataclass
class _LocalBindingProvider(PackageProvider):
    """Provider for explicit ``{name: from}`` import pins. Resolves a bound
    name to its pinned flow file on demand."""
    bindings : Dict[str, str] = dc.field(default_factory=dict)
    _provider_m : Dict[str, Any] = dc.field(default_factory=dict)

    def hasPackage(self, name, loader=None) -> bool:
        return name in self.bindings

    def getPackageNames(self, loader) -> List[str]:
        return list(self.bindings.keys())

    def getPackage(self, name, loader) -> Optional[Package]:
        return self.findPackage(name, loader)

    def findPackage(self, name, loader) -> Optional[Package]:
        if name not in self.bindings:
            return None
        from .package_provider_yaml import PackageProviderYaml
        if name not in self._provider_m:
            self._provider_m[name] = PackageProviderYaml(path=self.bindings[name])
        return self._provider_m[name].findPackage(name, loader)

