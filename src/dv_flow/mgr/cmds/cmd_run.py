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
from typing import ClassVar
from ..util import loadProjPkgDef
from ..task_data import SeverityE
from ..task_graph_builder import TaskGraphBuilder
from ..task_runner import TaskSetRunner
from ..task_listener_log import TaskListenerLog


class CmdRun(object):
    _log : ClassVar = logging.getLogger("CmdRun")

    def __call__(self, args):
        if args.root is not None:
            rootdir = args.root
        elif "DV_FLOW_ROOT" in os.environ.keys():
            rootdir = os.environ["DV_FLOW_ROOT"]
        else:
            rootdir = os.getcwd()

        # First, find the project we're working with
        listener = TaskListenerLog()
        pkg = loadProjPkgDef(rootdir, listener=listener.marker)

        if listener.has_severity[SeverityE.Error] > 0:
            print("Error(s) encountered while loading package definition")
            return 1

        if pkg is None:
            raise Exception("Failed to find a 'flow.dv' file that defines a package in %s or its parent directories" % os.getcwd())

        self._log.debug("Root flow file defines package: %s" % pkg.name)

        if len(args.tasks) > 0:
            pass
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

        builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
        runner = TaskSetRunner(rundir, builder=builder)

        if args.j != -1:
            runner.nproc = int(args.j)

        runner.add_listener(listener.event)

        tasks = []

        for spec in args.tasks:
            if spec.find('.') == -1:
                spec = pkg.name + "." + spec
            task = builder.mkTaskNode(spec)
            tasks.append(task)

        asyncio.run(runner.run(tasks))

        return runner.status


