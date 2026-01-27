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
import json
import logging
import os
from .cmds.cmd_graph import CmdGraph
from .cmds.cmd_run import CmdRun
from .cmds.cmd_show import CmdShow
from .cmds.cmd_util import CmdUtil
from .cmds.cmd_cache import CmdCache
from .cmds.cmd_validate import CmdValidate
from .cmds.cmd_context import CmdContext
from .cmds.cache.cmd_init import CmdCacheInit
from .cmds.show import (
    CmdShowPackages, CmdShowTasks, CmdShowTask,
    CmdShowTypes, CmdShowTags, CmdShowPackage, CmdShowProject,
    CmdShowSkills
)
from .ext_rgy import ExtRgy

def _get_skill_path():
    """Get the absolute path to the skill.md file."""
    import dv_flow.mgr
    pkg_dir = os.path.dirname(os.path.abspath(dv_flow.mgr.__file__))
    return os.path.join(pkg_dir, "share", "skill.md")

def get_parser():
    skill_path = _get_skill_path()
    parser = argparse.ArgumentParser(
        description='DV Flow Manager (dfm) - A dataflow-based build system for silicon design and verification.',
        epilog=f'For LLM agents: See the skill file at: {skill_path}',
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
    graph_parser.add_argument("-c", "--config",
                              help="Specifies the active configuration for the root package")
    graph_parser.add_argument("-o", "--output", 
                              help="Specifies the output file",
                              default="-")
    graph_parser.add_argument("-D",
                        dest="param_overrides",
                        action="append",
                        default=[],
                        metavar="NAME=VALUE",
                        help="Parameter override; may be used multiple times")
    graph_parser.add_argument("--show-params",
                        action="store_true",
                        help="Show parameter values in node labels")
    graph_parser.add_argument("--json",
                        action="store_true",
                        help="Output graph wrapped in JSON with markers for programmatic consumption")
    graph_parser.set_defaults(func=CmdGraph())

    run_parser = subparsers.add_parser('run', help='run a flow')
    run_parser.add_argument("tasks", nargs='*', help="tasks to run")
    run_parser.add_argument("-j",
                        help="Specifies degree of parallelism. Uses all cores by default",
                        type=int, default=-1)
    run_parser.add_argument("--clean",
                            action="store_true",
                            help="Cleans the rundir before running")
    run_parser.add_argument("-f", "--force",
                            action="store_true",
                            help="Force all tasks to run, ignoring up-to-date status")
    run_parser.add_argument("-v", "--verbose",
                            action="store_true",
                            help="Show all tasks including up-to-date ones")
    run_parser.add_argument("--root", 
                              help="Specifies the root directory for the flow")
    run_parser.add_argument("-c", "--config",
                            help="Specifies the active configuration for the root package")
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
                                        help='Display and search packages, tasks, types, and tags')
    show_parser.set_defaults(func=CmdShow())

    # Show sub-commands
    show_subparsers = show_parser.add_subparsers(dest='show_subcommand')

    # Common show arguments helper
    def add_common_show_args(parser):
        parser.add_argument("--search",
                            help="Search by keyword in name, desc, and doc")
        parser.add_argument("--regex",
                            help="Search by regex pattern in desc and doc")
        parser.add_argument("--tag",
                            help="Filter by tag (format: TagType or TagType:field=value)")
        parser.add_argument("--json",
                            action="store_true",
                            help="Output in JSON format")
        parser.add_argument("-v", "--verbose",
                            action="store_true",
                            help="Show additional details")
        parser.add_argument("-D",
                            dest="param_overrides",
                            action="append",
                            default=[],
                            metavar="NAME=VALUE",
                            help="Parameter override")
        parser.add_argument("-c", "--config",
                            help="Specifies the active configuration")
        parser.add_argument("--root",
                            help="Specifies the root directory for the flow")

    # show packages
    show_packages_parser = show_subparsers.add_parser('packages',
                                                       help='List and search available packages')
    add_common_show_args(show_packages_parser)
    show_packages_parser.set_defaults(func=CmdShowPackages())

    # show tasks
    show_tasks_parser = show_subparsers.add_parser('tasks',
                                                    help='List and search tasks')
    add_common_show_args(show_tasks_parser)
    show_tasks_parser.add_argument("--package",
                                   help="Filter tasks by package name")
    show_tasks_parser.add_argument("--scope",
                                   choices=["root", "export", "local"],
                                   help="Filter tasks by visibility scope")
    show_tasks_parser.set_defaults(func=CmdShowTasks())

    # show task <name>
    show_task_parser = show_subparsers.add_parser('task',
                                                   help='Display detailed information about a task')
    show_task_parser.add_argument("name", help="Task name (e.g., std.FileSet)")
    show_task_parser.add_argument("--needs",
                                  nargs='?',
                                  const=-1,
                                  type=int,
                                  metavar="DEPTH",
                                  help="Show dependency chain. Optional DEPTH limits levels (-1=unlimited)")
    show_task_parser.add_argument("--json",
                                  action="store_true",
                                  help="Output in JSON format")
    show_task_parser.add_argument("-v", "--verbose",
                                  action="store_true",
                                  help="Show additional details")
    show_task_parser.add_argument("-D",
                                  dest="param_overrides",
                                  action="append",
                                  default=[],
                                  metavar="NAME=VALUE",
                                  help="Parameter override")
    show_task_parser.add_argument("-c", "--config",
                                  help="Specifies the active configuration")
    show_task_parser.add_argument("--root",
                                  help="Specifies the root directory for the flow")
    show_task_parser.set_defaults(func=CmdShowTask())

    # show types
    show_types_parser = show_subparsers.add_parser('types',
                                                    help='List and search data types')
    add_common_show_args(show_types_parser)
    show_types_parser.add_argument("--package",
                                   help="Filter types by package name")
    show_types_parser.add_argument("--tags-only",
                                   action="store_true",
                                   help="Show only tag types (deriving from std.Tag)")
    show_types_parser.add_argument("--data-items-only",
                                   action="store_true",
                                   help="Show only data item types (deriving from std.DataItem)")
    show_types_parser.set_defaults(func=CmdShowTypes())

    # show tags
    show_tags_parser = show_subparsers.add_parser('tags',
                                                   help='List tag types and their usage')
    show_tags_parser.add_argument("--search",
                                  help="Search tag types by keyword")
    show_tags_parser.add_argument("--json",
                                  action="store_true",
                                  help="Output in JSON format")
    show_tags_parser.add_argument("-v", "--verbose",
                                  action="store_true",
                                  help="Show additional details")
    show_tags_parser.add_argument("-D",
                                  dest="param_overrides",
                                  action="append",
                                  default=[],
                                  metavar="NAME=VALUE",
                                  help="Parameter override")
    show_tags_parser.add_argument("-c", "--config",
                                  help="Specifies the active configuration")
    show_tags_parser.add_argument("--root",
                                  help="Specifies the root directory for the flow")
    show_tags_parser.set_defaults(func=CmdShowTags())

    # show package <name>
    show_package_parser = show_subparsers.add_parser('package',
                                                      help='Display detailed information about a package')
    show_package_parser.add_argument("name", help="Package name (e.g., std)")
    show_package_parser.add_argument("--json",
                                     action="store_true",
                                     help="Output in JSON format")
    show_package_parser.add_argument("-v", "--verbose",
                                     action="store_true",
                                     help="Show additional details")
    show_package_parser.add_argument("-D",
                                     dest="param_overrides",
                                     action="append",
                                     default=[],
                                     metavar="NAME=VALUE",
                                     help="Parameter override")
    show_package_parser.add_argument("-c", "--config",
                                     help="Specifies the active configuration")
    show_package_parser.add_argument("--root",
                                     help="Specifies the root directory for the flow")
    show_package_parser.set_defaults(func=CmdShowPackage())

    # show project
    show_project_parser = show_subparsers.add_parser('project',
                                                      help='Display current project structure')
    show_project_parser.add_argument("--imports",
                                     action="store_true",
                                     help="Show imported packages")
    show_project_parser.add_argument("--configs",
                                     action="store_true",
                                     help="Show available configurations")
    show_project_parser.add_argument("--json",
                                     action="store_true",
                                     help="Output in JSON format")
    show_project_parser.add_argument("-v", "--verbose",
                                     action="store_true",
                                     help="Show additional details")
    show_project_parser.add_argument("-D",
                                     dest="param_overrides",
                                     action="append",
                                     default=[],
                                     metavar="NAME=VALUE",
                                     help="Parameter override")
    show_project_parser.add_argument("-c", "--config",
                                     help="Specifies the active configuration")
    show_project_parser.add_argument("--root",
                                     help="Specifies the root directory for the flow")
    show_project_parser.set_defaults(func=CmdShowProject())

    # show skills
    show_skills_parser = show_subparsers.add_parser('skills',
                                                     help='List and query agent skills (DataSet types tagged with AgentSkillTag)')
    show_skills_parser.add_argument("name",
                                    nargs='?',
                                    help="Skill name to show details for (e.g., std.AgentSkill)")
    show_skills_parser.add_argument("--search",
                                    help="Search skills by keyword in name, desc, and skill_doc")
    show_skills_parser.add_argument("--package",
                                    help="Filter skills by package name")
    show_skills_parser.add_argument("--full",
                                    action="store_true",
                                    help="Show full skill documentation (with specific skill)")
    show_skills_parser.add_argument("--json",
                                    action="store_true",
                                    help="Output in JSON format")
    show_skills_parser.add_argument("-v", "--verbose",
                                    action="store_true",
                                    help="Show additional details")
    show_skills_parser.add_argument("-D",
                                    dest="param_overrides",
                                    action="append",
                                    default=[],
                                    metavar="NAME=VALUE",
                                    help="Parameter override")
    show_skills_parser.add_argument("-c", "--config",
                                    help="Specifies the active configuration")
    show_skills_parser.add_argument("--root",
                                    help="Specifies the root directory for the flow")
    show_skills_parser.set_defaults(func=CmdShowSkills())

    # Cache management commands
    cache_parser = subparsers.add_parser('cache',
        help='Cache management commands')
    cache_subparsers = cache_parser.add_subparsers(dest='cache_subcommand')
    
    # cache init subcommand
    cache_init_parser = cache_subparsers.add_parser('init',
        help='Initialize a cache directory')
    cache_init_parser.add_argument('cache_dir',
        help='Path to cache directory')
    cache_init_parser.add_argument('--shared',
        action='store_true',
        help='Create a shared cache for team use with group permissions')
    cache_init_parser.set_defaults(cache_func=CmdCacheInit())
    
    cache_parser.set_defaults(func=CmdCache())

    # Validate command
    validate_parser = subparsers.add_parser('validate',
        help='Validate flow.yaml/flow.dv files for errors and warnings')
    validate_parser.add_argument("flow_file",
                                 nargs='?',
                                 help="Flow file to validate (default: auto-detect)")
    validate_parser.add_argument("--json",
                                 action="store_true",
                                 help="Output in JSON format for programmatic consumption")
    validate_parser.add_argument("-D",
                                 dest="param_overrides",
                                 action="append",
                                 default=[],
                                 metavar="NAME=VALUE",
                                 help="Parameter override")
    validate_parser.add_argument("-c", "--config",
                                 help="Specifies the active configuration")
    validate_parser.add_argument("--root",
                                 help="Specifies the root directory for the flow")
    validate_parser.set_defaults(func=CmdValidate())

    # Context command
    context_parser = subparsers.add_parser('context',
        help='Output comprehensive project context for LLM agent consumption')
    context_parser.add_argument("--json",
                                action="store_true",
                                help="Output in JSON format (default)")
    context_parser.add_argument("--imports",
                                action="store_true",
                                help="Include detailed information about imported packages")
    context_parser.add_argument("--installed",
                                action="store_true",
                                help="Include list of all installed packages")
    context_parser.add_argument("-v", "--verbose",
                                action="store_true",
                                help="Include additional details (docs, params)")
    context_parser.add_argument("-D",
                                dest="param_overrides",
                                action="append",
                                default=[],
                                metavar="NAME=VALUE",
                                help="Parameter override")
    context_parser.add_argument("-c", "--config",
                                help="Specifies the active configuration")
    context_parser.add_argument("--root",
                                help="Specifies the root directory for the flow")
    context_parser.set_defaults(func=CmdContext())

    util_parser = subparsers.add_parser('util',
        help="Internal utility command")
    util_parser.add_argument("cmd")
    util_parser.add_argument("args", nargs=argparse.REMAINDER)
    util_parser.set_defaults(func=CmdUtil())

    return parser


def _run_client_mode(socket_path: str) -> int:
    """
    Run dfm in client mode, forwarding commands to the parent session's server.
    
    This is used when DFM_SERVER_SOCKET is set, indicating we're running
    inside an LLM assistant process within a Prompt task.
    """
    import asyncio
    import sys
    from .dfm_server import DfmClient
    
    async def run_client():
        client = DfmClient(socket_path)
        
        try:
            await client.connect()
            
            # Parse command from sys.argv
            args = sys.argv[1:]
            
            if not args:
                print("Usage: dfm <command> [args...]", file=sys.stderr)
                return 1
            
            cmd = args[0]
            
            if cmd == "run":
                # dfm run task1 task2 ...
                tasks = []
                param_overrides = {}
                timeout = None
                
                i = 1
                while i < len(args):
                    if args[i] == "-D" and i + 1 < len(args):
                        # Parse parameter override
                        override = args[i + 1]
                        if "=" in override:
                            key, value = override.split("=", 1)
                            param_overrides[key] = value
                        i += 2
                    elif args[i] == "--timeout" and i + 1 < len(args):
                        timeout = float(args[i + 1])
                        i += 2
                    elif not args[i].startswith("-"):
                        tasks.append(args[i])
                        i += 1
                    else:
                        i += 1
                
                if not tasks:
                    print("Error: No tasks specified", file=sys.stderr)
                    return 1
                
                result = await client.run(tasks, param_overrides, timeout)
                print(json.dumps(result, indent=2))
                return result.get("status", 0)
            
            elif cmd == "show":
                if len(args) < 2:
                    print("Error: show requires subcommand", file=sys.stderr)
                    return 1
                
                subcmd = args[1]
                
                if subcmd == "tasks":
                    params = {}
                    i = 2
                    while i < len(args):
                        if args[i] == "--package" and i + 1 < len(args):
                            params["package"] = args[i + 1]
                            i += 2
                        elif args[i] == "--scope" and i + 1 < len(args):
                            params["scope"] = args[i + 1]
                            i += 2
                        elif args[i] == "--search" and i + 1 < len(args):
                            params["search"] = args[i + 1]
                            i += 2
                        else:
                            i += 1
                    
                    result = await client.show_tasks(**params)
                    print(json.dumps(result, indent=2))
                    
                elif subcmd == "task" and len(args) > 2:
                    result = await client.show_task(args[2])
                    print(json.dumps(result, indent=2))
                    
                else:
                    print(f"Error: Unknown show subcommand: {subcmd}", file=sys.stderr)
                    return 1
            
            elif cmd == "context":
                include_imports = "--imports" in args
                verbose = "-v" in args or "--verbose" in args
                result = await client.context(include_imports, verbose)
                print(json.dumps(result, indent=2))
            
            elif cmd == "validate":
                file_arg = None
                for i, arg in enumerate(args[1:], 1):
                    if not arg.startswith("-"):
                        file_arg = arg
                        break
                result = await client.validate(file_arg)
                print(json.dumps(result, indent=2))
                return 0 if result.get("valid", False) else 1
            
            elif cmd == "ping":
                result = await client.ping()
                print(json.dumps(result, indent=2))
            
            else:
                print(f"Error: Unknown command: {cmd}", file=sys.stderr)
                return 1
            
            return 0
            
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        finally:
            await client.disconnect()
    
    return asyncio.run(run_client())


def main():
    # Check if we should run in client mode
    socket_path = os.environ.get("DFM_SERVER_SOCKET")
    if socket_path:
        # Running inside an LLM assistant - forward to parent session
        return _run_client_mode(socket_path)
    
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
    import sys
    sys.exit(main() or 0)
