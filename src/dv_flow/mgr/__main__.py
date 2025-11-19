#****************************************************************************
#* __main__.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import argparse
import logging
import os
from .cmds.cmd_graph import CmdGraph
from .cmds.cmd_run import CmdRun
from .cmds.cmd_show import CmdShow
from .cmds.cmd_util import CmdUtil
from .ext_rgy import ExtRgy

def get_parser():
    parser = argparse.ArgumentParser(
        description='dv_flow_mgr',
        prog='dfm')
    # parser.add_argument("-d", "--debug", 
    #                     help="Enable debug",
    #                     action="store_true")
    parser.add_argument("--log-level", 
                        help="Configures debug level [INFO, DEBUG]",
                        choices=("NONE", "INFO", "DEBUG"))
    parser.add_argument("-D",
                        dest="param_overrides",
                        action="append",
                        default=[],
                        metavar="NAME=VALUE",
                        help="Parameter override; may be used multiple times")
    # parser.add_argument("-v", "--verbose", 
    #                     help="Enable verbose output",
    #                     action="store_true")
    subparsers = parser.add_subparsers(required=True)

    graph_parser = subparsers.add_parser('graph', 
                                         help='Generates the graph of a task')
    graph_parser.add_argument("task", nargs="?", help="task to graph")
    graph_parser.add_argument("-f", "--format", help="Specifies the output format",
                              default="dot")
    graph_parser.add_argument("--root", 
                              help="Specifies the root directory for the flow")
    graph_parser.add_argument("-o", "--output", 
                              help="Specifies the output file",
                              default="-")
    graph_parser.add_argument("-D",
                        dest="param_overrides",
                        action="append",
                        default=[],
                        metavar="NAME=VALUE",
                        help="Parameter override; may be used multiple times")
    graph_parser.set_defaults(func=CmdGraph())

    run_parser = subparsers.add_parser('run', help='run a flow')
    run_parser.add_argument("tasks", nargs='*', help="tasks to run")
    run_parser.add_argument("-j",
                        help="Specifies degree of parallelism. Uses all cores by default",
                        type=int, default=-1)
    run_parser.add_argument("--clean",
                            action="store_true",
                            help="Cleans the rundir before running")
    run_parser.add_argument("--root", 
                              help="Specifies the root directory for the flow")
    run_parser.add_argument("-u", "--ui",
                        help="Console UI style (log, progress, tui). Default: progress if terminal else log",
                        choices=("log","progress","tui"),
                        default=None)
    run_parser.add_argument("-D",
                        dest="param_overrides",
                        action="append",
                        default=[],
                        metavar="NAME=VALUE",
                        help="Parameter override; may be used multiple times")
    run_parser.set_defaults(func=CmdRun())

    show_parser = subparsers.add_parser('show', 
                                        help='Display information about a task or tasks')
    show_parser.add_argument("task", nargs='?', help="task to show")
    show_parser.add_argument("-a", "--all",
                        action="store_true",
                        help="Shows all tasks required for the subject to run")
    show_parser.add_argument("-v", "--verbose",
                        action="store_true",
                        help="Shows additional information about tasks")
    show_parser.add_argument("-D",
                        dest="param_overrides",
                        action="append",
                        default=[],
                        metavar="NAME=VALUE",
                        help="Parameter override; may be used multiple times")
    show_parser.set_defaults(func=CmdShow())

    util_parser = subparsers.add_parser('util',
        help="Internal utility command")
    util_parser.add_argument("cmd")
    util_parser.add_argument("args", nargs=argparse.REMAINDER)
    util_parser.set_defaults(func=CmdUtil())

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

    return args.func(args)

if __name__ == "__main__":
    main()
