import dataclasses as dc

@dc.dataclass
class TaskNodeCtxt(object):
    """Holds data shared with all task-graph nodes"""
    root_pkgdir : str
    root_rundir : str
