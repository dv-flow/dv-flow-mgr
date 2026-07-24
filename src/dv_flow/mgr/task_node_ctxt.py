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
    # Per-run output-data identity; every std.Publish task in a run shares this
    # so they publish into the same <root_rundir>/out/<run_id> directory.
    run_id : str = ""
