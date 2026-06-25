import argparse
import json
import os
from ..package import Package
from ..util.util import loadProjPkgDef

class CmdUtil(object):

    def __call__(self, args):

        if args.cmd == "workspace":
            self.workspace(args)
        elif args.cmd == "schema":
            self.schema(args)
        else:
            raise Exception("Unknown util command '%s' (expected 'workspace' or 'schema')" % args.cmd)

    def schema(self, args):
        from ..util.cmds.cmd_schema import CmdSchema

        parser = argparse.ArgumentParser(prog="dfm util schema",
            description="Output JSON schema for DV Flow definitions")
        parser.add_argument("-o", "--output",
            help="Destination file (default: stdout)",
            default="-")
        parser.add_argument("--generate",
            action="store_true",
            help="Generate schema from Pydantic models instead of "
                 "loading the canonical schema (development mode)")
        schema_args = parser.parse_args(args.args)

        CmdSchema()(schema_args)

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