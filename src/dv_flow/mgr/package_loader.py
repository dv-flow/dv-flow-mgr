import abc
from typing import Dict, Optional, Union
from .task import Task
from .type import Type
from .package import Package
from .package_provider import PackageProvider
from .marker_listener import MarkerListener

class PackageLoader(PackageProvider,MarkerListener):

    @abc.abstractmethod
    def findType(self, name) -> Optional[Type]: pass

    @abc.abstractmethod
    def findTask(self, name) -> Optional[Task]: pass

    def findTaskOrType(self, name) -> Optional[Union[Type,Task]]: pass

    @abc.abstractmethod
    def pushPath(self, path): pass

    @abc.abstractmethod
    def popPath(self): pass

    @abc.abstractmethod
    def evalExpr(self, expr : str) -> str: pass

    @abc.abstractmethod
    def pushEvalScope(self, vars : Dict[str,object], inherit=True): pass

    @abc.abstractmethod
    def popEvalScope(self): pass



