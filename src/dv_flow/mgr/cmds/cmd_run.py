#****************************************************************************
#* cmd_run.py
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
import asyncio
import os
import logging
import shutil
import sys
import time
from typing import ClassVar
from ..ext_rgy import ExtRgy
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..task_data import SeverityE
from ..task_graph_builder import TaskGraphBuilder
from ..task_runner import TaskSetRunner
from ..task_listener_log import TaskListenerLog
from ..cli_task_resolver import CLITaskResolver, TaskResolutionError
from ..task_listener_tui import TaskListenerTui
from ..task_listener_progress import TaskListenerProgress
from ..task_listener_progress_bar import TaskListenerProgressBar
from ..task_listener_trace import TaskListenerTrace
from ..cache_config import load_cache_providers
from .util import get_rootdir, get_naming_scheme
from ..runner_config import load_runner_config


class CmdRun(object):
    _log : ClassVar = logging.getLogger("CmdRun")

    def __call__(self, args):

        # `dfm run` supplies a single `task`; the rest of this method works off
        # a `tasks` list, both because the run machinery below takes a list of
        # roots and because a no-task invocation (which lists the available
        # tasks) is just the empty case. `args.task` stays set, and is the
        # signal for the per-task front-end behavior below.
        if not hasattr(args, "tasks"):
            task = getattr(args, "task", None)
            args.tasks = [task] if task else []

        rgy = ExtRgy.inst()

        # Determine which console listener to use
        ui = getattr(args, 'ui', None)
        if ui is None:
            # Auto-select based on whether output is a terminal
            ui = 'progress' if sys.stdout.isatty() else 'log'
            # When logging is enabled at INFO or above, prefer plain-text log (no rich)
            root_level = logging.getLogger().level
            if root_level <= logging.INFO:
                ui = 'log'

        # If user explicitly requested 'progress' but stdout isn't a TTY, fallback
        explicit = getattr(args, 'ui', None) is not None
        if ui == 'progress' and not sys.stdout.isatty():
            if explicit:
                print("Note: 'progress' UI requested but stdout is not a terminal. Falling back to 'log' UI.")
            ui = 'log'

        listener = TaskListenerLog()

        # Parse parameter overrides from CLI (-D) and file (-P)
        from ..util import load_param_file, merge_parameter_overrides
        
        from ..util import parameter_override_keys
        from ..param_override_tracker import OverrideBindingTracker

        cli_overrides = parse_parameter_overrides(getattr(args, "param_overrides", []))
        # Track where each -D key binds so keys that bind nowhere (typically a
        # typo) can be reported instead of silently ignored. Only -D keys are
        # tracked; -P entries are not command-line keys.
        override_tracker = OverrideBindingTracker(
            keys=parameter_override_keys(getattr(args, "param_overrides", [])))
        file_overrides = {'package': {}, 'task': {}, 'leaf': {}}
        
        if hasattr(args, 'param_file') and args.param_file:
            try:
                file_overrides = load_param_file(args.param_file)
            except Exception as e:
                print(f"Error loading parameter file: {e}")
                sys.exit(1)
        
        # Merge (CLI takes precedence)
        merged_overrides = merge_parameter_overrides(cli_overrides, file_overrides)
        
        # Extract task and leaf overrides for later use
        task_overrides = merged_overrides.get('task', {})
        leaf_overrides = merged_overrides.get('leaf', {})

        # First, find the project we're working with using selected listener for load markers
        loader, pkg = loadProjPkgDef(
            get_rootdir(args),
            listener=listener.marker,
            parameter_overrides=merged_overrides,  # Pass full structure (will extract package params)
            config=getattr(args, "config", None),
            package_maps=getattr(args, "package_map", []),
            override_tracker=override_tracker)

        if listener.has_severity[SeverityE.Error] > 0:
            print("Error(s) encountered while loading package definition")
            sys.exit(1)

        if pkg is None:
            raise Exception("Failed to find a 'flow.yaml/flow.toml' file that defines a package in %s or its parent directories" % os.getcwd())

        assert loader is not None
        self._log.debug("Root flow file defines package: %s" % pkg.name)

        resolver = CLITaskResolver.from_package(pkg)

        # Phase 2a: project-level flags (package variables declared `cli:`).
        # These are consumed BEFORE the task's own, and a package variable that
        # was actually supplied forces a reload -- a package variable is read
        # during the load (a select family's axes, an `iff:`), so binding it
        # afterwards would make `--build cov` and `-D build=cov` mean different
        # things. See _parse_package_args.
        if getattr(args, "task", None) is not None:
            rc, pkg_values = self._parse_package_args(args, resolver, pkg, loader)
            if rc is not None:
                return rc
            if pkg_values:
                merged_overrides.setdefault('package', {}).update(
                    {k: str(v) for k, v in pkg_values.items()})
                loader, pkg = loadProjPkgDef(
                    get_rootdir(args),
                    listener=listener.marker,
                    parameter_overrides=merged_overrides,
                    config=getattr(args, "config", None),
                    package_maps=getattr(args, "package_map", []),
                    override_tracker=override_tracker)
                if pkg is None or listener.has_severity[SeverityE.Error] > 0:
                    print("Error(s) encountered while loading package definition")
                    sys.exit(1)
                resolver = CLITaskResolver.from_package(pkg)

        # Phase 2b of the two-phase parse. The flow has now loaded,
        # so the invoked task's flags are knowable and its own arguments --
        # everything phase 1 could not recognize -- can be parsed. Runs here
        # because the result is folded into task_overrides, which must be final
        # before TaskGraphBuilder is constructed below.
        if getattr(args, "task", None) is not None:
            rc = self._parse_task_args(args, resolver, task_overrides,
                                       pkg=pkg, loader=loader,
                                       overrides=merged_overrides)
            if rc is not None:
                return rc

        if len(args.tasks) > 0:
            pass
            if ui == 'log':
                listener = TaskListenerLog()
            elif ui == 'progress':
                listener = TaskListenerProgress()
            elif ui == 'progressbar':
                listener = TaskListenerProgressBar(message="Initalizing...")
            elif ui == 'tui':
                listener = TaskListenerTui()
            else:
                if explicit:
                    print(f"Unknown UI '{ui}'. Falling back to log.")
                listener = TaskListenerLog()
        else:
            # Print out available tasks
            override_targets = set()
            if hasattr(pkg, 'pkg_def') and pkg.pkg_def is not None:
                for td in pkg.pkg_def.tasks:
                    if getattr(td, 'override', None):
                        override_targets.add(td.override)
            tasks = []
            # Root package tasks
            for task in pkg.task_m.values():
                tasks.append(task)
            # De-duplicate and sort
            tasks = sorted({t.name: t for t in tasks}.values(), key=lambda x: x.name)

            # Filter for 'root' visibility tasks
            root_tasks = [t for t in tasks if getattr(t, 'is_root', False)]

            # A select family's cells are runnable tasks, so they are all
            # root-scoped -- but listing a 3x4 family as twelve lines drowns
            # everything else. Show the FAMILY, with its axes standing in for
            # the cells (`dfm show task <family>` lists them).
            _cells = set()
            for t in tasks:
                select = getattr(getattr(t, 'strategy', None), 'select', None)
                if select is not None:
                    _cells.update("%s.%s" % (t.name, k) for k in select.cells)
            if _cells:
                root_tasks = [t for t in root_tasks if t.name not in _cells]
            
            if root_tasks:
                # Show only root tasks
                tasks = root_tasks
            else:
                # Show warning and all tasks
                print("Warning: No 'root' tasks found in the current package. Runnable tasks must be marked 'scope: root'.")
                print()

            max_name_len = max((len(t.name) for t in tasks), default=0)

            print("No task specified. Available Tasks:")
            for t in tasks:
                desc = t.desc if t.desc else "<no description>"
                select = getattr(getattr(t, 'strategy', None), 'select', None)
                if select is not None:
                    # The axes ARE the description of what this name offers.
                    axes = " x ".join(
                        "%s: %s" % (a, ",".join(str(v) for v in vals))
                        for a, vals in select.axes.items())
                    desc = "%s [%s]" % (desc, axes)
                print(f"{t.name.ljust(max_name_len)} - {desc}")

            pass

        # TODO: allow user to specify run root -- maybe relative to some fixed directory?
        rundir = os.path.join(os.getcwd(), "rundir")

        # Validate --base-rundir
        base_rundir = getattr(args, 'base_rundir', None)
        if base_rundir is not None:
            base_rundir = os.path.abspath(base_rundir)
            if not os.path.isdir(base_rundir):
                print("Error: --base-rundir path does not exist: %s" % base_rundir)
                sys.exit(1)

        if args.clean:
            print("Note: Cleaning rundir %s" % rundir)
            if os.path.exists(rundir):
                shutil.rmtree(rundir)
            os.makedirs(rundir)

        # Load runner configuration and resolve backend
        cli_runner = getattr(args, 'runner', None)
        cli_runner_opts = {}
        for opt in getattr(args, 'runner_opts', []):
            if '=' in opt:
                k, v = opt.split('=', 1)
                cli_runner_opts[k] = v
            else:
                self._log.warning("Ignoring malformed --runner-opt: %s" % opt)

        # The project root is the directory containing the flow file.
        # The daemon writes .dfm/daemon.json here; we look for it to
        # decide whether to delegate to a running daemon.
        project_root = get_rootdir(args)

        runner_config = load_runner_config(
            project_root=project_root,
            cli_runner=cli_runner,
            cli_opts=cli_runner_opts if cli_runner_opts else None,
       )

        # Determine runner backend.
        # - No --runner: auto-detect (daemon if running, else local)
        # - --runner local: force local, ignore daemon
        # - --runner <other>: use that backend directly, ignore daemon
        backend = None
        if cli_runner is None:
            # Auto-detect: delegate to daemon if one is running
            from ..daemon_client import DaemonClientBackend
            daemon_client = DaemonClientBackend.discover(project_root)
            if daemon_client is not None:
                backend = daemon_client
                self._log.info("Auto-detected running daemon at %s", project_root)
            else:
                self._log.info("No daemon detected, using local execution")
        elif cli_runner == "local":
            # Explicit local: always run in-process
            self._log.info("Using local execution (--runner local)")
        else:
            # Explicit non-local runner: instantiate backend directly
            runner_cls = rgy.findRunner(cli_runner)
            if runner_cls is None:
                available = ', '.join(rgy.getRunnerNames())
                print("Error: unknown runner '%s'. Available runners: %s" % (
                    cli_runner, available), file=sys.stderr)
                return 1
            backend = runner_cls(config=runner_config, project_root=project_root)
            self._log.info("Using %s runner backend (--runner %s)", cli_runner, cli_runner)

        # Resolve this run's output-data identity. All std.Publish tasks in the
        # run share it (out/<run_id>); export it so shell tasks can publish too.
        from ..run_id import alloc_run_id
        run_id = getattr(args, "run_id", None) or alloc_run_id(rundir)
        run_env = os.environ.copy()
        run_env["DFM_RUN_ID"] = run_id
        run_env["DFM_OUT_DIR"] = os.path.join(rundir, "out", run_id)

        # Materialize <rundir>/bin (dfm-out, dfm shims) and put it on PATH so
        # shell tasks can invoke them without the entry-point scripts installed.
        from ..out import install_run_bin
        bindir = install_run_bin(rundir)
        run_env["PATH"] = bindir + os.pathsep + run_env.get("PATH", "")

        # Graph-build diagnostics (a task's `requires:` contract, above all) had
        # nowhere to go: the builder's marker channel defaults to a no-op and
        # was never wired, so a violation was recorded and discarded. Collect
        # them here, show them, and gate the run on an error below -- a contract
        # that reports and then runs anyway is worse than no contract.
        build_markers = []

        def _build_marker(marker):
            build_markers.append(marker)
            listener.marker(marker)

        builder = TaskGraphBuilder(
            root_pkg=pkg,
            rundir=rundir,
            loader=loader,
            env=run_env,
            run_id=run_id,
            task_param_overrides=task_overrides,
            leaf_param_overrides=leaf_overrides,
            override_tracker=override_tracker,
            marker_l=_build_marker,
            naming_scheme=get_naming_scheme())

        # Apply CLI --override arguments (TARGET=REPLACEMENT)
        for override_spec in getattr(args, 'overrides', []):
            if '=' not in override_spec:
                print("Error: --override requires TARGET=REPLACEMENT format", file=sys.stderr)
                return 1
            target, replacement = override_spec.split('=', 1)
            builder.addOverride(target.strip(), replacement.strip())

        runner = TaskSetRunner(rundir, builder=builder, backend=backend)
        runner.base_rundir = base_rundir

        # Initialize cache providers from DV_FLOW_CACHE environment variable
        runner.cache_providers = load_cache_providers()
        runner.hash_registry = rgy
        
        if runner.cache_providers:
            self._log.info(f"Cache enabled with {len(runner.cache_providers)} provider(s)")

        if args.j != -1:
            runner.nproc = int(args.j)
        
        # Wire up force_run from CLI
        if getattr(args, 'force', False):
            runner.force_run = True

        if not os.path.isdir(os.path.join(rundir, "log")):
            os.makedirs(os.path.join(rundir, "log"))
        
        fp = open(os.path.join(rundir, "log", "%s.trace.json" % pkg.name), "w")
        trace = TaskListenerTrace(fp)

        # Pass verbose flag to listener
        listener.verbose = getattr(args, 'verbose', False)

        runner.add_listener(listener.event)
        runner.add_listener(trace.event)

        # Optionally set up the diagnostics report bundle. The report reads
        # per-task data from the on-disk exec_data.json each task writes to the
        # shared rundir, so it works for any execution backend (local, daemon,
        # or remote runners such as LSF).
        report = None
        report_dir = getattr(args, "report_dir", None)
        if report_dir is not None:
            from ..task_listener_report import TaskListenerReport
            report = TaskListenerReport(rundir=rundir, root_name=pkg.name)
            runner.add_listener(report.event)

        tasks = []
        resolved_tasks = []

        for spec in args.tasks:
            try:
                resolved_task = resolver.resolve(spec)
                # Hold this node's contract checks until `--needs` is wired --
                # its need-set is not final until then.
                builder.deferCheckFor(resolved_task.name)
                if getattr(resolved_task, 'select_partial', None):
                    # A partial cell key (`sim-img.prof`). The axis bindings live
                    # on the resolved task and would be lost by re-resolving from
                    # its name, so the builder takes the task itself.
                    task = builder.mkSelectPartialNode(resolved_task)
                else:
                    task = builder.mkTaskNode(resolved_task.name)
                rc = self._wire_cli_needs(args, builder, resolver, task)
                if rc is not None:
                    return rc
                builder.flushDeferredChecks()
                tasks.append(task)
                resolved_tasks.append(resolved_task)
            except TaskResolutionError as e:
                print("Error: %s" % str(e), file=sys.stderr)
                return 1
            except Exception as e:
                print("Error: %s" % str(e), file=sys.stderr)
                return 1

        if any(m.severity == SeverityE.Error for m in build_markers):
            print("Error(s) encountered while building the task graph",
                  file=sys.stderr)
            return 1

        # The graph is now built, so every -D key that was going to bind has
        # bound. Report the ones that did not, and the ones that bound in two
        # namespaces at once. Diagnostics only -- binding semantics and exit
        # status are unchanged.
        for msg in override_tracker.warnings():
            print("Warning: %s" % msg, file=sys.stderr)

        asyncio.run(runner.run(tasks))

        trace.close()
        fp.close()

        # End-of-run summary. Post-run and node-graph-based, so it renders the
        # same under every UI -- including the piped/CI runs that previously got
        # nothing because the panel lived in the progress listener.
        summary_md = self._emit_summary(args, tasks, resolved_tasks, runner,
                                        want_markdown=(report is not None))

        if report is not None:
            report.generate(report_dir, generated_unix=int(time.time()),
                            summary_md=summary_md)
            print("Wrote run report to %s" % report_dir)

        return runner.status

    def _wire_cli_needs(self, args, builder, resolver, node):
        """Wire `--needs TASK` onto the invoked task's node.

        A command-line need is the same edge as one written in `needs:`, so it
        resolves through the same name resolver (partial names and select cell
        keys included) and is ADDITIVE -- it never replaces what the task
        declares.

        Returns an exit status to return immediately, or None to carry on.
        """
        specs = getattr(args, "needs", None) or []
        if not specs:
            return None

        for spec in specs:
            try:
                need_task = resolver.resolve(spec)
            except TaskResolutionError as e:
                print("Error: --needs %s: %s" % (spec, e), file=sys.stderr)
                return 1
            try:
                if getattr(need_task, 'select_partial', None):
                    need_node = builder.mkSelectPartialNode(need_task)
                else:
                    need_node = builder.mkTaskNode(need_task.name)
            except Exception as e:
                print("Error: --needs %s: %s" % (spec, e), file=sys.stderr)
                return 1

            node.needs.append((need_node, False))
            # A compound consumes through `input`, not `needs` -- the same
            # distinction that made deferred cell needs invisible to a compound
            # body. Without this, `--needs` on a compound root would be accepted
            # and silently do nothing.
            if getattr(node, 'input', None) is not None:
                node.input.needs.append((need_node, False))

        return None

    def _parse_package_args(self, args, resolver, pkg, loader):
        """Phase 2a: consume the PROJECT's flags out of the leftover tokens.

        Returns `(exit-status-or-None, {variable: value})`. Whatever is left
        after this is the task's own arguments.

        **A flag the invoked task also claims belongs to the task.** Both are
        legitimate declarations and neither site can see the other, so the rule
        has to be stated once and reported: the task's parameter is the more
        specific answer, and the package variable stays reachable as
        `-D <name>=<value>`.
        """
        from ..cli_args import (collect_package_cli, resolve_task_cli,
                                parse_task_args, validate_package_cli)

        leftover = list(getattr(args, "task_args", []) or [])
        pkg_args = collect_package_cli(pkg, loader)
        if not pkg_args:
            return None, {}

        # Load-time validation has no natural home for a package-level flag (it
        # is not attached to a task), so it runs here -- still before anything
        # is built, and reported the same way.
        problems = []
        validate_package_cli(pkg, loader, problems.append)
        if problems:
            for msg in problems:
                print("Error: %s" % msg, file=sys.stderr)
            return 1, {}

        try:
            task = resolver.resolve(args.task)
        except TaskResolutionError:
            # Reported by the task-args phase, with its suggestions.
            return None, {}

        task_flags = {a.name for a in resolve_task_cli(task)}
        shadowed = [a for a in pkg_args if a.name in task_flags]
        for a in shadowed:
            print("Warning: --%s is declared by both task '%s' and a package "
                  "variable; the task parameter wins. Set the package variable "
                  "with -D %s=<value>." % (a.name, task.name, a.param),
                  file=sys.stderr)
        pkg_args = [a for a in pkg_args if a.name not in task_flags]
        if not pkg_args:
            return None, {}

        # `parse_known_args` semantics: take what the project declares and hand
        # the rest on. An unknown flag is the TASK parser's to reject, since it
        # is the one that can say what the task accepts.
        values, remaining = parse_task_args(
            pkg, pkg_args, leftover, "dfm run", partial=True)
        args.task_args = remaining
        return None, values

    def _resolved_defaults(self, task, pkg, loader, overrides):
        """`{param: value}` for the help view, with `${{ }}` defaults evaluated.

        A display-only convenience: a failure here must degrade to showing the
        raw expression, never break `--help`. The throwaway builder constructs
        no nodes (see `resolveTaskParams`), so this costs a parameter-type build.
        """
        if pkg is None or loader is None:
            return None
        try:
            from ..task_graph_builder import TaskGraphBuilder
            b = TaskGraphBuilder(
                root_pkg=pkg,
                rundir=os.path.join(os.getcwd(), "rundir"),
                loader=loader,
                task_param_overrides=(overrides or {}).get('task', {}),
                leaf_param_overrides=(overrides or {}).get('leaf', {}))
            return b.resolveTaskParams(task)
        except Exception as e:
            self._log.debug("could not resolve defaults for %s: %s", task.name, e)
            return None

    def _parse_task_args(self, args, resolver, task_overrides,
                         pkg=None, loader=None, overrides=None):
        """Phase 2 of the `run` parse: bind the task's own `--flags`.

        Returns an exit status to return immediately (`--help`, a bad task
        name), or None to carry on with the run.
        """
        from ..cli_args import (resolve_task_cli, parse_task_args,
                                build_arg_parser, collect_package_cli)

        try:
            task = resolver.resolve(args.task)
        except TaskResolutionError as e:
            print("Error: %s" % str(e), file=sys.stderr)
            return 1

        cli_args = resolve_task_cli(task)
        prog = "dfm run %s" % task.name
        leftover = list(getattr(args, "task_args", []) or [])

        # Project-level flags are consumed before this point, but they belong in
        # the help: from the command line they are indistinguishable from the
        # task's own, so listing only half of what `dfm run <task>` accepts
        # would be actively misleading.
        pkg_args = [a for a in collect_package_cli(pkg, loader)
                    if not a.hidden and a.name not in {c.name for c in cli_args}]

        if getattr(args, "task_help", False):
            # `dfm run <task> --help` is the task's argument help, not dfm's.
            from .show.usage import render_usage
            values = self._resolved_defaults(task, pkg, loader, overrides)
            render_usage(task, prog="dfm run", values=values)
            if cli_args:
                print()
                arg_parser, _ = build_arg_parser(task, cli_args, prog, values=values)
                arg_parser.print_help()
            if pkg_args:
                print()
                print("Project options (apply to any task in %s):" % pkg.name)
                for a in pkg_args:
                    flags = "--%s" % a.name
                    if a.short:
                        flags = "-%s, %s" % (a.short, flags)
                    line = "  %-20s %s" % (flags, a.help or "")
                    default = getattr(a.pdef, 'value', None)
                    if default not in (None, ''):
                        line += " (default: %s)" % default
                    print(line.rstrip())
            return 0

        if not cli_args:
            if leftover:
                hint = ("Set parameters with -D name=value, or mark a parameter "
                        "`cli: true` in its declaration.")
                if pkg_args:
                    hint = ("This project accepts: %s. Otherwise set parameters "
                            "with -D name=value, or mark a parameter `cli: true` "
                            "in its declaration." % ", ".join(
                                "--%s" % a.name for a in pkg_args))
                print("Error: task '%s' accepts no arguments, but got: %s\n%s" % (
                    task.name, " ".join(leftover), hint), file=sys.stderr)
                return 1
            return None

        values = parse_task_args(task, cli_args, leftover, prog)

        # Bind through the override map (design §4.4 option (a)), NOT as
        # mkTaskNode kwargs: kwargs are applied *before* the override pass, so a
        # `-D` would silently win over an explicit `--flag`. Keyed on the
        # resolved FULL task name only -- the override map also matches leaf
        # names, so a leaf-keyed entry would leak this root's flag into any
        # nested task sharing that leaf name.
        if values:
            task_overrides.setdefault(task.name, {}).update(values)

        return None

    def _emit_summary(self, args, nodes, resolved_tasks, runner, want_markdown=False):
        """Render the end-of-run summary to the console and, if asked, to a file.

        Returns the summary as markdown when `want_markdown` (for the --report
        bundle), else None. A failure anywhere in here is reported and swallowed:
        a summary is a presentation concern and must not change the run's verdict.
        """
        from ..summary_ctxt import (
            SummaryCtxt, resolve_task_summary, invoke_summary, summary_file_text,
            BUILTIN_TASK_SUMMARY)

        if not nodes:
            return None

        # A *declared* summary belongs to a single invoked root -- with several
        # roots there is no one declaration to honor. `run` now takes exactly
        # one task, so this holds in practice; the length test stays because
        # `tasks` is still a list and other entry points (the daemon protocol)
        # can supply several.
        decl = None
        if len(resolved_tasks) == 1:
            decl = resolve_task_summary(resolved_tasks[0])
        if decl is None:
            decl = BUILTIN_TASK_SUMMARY

        ctxt = SummaryCtxt(
            root=nodes[0],
            status=runner.status,
            roots=list(nodes),
            verbose=getattr(args, 'verbose', False),
            cache_enabled=bool(getattr(runner, 'cache_providers', None)))

        try:
            value = invoke_summary(decl, ctxt)
        except Exception as e:
            self._log.error("Failed to build summary: %s" % e)
            return None

        if value is not None and not getattr(args, 'no_summary', False):
            self._print_summary(value)

        summary_file = getattr(args, 'summary_file', None)
        if summary_file is not None:
            # Independent of --no-summary: "silence the console, write the file"
            # is a real CI configuration.
            try:
                text = summary_file_text(
                    decl, ctxt, value, markdown=summary_file.endswith(".md"))
                if text is not None:
                    with open(summary_file, "w") as f:
                        f.write(text)
            except Exception as e:
                self._log.error("Failed to write summary file %s: %s" % (
                    summary_file, e))

        if want_markdown:
            try:
                return summary_file_text(decl, ctxt, value, markdown=True)
            except Exception as e:
                self._log.error("Failed to render summary for the report: %s" % e)
        return None

    def _print_summary(self, value):
        if isinstance(value, str):
            print(value)
            return
        from rich.console import Console
        # A non-tty Console emits no ANSI, so piped output stays clean.
        Console().print(value)
