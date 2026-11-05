from ...rundir_store_ops import unlink_rundir
from .common import project_root


class CmdStoreUnlink:
    """dfm store unlink [--local] [--keep]"""

    def __call__(self, args):
        pkg_root = project_root(args)
        entry = unlink_rundir(pkg_root, local=args.local, keep=args.keep)
        what = "replaced with a local directory" if args.local else "removed"
        print("%s/rundir link %s" % (pkg_root, what))
        if entry is not None and args.keep:
            print("Store entry %s kept" % entry)
        return 0
