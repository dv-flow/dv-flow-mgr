import abc
from typing import List, Optional, TYPE_CHECKING
from .package import Package

if TYPE_CHECKING:
    from .package_loader import PackageLoader

class PackageProvider(object):

    @abc.abstractmethod
    def getPackageNames(self, loader : 'PackageLoader') -> List[str]: pass

    @abc.abstractmethod
    def getPackage(self, name : str, loader : 'PackageLoader') -> Package: pass
    
    @abc.abstractmethod
    def findPackage(self, name : str, loader : 'PackageLoader') -> Optional[Package]: pass


