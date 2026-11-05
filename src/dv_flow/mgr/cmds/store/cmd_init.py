import os
import stat

from ...rundir_store_entry import is_store_root, write_marker


class CmdStoreInit:
    """dfm store init <dir> [--shared|--group]"""

    def __call__(self, args):
        root = os.path.abspath(os.path.expanduser(args.dir))
        mode = "shared" if args.shared else ("group" if args.group else "private")
        os.makedirs(root, exist_ok=True)
        if is_store_root(root):
            print("%s is already a rundir store" % root)
        else:
            write_marker(root, mode)
            print("Initialized rundir store %s (%s)" % (root, mode))
        if args.shared:
            os.chmod(root, 0o1777)
        elif args.group:
            os.chmod(root, 0o2775)
        print("Mode: %s" % oct(stat.S_IMODE(os.stat(root).st_mode)))
        return 0
