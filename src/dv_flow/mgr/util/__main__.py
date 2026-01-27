import argparse
import logging
from .cmds.cmd_schema import CmdSchema

def get_parser():
    parser = argparse.ArgumentParser(description="dv-flow-mgr.util")
    parser.add_argument("--log-level", 
                        help="Configures debug level [INFO, DEBUG]",
                        choices=("NONE", "INFO", "DEBUG"))

    subparsers = parser.add_subparsers(required=True)

    schema = subparsers.add_parser('schema', 
                                   help='Output JSON schema for DV Flow definitions')
    schema.add_argument("-o", "--output", 
                        help="Destination file (default: stdout)", 
                        default="-")
    schema.add_argument("--generate",
                        action="store_true",
                        help="Generate schema from Pydantic models instead of loading canonical schema (development mode)")
    schema.set_defaults(f=CmdSchema())

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
