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
import sys
from typing import ClassVar
from ..ext_rgy import ExtRgy
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..task_data import SeverityE
from ..task_graph_builder import TaskGraphBuilder
from ..task_runner import TaskSetRunner
from ..task_listener_log import TaskListenerLog
from ..task_listener_tui import TaskListenerTui
from ..task_listener_progress import TaskListenerProgress
from ..task_listener_trace import TaskListenerTrace
from .util import get_rootdir


class CmdRun(object):
    _log : ClassVar = logging.getLogger("CmdRun")

    def __call__(self, args):

        rgy = ExtRgy.inst()

        # Determine which console listener to use
        ui = getattr(args, 'ui', None)
        if ui is None:
            # Auto-select based on whether output is a terminal
            ui = 'progress' if sys.stdout.isatty() else 'log'

        # If user explicitly requested 'progress' but stdout isn't a TTY, fallback
        explicit = getattr(args, 'ui', None) is not None
        if ui == 'progress' and not sys.stdout.isatty():
            if explicit:
                print("Note: 'progress' UI requested but stdout is not a terminal. Falling back to 'log' UI.")
            ui = 'log'

        listener = TaskListenerLog()

        # First, find the project we're working with using selected listener for load markers
        loader, pkg = loadProjPkgDef(
            get_rootdir(args),
            listener=listener.marker,
            parameter_overrides=parse_parameter_overrides(getattr(args, "param_overrides", [])))

        if listener.has_severity[SeverityE.Error] > 0:
            print("Error(s) encountered while loading package definition")
            sys.exit(1)

        if pkg is None:
            raise Exception("Failed to find a 'flow.dv' file that defines a package in %s or its parent directories" % os.getcwd())

        assert loader is not None
        self._log.debug("Root flow file defines package: %s" % pkg.name)

        if len(args.tasks) > 0:
            pass
            if ui == 'log':
                listener = TaskListenerLog()
            elif ui == 'progress':
                listener = TaskListenerProgress()
            elif ui == 'tui':
                listener = TaskListenerTui()
            else:
                if explicit:
                    print(f"Unknown UI '{ui}'. Falling back to log.")
                listener = TaskListenerLog()
        else:
            # Print out available tasks
            tasks = []
            for task in pkg.task_m.values():
                tasks.append(task)
            tasks.sort(key=lambda x: x.name)

            max_name_len = 0
            for t in tasks:
                if len(t.name) > max_name_len:
                    max_name_len = len(t.name)

            print("No task specified. Available Tasks:")
            for t in tasks:
                desc = t.desc
                if desc is None or t.desc == "":
                    "<no descripion>"
                print("%s - %s" % (t.name.ljust(max_name_len), desc))

            pass

        # Create a session around <pkg>
        # Need to select a backend
        # Need somewhere to store project config data
        # Maybe separate into a task-graph builder and a task-graph runner

        # TODO: allow user to specify run root -- maybe relative to some fixed directory?
        rundir = os.path.join(pkg.basedir, "rundir")


        if args.clean:
            print("Note: Cleaning rundir %s" % rundir)
            if os.path.exists(rundir):
                os.rmdir(rundir)
            os.makedirs(rundir)

        builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
        runner = TaskSetRunner(rundir, builder=builder)

        if args.j != -1:
            runner.nproc = int(args.j)

        if not os.path.isdir(os.path.join(rundir, "log")):
            os.makedirs(os.path.join(rundir, "log"))
        
        fp = open(os.path.join(rundir, "log", "%s.trace.json" % pkg.name), "w")
        trace = TaskListenerTrace(fp)

        runner.add_listener(listener.event)
        runner.add_listener(trace.event)

        tasks = []

        for spec in args.tasks:
            if spec.find('.') == -1:
                spec = pkg.name + "." + spec
            task = builder.mkTaskNode(spec)
            tasks.append(task)

        asyncio.run(runner.run(tasks))

        trace.close()
        fp.close()

        return runner.status
