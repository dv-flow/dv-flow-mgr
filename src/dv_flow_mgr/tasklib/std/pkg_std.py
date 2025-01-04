import dataclasses as dc
from ...package_def import Package
from .task_fileset import TaskFileSetCtor

@dc.dataclass
class PackageStd(Package):

    def __post_init__(self):
        print("PackageStd::__post_init__", flush=True)
        self.tasks["FileSet"] = TaskFileSetCtor()

    pass

