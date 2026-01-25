#****************************************************************************
#* cmd_show.py
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
import logging
from typing import ClassVar


class CmdShow(object):
    """Main show command - displays available sub-commands."""
    _log : ClassVar = logging.getLogger("CmdShow")

    def __call__(self, args):
        # Check if a sub-command was invoked
        show_subcommand = getattr(args, 'show_subcommand', None)
        
        if show_subcommand is not None:
            # Sub-command was specified, argparse already set the right func
            # This path shouldn't normally be hit since argparse handles dispatch
            return 0
        
        # No sub-command specified - show available sub-commands
        print("Usage: dfm show <subcommand> [options]")
        print("")
        print("Available sub-commands:")
        print("  packages  - List and search available packages")
        print("  package   - Display detailed information about a package")
        print("  tasks     - List and search tasks")
        print("  task      - Display detailed information about a task")
        print("  types     - List and search data types")
        print("  tags      - List tag types and their usage")
        print("  project   - Display current project structure")
        print("  skills    - List and query agent skills")
        print("")
        print("Run 'dfm show <subcommand> --help' for more information on a command.")
        
        return 0
