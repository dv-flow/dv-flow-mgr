from abc import abstractmethod
from .package import Package
from typing import Optional

class PackageFactory(object):

    @abstractmethod
    def create(self, 
               override : Optional[Package]=None) -> Package:
        pass

    pass