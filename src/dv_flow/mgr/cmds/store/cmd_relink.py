from ...rundir_store_ops import relink_rundir
from .common import project_decision, project_package, project_root


class CmdStoreRelink:
    """dfm store relink [--store DIR]"""

    def __call__(self, args):
        pkg_root = project_root(args)
        d, _ = project_decision(args, pkg_root)
        entry = relink_rundir(pkg_root, d, project_package(pkg_root))
        print("%s/rundir -> %s" % (pkg_root, entry))
        return 0
