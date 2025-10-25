import abc
from typing import List, Optional, Protocol, TYPE_CHECKING
from .package import Package

if TYPE_CHECKING:
    from .package_loader_p import PackageLoader

class PackageProvider(Protocol):

    @abc.abstractmethod
    def getPackageNames(self, loader : 'PackageLoader') -> List[str]: pass

    @abc.abstractmethod
    def getPackage(self, name : str, loader : 'PackageLoader') -> Package: pass
    
    @abc.abstractmethod
    def findPackage(self, name : str, loader : 'PackageLoader') -> Optional[Package]: pass


