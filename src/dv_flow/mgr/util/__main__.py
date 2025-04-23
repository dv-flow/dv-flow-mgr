import argparse
import logging
from .cmds.cmd_schema import CmdSchema
from .cmds.cmd_workspace import CmdWorkspace

def get_parser():
    parser = argparse.ArgumentParser(description="dv-flow-mgr.util")
    parser.add_argument("--log-level", 
                        help="Configures debug level [INFO, DEBUG]",
                        choices=("NONE", "INFO", "DEBUG"))

    subparsers = parser.add_subparsers(required=True)

    schema = subparsers.add_parser('schema', help='Write schema')
    schema.add_argument("-o", "--output", 
                        help="Destination file", 
                        default="-")
    schema.set_defaults(f=CmdSchema())

    workspace = subparsers.add_parser('workspace', 
                                      help='Dumps the workspace structure in JSON')
    workspace.set_defaults(f=CmdWorkspace())

    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()

    if args.log_level is not None and args.log_level != "NONE":
        opt_m = {
            "INFO": logging.INFO,
            "DEBUG": logging.DEBUG
        }
        logging.basicConfig(level=opt_m[args.log_level])

    args.f(args)

if __name__ == "__main__":
    main()
