from __future__ import annotations

import abc
import dataclasses as dc
from typing import Dict, List, Optional, Union
from .task import Task
from .type import Type
from .package import Package
from .package_provider import PackageProvider
from .srcinfo import SrcInfo
from .marker_listener import MarkerListener

@dc.dataclass
class PackageLoaderP(MarkerListener):
    marker_listeners : List[MarkerListener] = dc.field(default_factory=list)

    @abc.abstractmethod
    def getPackageNames(self) -> List[str]: ...

    @abc.abstractmethod
    def getPackage(self, name : str) -> Package: ...
    
    @abc.abstractmethod
    def findPackage(self, name : str) -> Optional[Package]: ...

    @abc.abstractmethod
    def findType(self, name) -> Optional[Type]: pass

    @abc.abstractmethod
    def findTask(self, name) -> Optional[Task]: pass

    def findTaskOrType(self, name) -> Optional[Union[Type,Task]]: pass

    @abc.abstractmethod
    def pathStack(self) -> List[str]: ...

    @abc.abstractmethod
    def pushPath(self, path): pass

    @abc.abstractmethod
    def popPath(self): pass

    @abc.abstractmethod
    def rootDir(self) -> str: ...

    @abc.abstractmethod
    def evalExpr(self, expr : str) -> str: pass

    @abc.abstractmethod
    def pushEvalScope(self, vars : Dict[str,object], inherit=True): pass

    @abc.abstractmethod
    def popEvalScope(self): pass

    @abc.abstractmethod
    def feedsMap(self) -> Dict[str,List[Task]]: ...

    @abc.abstractmethod
    def addFeed(self, task : Task, fed_name : str): ...

    @abc.abstractmethod
    def getSimilarNamesError(self, name : str, only_tasks : bool=False) -> str: ...

    @abc.abstractmethod
    def error(self, msg : str, src : Optional[SrcInfo]=None): ...



