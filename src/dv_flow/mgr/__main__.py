#****************************************************************************
#* __main__.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
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
from .cmds.cmd_run import CmdRun

def get_parser():
    parser = argparse.ArgumentParser(description='dv_flow_mgr')
    # parser.add_argument("-d", "--debug", 
    #                     help="Enable debug",
    #                     action="store_true")
    parser.add_argument("--log-level", 
                        help="Configures debug level [INFO, DEBUG]",
                        choices=("NONE", "INFO", "DEBUG"))
    # parser.add_argument("-v", "--verbose", 
    #                     help="Enable verbose output",
    #                     action="store_true")
    subparsers = parser.add_subparsers(required=True)

    run_parser = subparsers.add_parser('run', help='run a flow')
    run_parser.add_argument("tasks", nargs='*', help="tasks to run")
    run_parser.set_defaults(func=CmdRun())

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

    args.func(args)

if __name__ == "__main__":
    main()
