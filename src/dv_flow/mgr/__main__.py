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
class _LazyCmd:
    """Wrapper that defers importing a command class until it's called."""
    def __init__(self, module_path, class_name):
        self._module_path = module_path
        self._class_name = class_name
        self._instance = None
    def __call__(self, *args, **kwargs):
        if self._instance is None:
            import importlib
            mod = importlib.import_module(self._module_path, __package__)
            self._instance = getattr(mod, self._class_name)()
        return self._instance(*args, **kwargs)

def _lazy(module_path, class_name):
    return _LazyCmd(module_path, class_name)


class _CmdMcp:
    """Start DFM as an MCP server on stdio."""

    def __call__(self, args):
        import asyncio, sys
        from .cmds.util import get_rootdir
        from .util import loadProjPkgDef
        from .task_listener_log import TaskListenerLog
        from .task_data import SeverityE

        listener = TaskListenerLog()
        try:
            loader, pkg = loadProjPkgDef(
                get_rootdir(args),
                listener=listener.marker,
                config=getattr(args, 'config', None),
            )
        except Exception as e:
            print(f"Error loading project: {e}", file=sys.stderr)
            return 1
        if listener.has_severity[SeverityE.Error] > 0 or pkg is None:
            print("Error loading project.", file=sys.stderr)
            return 1

        try:
            from .cmds.agent.dfm_mcp_server import run_mcp_server
        except ImportError as e:
            print(f"MCP server requires: pip install dv-flow-mgr[agent]\n({e})", file=sys.stderr)
            return 1

        asyncio.run(run_mcp_server(pkg, loader))
        return 0

class _CmdWorker:
    """Run as a worker process, connecting to a daemon."""

    def __call__(self, args):
        import asyncio
        from .worker import run_worker

        asyncio.run(run_worker(
            connect_addr=args.connect,
            worker_id=args.worker_id,
            resource_class=args.resource_class,
            lsf_job_id=args.lsf_job_id,
        ))
        return 0

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
                        help="Parameter override. For package params: -D param=value. "
                             "For task params: -D task.param=value or -D pkg.task.param=value. "
                             "Lists auto-convert: -D top=counter becomes ['counter']. "
                             "May be used multiple times")
    parser.add_argument("-P", "--param-file",
                        dest="param_file",
                        metavar="FILE_OR_JSON",
                        help="JSON file path or inline JSON string for complex parameter types. "
                             "Inline example: -P '{\"tasks\": {\"build\": {\"top\": [\"counter\"]}}}'. "
                             "CLI -D options take precedence over -P values")
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
    graph_parser.set_defaults(func=_lazy(".cmds.cmd_graph", "CmdGraph"))

    run_parser = subparsers.add_parser('run', help='run a flow')
    run_parser.add_argument("tasks", nargs='*', help="tasks to run")
    run_parser.add_argument("-j",
                        help="Specifies degree of parallelism. Uses all cores by default",
                        type=int, default=-1)
    run_parser.add_argument("--clean",
                            action="store_true",
                            help="Cleans the rundir before running")
    run_parser.add_argument("--base-rundir",
                            dest="base_rundir",
                            default=None,
                            metavar="PATH",
                            help="Reuse artifacts from a pre-built rundir. Tasks present in "
                                 "this directory are assumed up-to-date and not re-executed.")
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
                        help="Console UI style (log, progress, progressbar, tui). Default: progress if terminal else log",
                        choices=("log","progress","progressbar","tui"),
                        default=None)
    run_parser.add_argument("-D",
                        dest="param_overrides",
                        action="append",
                        default=[],
                        metavar="NAME=VALUE",
                        help="Parameter override. For package params: -D param=value. "
                             "For task params: -D task.param=value. "
                             "May be used multiple times")
    run_parser.add_argument("-P", "--param-file",
                        dest="param_file",
                        metavar="FILE_OR_JSON",
                       help="JSON file or inline JSON string (e.g., '{\"tasks\": {...}}')")
    run_parser.add_argument("--runner",
                        help="Runner backend: 'local' (in-process), 'lsf' (embedded LSF pool), "
                             "or omit for auto-detect (daemon if running, else local)",
                        default=None)
    run_parser.add_argument("--runner-opt",
                        dest="runner_opts",
                        action="append",
                        default=[],
                        metavar="KEY=VALUE",
                        help="Runner backend option (key=value). May be used multiple times")
    run_parser.add_argument("--override",
                        dest="overrides",
                        action="append",
                        default=[],
                        metavar="TARGET=REPLACEMENT",
                        help="Override a task: TARGET=REPLACEMENT (e.g. pkg.Task=std.Null)")
    run_parser.set_defaults(func=_lazy(".cmds.cmd_run", "CmdRun"))

    # Completion command
    complete_parser = subparsers.add_parser('complete',
        help='Print tab-completion candidates for task names')
    complete_parser.add_argument('prefix', nargs='?', default='',
        help='Partial task name to complete')
    complete_parser.add_argument('--root',
        help='Specifies the root directory for the flow')
    complete_parser.add_argument('-c', '--config',
        help='Specifies the active configuration for the root package')
    complete_parser.set_defaults(func=_lazy(".cmds.cmd_complete", "CmdComplete"))

    show_parser = subparsers.add_parser('show', 
                                        help='Display and search packages, tasks, types, and tags')
    show_parser.set_defaults(func=_lazy(".cmds.cmd_show", "CmdShow"))

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
    show_packages_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowPackages"))

    # show tasks
    show_tasks_parser = show_subparsers.add_parser('tasks',
                                                    help='List and search tasks')
    add_common_show_args(show_tasks_parser)
    show_tasks_parser.add_argument("--package",
                                   help="Filter tasks by package name")
    show_tasks_parser.add_argument("--scope",
                                   choices=["root", "export", "local"],
                                   help="Filter tasks by visibility scope")
    show_tasks_parser.add_argument("--produces",
                                   help="Filter tasks by produces pattern (e.g., 'type=std.FileSet,filetype=verilog')")
    show_tasks_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowTasks"))

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
    show_task_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowTask"))

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
    show_types_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowTypes"))

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
    show_tags_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowTags"))

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
    show_package_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowPackage"))

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
    show_project_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowProject"))

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
    show_skills_parser.set_defaults(func=_lazy(".cmds.show", "CmdShowSkills"))

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
    cache_init_parser.set_defaults(cache_func=_lazy(".cmds.cache.cmd_init", "CmdCacheInit"))
    
    cache_parser.set_defaults(func=_lazy(".cmds.cmd_cache", "CmdCache"))

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
    validate_parser.set_defaults(func=_lazy(".cmds.cmd_validate", "CmdValidate"))

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
    context_parser.set_defaults(func=_lazy(".cmds.cmd_context", "CmdContext"))

    agent_parser = subparsers.add_parser('agent',
        help='Launch an AI assistant with DV Flow context')
    agent_parser.add_argument('tasks',
        nargs='*',
        help='Task references to use as context (skills, personas, tools, references)')
    agent_parser.add_argument('-a', '--assistant',
        choices=['copilot', 'codex', 'mock', 'native'],
        help='Specify which assistant to use (default: native if no subprocess CLI detected)')
    agent_parser.add_argument('-m', '--model',
        help='Specify the AI model to use')
    agent_parser.add_argument('--root',
        help='Specifies the root directory for the flow')
    agent_parser.add_argument('-c', '--config',
        help='Specifies the active configuration for the root package')
    agent_parser.add_argument('-D',
        dest='param_overrides',
        action='append',
        default=[],
        metavar='NAME=VALUE',
        help='Parameter override; may be used multiple times')
    agent_parser.add_argument('--config-file',
        help='Output assistant config file instead of launching (for debugging)')
    agent_parser.add_argument('--json',
        action='store_true',
        help='Output context as JSON instead of launching assistant')
    agent_parser.add_argument('--clean',
        action='store_true',
        help='Clean rundir before executing tasks')
    agent_parser.add_argument('--ui',
        choices=['log', 'progress', 'progressbar', 'tui'],
        help='Select UI mode for task execution')
    agent_parser.add_argument('--approval-mode',
        dest='approval_mode',
        choices=['never', 'auto', 'write'],
        help='Tool approval mode: never (run all), auto/write (prompt before write/shell tools)')
    agent_parser.add_argument('--trace',
        action='store_true',
        help='Enable agent tracing to ~/.dfm/traces/ (or trace_dir in config)')
    agent_parser.set_defaults(func=_lazy(".cmds.cmd_agent", "CmdAgent"))

    mcp_parser = subparsers.add_parser('mcp',
        help='Start DFM as an MCP server (stdio) for Claude Desktop, Cursor, VS Code, etc.')
    mcp_parser.add_argument('tasks',
        nargs='*',
        help='Task references to use as context (skills, personas, tools, references)')
    mcp_parser.add_argument('--root',
        help='Specifies the root directory for the flow')
    mcp_parser.add_argument('-c', '--config',
        help='Specifies the active configuration for the root package')
    mcp_parser.set_defaults(func=_lazy(".__main__", "_CmdMcp"))

    daemon_parser = subparsers.add_parser('daemon',
        help='Manage the background daemon (worker pool manager)')
    daemon_subparsers = daemon_parser.add_subparsers(dest='daemon_subcmd')

    daemon_start_parser = daemon_subparsers.add_parser('start',
        help='Start the daemon')
    daemon_start_parser.add_argument('--root',
        help='Project root directory')
    daemon_start_parser.add_argument('--runner',
        help='Runner backend (e.g. local, lsf)')
    daemon_start_parser.add_argument('--pool-size',
        type=int, default=None,
        help='Maximum number of workers')
    daemon_start_parser.add_argument('--monitor',
        action='store_true',
        help='Attach monitor TUI after starting')
    daemon_start_parser.add_argument('--foreground',
        action='store_true',
        help='Run daemon in foreground (default is background)')

    daemon_stop_parser = daemon_subparsers.add_parser('stop',
        help='Stop the daemon')
    daemon_stop_parser.add_argument('--root',
        help='Project root directory')

    daemon_status_parser = daemon_subparsers.add_parser('status',
        help='Show daemon status')
    daemon_status_parser.add_argument('--root',
        help='Project root directory')
    daemon_status_parser.add_argument('--json',
        action='store_true',
        help='Output in JSON format')

    daemon_parser.set_defaults(func=_lazy(".cmds.cmd_daemon", "CmdDaemon"))

    worker_parser = subparsers.add_parser('worker',
        help='Run as a worker process (internal, used by daemon)')
    worker_parser.add_argument('--connect',
        required=True,
        help='Daemon address to connect to (host:port)')
    worker_parser.add_argument('--worker-id',
        default=None,
        help='Worker ID (auto-generated if not specified)')
    worker_parser.add_argument('--resource-class',
        default='',
        help='Resource class this worker provides')
    worker_parser.add_argument('--lsf-job-id',
        default='',
        help='LSF job ID (if launched via bsub)')
    worker_parser.set_defaults(func=_lazy(".__main__", "_CmdWorker"))

    util_parser = subparsers.add_parser('util',
        help="Internal utility command")
    util_parser.add_argument("cmd")
    util_parser.add_argument("args", nargs=argparse.REMAINDER)
    util_parser.set_defaults(func=_lazy(".cmds.cmd_util", "CmdUtil"))

    return parser


def _run_client_mode(socket_path: str) -> int:
    """
    Run dfm in client mode, forwarding commands to the parent session's server.
    
    This is used when DFM_SERVER_SOCKET is set, indicating we're running
    inside an LLM assistant process within an Agent task.
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
