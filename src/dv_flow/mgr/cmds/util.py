import os

def get_rootdir(args):
    rootdir = None
    if hasattr(args, "root") and args.root is not None:
        rootdir = args.root
    elif "DV_FLOW_ROOT" in os.environ.keys():
        rootdir = os.environ["DV_FLOW_ROOT"]
    else:
        rootdir = os.getcwd()
    return rootdir