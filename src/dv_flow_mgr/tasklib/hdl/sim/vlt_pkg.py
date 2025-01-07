import dataclasses as dc
from .pkg_hdl_sim import PackageHdlSim
from .vlt_task_sim_image import TaskVltSimImageCtor
from .vlt_task_sim_run import TaskVltSimRunCtor

@dc.dataclass
class VltPackage(PackageHdlSim):

    def __post_init__(self):
        print("PackageVlt::__post_init__", flush=True)
        self.tasks["SimImage"] = TaskVltSimImageCtor()
        self.tasks["SimRun"] = TaskVltSimRunCtor()
    pass

