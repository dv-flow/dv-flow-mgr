from ...rundir_store_ops import migrate_rundir
from .common import project_decision, project_package, project_root


class CmdStoreMigrate:
    """dfm store migrate"""

    def __call__(self, args):
        pkg_root = project_root(args)
        d, _ = project_decision(args, pkg_root)
        res = migrate_rundir(pkg_root, d, project_package(pkg_root),
                             dry_run=args.dry_run)
        if args.dry_run:
            print("Would move %s/rundir into store %s (from %s)"
                  % (pkg_root, res, d.provenance))
        else:
            print("Migrated %s/rundir -> %s" % (pkg_root, res))
        return 0
