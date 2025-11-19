import json
import os
from ..package import Package
from ..util.util import loadProjPkgDef

class CmdUtil(object):

    def __call__(self, args):

        if args.cmd == "workspace":
            self.workspace(args)

    def workspace(self, args):

        pkg : Package = None
        markers = None

        for name in ("flow.dv","flow.yaml","flow.yml","flow.toml"):
            if os.path.isfile(os.path.join(os.getcwd(), name)):
                markers = []
                def marker(m):
                    nonlocal markers
                    print("marker: %s" % str(m))
                    markers.append(m)
                loader, pkg = loadProjPkgDef(os.getcwd(), marker)
                break


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