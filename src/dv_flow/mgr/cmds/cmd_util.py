import argparse
import json
import os
from ..package import Package
from ..util.util import loadProjPkgDef
from ..ext_rgy import ExtRgy

class CmdUtil(object):

    @staticmethod
    def get_parser(self=None):

        ext_rgy = ExtRgy.inst()

        parser = argparse.ArgumentParser(
            description='Utility commands for dv_flow_mgr',
            prog='dfm util')
        subparsers = parser.add_subparsers(dest='cmd', required=True)
        help = subparsers.add_parser('help',
                                       help='Display this help message')
        if self is not None:
            help.set_defaults(func=self.help)

        for ext in ext_rgy.utilcmd_ext:
            ext(subparsers)

        workspace = subparsers.add_parser('workspace', 
                                       help='Display information about the workspace')
        if self is not None:
            workspace.set_defaults(func=self.workspace)

        for ext in ext_rgy._subcmd_ext:
            ext(subparsers)

        return parser

    def __call__(self, args):
        parser = CmdUtil.get_parser(self)

        in_args = [args.cmd]
        in_args.extend(args.args)
        util_args = parser.parse_args(in_args)

        util_args.func(util_args)

    def help(self, args):
        parser = CmdUtil.get_parser(self)
        parser.print_help()

    def mk_run_spec(self, args):
        dir = os.path.dirname(args.output)
        if dir and not os.path.isdir(dir):
            os.makedirs(os.path.dirname(args.output))

        with open(args.spec, "r") as f:
            try:
                spec = json.load(f)
            except Exception as e:
                print("Error reading spec file '%s': %s" % (args.spec, str(e)))
                raise e
            
        desc = spec.get("desc", "")


        with open(args.output, "w") as f:
            run_spec = {
                "name": "name",
                "type": spec["type"],
                "inputs": [],
                "params": {},
                "shell": "",
                "run": "",
                "description": desc,
                "root_rundir": args.root_rundir,
                "root_pkgdr": args.root_pkgdr
            }
            json.dump(run_spec, f, indent=4)
        pass

    def workspace(self, args):

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


    def run_spec(self, args):
        if args.status is not None:
            print("Status: %s" % args.status)
            if not os.path.isfile(args.status):
                with open(args.status, "w") as f:
                    f.write("\n")
        print("run-spec")