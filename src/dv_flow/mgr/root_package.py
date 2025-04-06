import dataclasses as dc
from .package import Package

@dc.dataclass
class RootPackage(Package):
    
    def dump(self):
        pass

