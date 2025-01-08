import dataclasses as dc
from .pkg_hdl_sim import PackageHdlSim
from .mti_task_sim_image import TaskMtiSimImageCtor
from .mti_task_sim_run import TaskMtiSimRunCtor

@dc.dataclass
class MtiPackage(PackageHdlSim):
    def __post_init__(self):
        self.tasks["SimImage"] = TaskMtiSimImageCtor()
        self.tasks["SimRun"] = TaskMtiSimRunCtor()

