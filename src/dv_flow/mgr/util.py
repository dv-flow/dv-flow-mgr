import os
import yaml
from .package_def import PackageDef

def loadProjPkgDef(path):
    """Locates the project's flow spec and returns the PackageDef"""

    dir = path
    ret = None
    while dir != "/" and dir != "" and os.path.isdir(dir):
        if os.path.exists(os.path.join(dir, "flow.dv")):
            with open(os.path.join(dir, "flow.dv")) as f:
                data = yaml.load(f, Loader=yaml.FullLoader)
                if "package" in data.keys():
                    ret = PackageDef.load(os.path.join(dir, "flow.dv"))
                    break
        dir = os.path.dirname(dir)
    return ret

