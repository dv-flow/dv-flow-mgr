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
import asyncio
import os
import logging
import toposort
from typing import ClassVar
from ..util import loadProjPkgDef
from ..task_graph_builder import TaskGraphBuilder
from ..task_runner import TaskSetRunner
from ..task_listener_log import TaskListenerLog
from ..task_graph_dot_writer import TaskGraphDotWriter


class CmdShow(object):
    _log : ClassVar = logging.getLogger("CmdGraph")

    def __call__(self, args):

        # First, find the project we're working with
        pkg = loadProjPkgDef(os.getcwd())

        if pkg is None:
            raise Exception("Failed to find a 'flow.dv' file that defines a package in %s or its parent directories" % os.getcwd())

        self._log.debug("Root flow file defines package: %s" % pkg.name)

        if args.task is None:
            # Print out available tasks
            tasks = []
            for task in pkg.task_m.values():
                tasks.append(task)
            for frag in pkg.fragment_def_l:
                for task in frag.tasks:
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
        else:
            rundir = os.path.join(pkg.basedir, "rundir")

            builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)


            if args.all:
                t = builder.mkTaskNode(pkg.name + "." + args.task)
                dep_m = TaskSetRunner(rundir=None).buildDepMap(t)

                order = list(toposort.toposort(dep_m))

                print("Task: %s" % t.name)

                last_s = set()
                for i,s in enumerate(order):
                    print("-- TaskSet %d --" % (i+1))
                    for t in s:
                        print("  - %s" % t.name)
                        if args.verbose and len(t.params.model_fields.items()):
                            print("    params:")
                            for name,field in t.params.model_fields.items():
                                print("    - %s: %s" % (name, getattr(t.params, name)))
                        if len(t.needs):
                            print("    needs:")
                            for n in t.needs:
                                print("    - %s%s" % (
                                    n[0].name,
                                    ("*" if n[0] in last_s else "")))
                    last_s = s
                        
                pass
            else:
                # Show show info about the current task
                pass

        return 0


