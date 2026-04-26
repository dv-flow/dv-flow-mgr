import os

def get_rootdir(args):
    rootdir = None
    if hasattr(args, "root") and args.root is not None:
        rootdir = args.root
    elif "DV_FLOW_ROOT" in os.environ.keys():
        rootdir = os.environ["DV_FLOW_ROOT"]
    else:
        rootdir = os.getcwd()

    rootdir = os.path.abspath(rootdir)

    return rootdir

def get_naming_scheme():
    """Return the naming scheme string from DV_FLOW_RUNDIR_LAYOUT (default: 'legacy')."""
    return os.environ.get("DV_FLOW_RUNDIR_LAYOUT", "legacy")
