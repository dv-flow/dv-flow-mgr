import json
import os
from ...package import Package
from ...util.util import loadProjPkgDef

class CmdWorkspace(object):

    def __call__(self, args):

        pkg : Package = None
        markers = None

        if os.path.isfile(os.path.join(os.getcwd(), "flow.dv")):
            markers = []
            def marker(m):
                nonlocal markers
                print("marker: %s" % str(m))
                markers.append(m)
            pkg = loadProjPkgDef(os.getcwd(), marker)


        if pkg is None and markers is None:
            print("{abc}")
        elif pkg is not None:
            print(json.dumps(pkg.to_json(markers)))
        else:
            result = {}
            result["markers"] = [
                {"msg": marker.msg, "severity": str(marker.severity)}
                for marker in markers
            ]
            print(json.dumps(result))

        pass