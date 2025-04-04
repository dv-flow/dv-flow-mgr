import dataclasses as dc
from .package import Package

@dc.dataclass
class PackageRoot(Package):
    """
    PackageRoot is a tree of all content referenced
    under a root package"
    """

    pass