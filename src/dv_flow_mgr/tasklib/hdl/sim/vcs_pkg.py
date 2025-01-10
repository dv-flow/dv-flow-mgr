import dataclasses as dc
from .pkg_hdl_sim import PackageHdlSim
from .vcs_task_sim_image import TaskVcsSimImageCtor
from .vcs_task_sim_run import TaskVcsSimRunCtor

@dc.dataclass
class VcsPackage(PackageHdlSim):

    def __post_init__(self):
        print("PackageVcs::__post_init__", flush=True)
        self.tasks["SimImage"] = TaskVcsSimImageCtor()
        self.tasks["SimRun"] = TaskVcsSimRunCtor()
    pass

