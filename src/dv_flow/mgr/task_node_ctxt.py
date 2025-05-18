import dataclasses as dc
from typing import Dict

@dc.dataclass
class TaskNodeCtxt(object):
    """Holds data shared with all task-graph nodes"""
    root_pkgdir : str
    root_rundir : str
    env : Dict
