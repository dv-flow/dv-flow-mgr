import dataclasses as dc
from typing import Dict, Optional

@dc.dataclass
class TaskNodeCtxt(object):
    """Holds data shared with all task-graph nodes"""
    root_pkgdir : str
    root_rundir : str
    env : Dict
    naming_scheme : Optional['NamingScheme'] = None
    root_package_name : str = ""
