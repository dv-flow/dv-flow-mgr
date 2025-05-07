import dataclasses as dc
from .package import Package
from .config import Config

@dc.dataclass
class PackageNode(object):
    """Represents a specific package specialization"""
    pkg : Package
    cfg : Config

