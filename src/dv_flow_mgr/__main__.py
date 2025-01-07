
import argparse
from .cmds.cmd_run import CmdRun

def get_parser():
    parser = argparse.ArgumentParser(description='dv_flow_mgr')
    subparsers = parser.add_subparsers(required=True)

    run_parser = subparsers.add_parser('run', help='run a flow')
    run_parser.add_argument("tasks", nargs='+', help="tasks to run")
    run_parser.set_defaults(func=CmdRun())

    return parser

def main():
    parser = get_parser()
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
