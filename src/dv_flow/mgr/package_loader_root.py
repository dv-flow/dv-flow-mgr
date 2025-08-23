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
from .package_loader import PackageLoader
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
class PackageLoaderRoot(PackageLoader):
    pkg_rgy : Optional[ExtRgy] = dc.field(default=None)
    marker_listeners : List[Callable] = dc.field(default_factory=list)
    env : Optional[Dict[str, str]] = dc.field(default=None)
    _log : ClassVar = logging.getLogger("PackageLoader")
    _file_s : List[str] = dc.field(default_factory=list)
    _pkg_m : Dict[str, Package] = dc.field(default_factory=dict)
    _pkg_path_m : Dict[str, Package] = dc.field(default_factory=dict)
    _eval : ParamRefEval = dc.field(default_factory=ParamRefEval)
    _feeds_map : Dict[str, List["Task"]] = dc.field(default_factory=dict)
#    _eval_ctxt : NameResolutionContext = dc.field(default_factory=NameResolutionContext)
    _loader_scope : Optional[LoaderScope] = None
    _pkg_providers : List[PackageProvider] = dc.field(default_factory=list)

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = ExtRgy.inst()
        self._pkg_providers.append(self.pkg_rgy)

        if self.env is None:
            self.env = os.environ.copy()

        self._eval.set("env", self.env)
        # Preserve rundir for expansion during task execution
        self._eval.set("rundir", "${{ rundir }}")

        self._eval.set_name_resolution(self)

    def load(self, root) -> Package:
        from .package_provider_yaml import PackageProviderYaml

        self._log.debug("--> load %s" % root)
        root = os.path.normpath(root)
        self._eval.set("root", root)
        self._eval.set("rootdir", os.path.dirname(root))
        provider = PackageProviderYaml(path=root)
        ret = provider.getPackage(
            provider.getPackageNames(self)[0],
            self)
        self._log.debug("<-- load %s" % root)
        return ret
    
    # def load_rgy(self, name) -> Package:
    #     self._log.debug("--> load_rgy %s" % name)
    #     pkg = Package(PackageDef(name="anonymous"))
    #     pkg.paramT = EmptyParams

    #     name = name if isinstance(name, list) else [name]

    #     for nn in name:
    #         pp_n : Package = self.getPackage(nn, self)
    #         pkg.pkg_m[pp_n.name] = pp_n
    #     self._log.debug("<-- load_rgy %s" % name)
    #     return pkg
    
    def getPackageNames(self, ml):
        names = []
        for p in self._pkg_providers:
            for n in p.getPackageNames(ml):
                if n not in names:
                    n.append(n)
        return names

    def getPackage(self, name, loader : PackageLoader) -> Package:
        pkg = self.findPackage(name, loader)

        if not pkg:
            raise Exception("Failed to find package %s" % name)
        return pkg
    
    def findPackage(self, name, loader : PackageLoader) -> Optional[Package]:
        pkg = None

        for p in self._pkg_providers:
            pkg = p.findPackage(name, loader)
            if pkg:
                break

        return pkg

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

    def popPath(self):
        self._file_s.pop()

    def evalExpr(self, expr : str) -> str:
        if "${{" in expr:
            expr = self._eval.eval(expr)
        return expr

    def resolve_variable(self, name):
        self._log.debug("--> resolve_variable %s" % name)
        ret = None
        if len(self._pkg_s):
            ret = self._pkg_s[-1].resolve_variable(name)
        else:
            ret = self._loader_scope.resolve_variable(name)

        self._log.debug("<-- resolve_variable %s -> %s" % (name, str(ret)))
        return ret
    
    def _getSimilarError(self, name, only_tasks=False):
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
