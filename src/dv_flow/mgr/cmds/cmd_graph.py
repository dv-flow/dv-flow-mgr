#****************************************************************************
#* cmd_graph.py
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
import io
import json
import os
import logging
from typing import ClassVar
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..task_graph_builder import TaskGraphBuilder
from ..task_runner import TaskSetRunner
from ..task_listener_log import TaskListenerLog
from ..task_graph_dot_writer import TaskGraphDotWriter
from .util import get_rootdir

# Markers for programmatic extraction of graph content
DFM_GRAPH_BEGIN = "<<<DFM_GRAPH_BEGIN>>>"
DFM_GRAPH_END = "<<<DFM_GRAPH_END>>>"


class CmdGraph(object):
    _log : ClassVar = logging.getLogger("CmdGraph")

    def __call__(self, args):

        # First, find the project we're working with
        loader, pkg = loadProjPkgDef(
            get_rootdir(args),
            parameter_overrides=parse_parameter_overrides(getattr(args, "param_overrides", [])),
            config=getattr(args, "config", None))

        if pkg is None:
            raise Exception("Failed to find a 'flow.dv/flow.yaml/flow.toml' file that defines a package in %s or its parent directories" % os.getcwd())

        self._log.debug("Root flow file defines package: %s" % pkg.name)

        if args.task is None:
            # Print out available tasks
            tasks = []
            for task in pkg.task_m.values():
                tasks.append(task)
#            for frag in pkg._fragment_l:
#                for task in frag.tasks:
#                    tasks.append(task)
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

            builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)

            for pref in ("", "%s." % pkg.name):
                name = "%s%s" % (pref, args.task)
                task = builder.findTask(name)
                if task is not None:
                    break

            if task is None:
                raise Exception("Task '%s' not found in package '%s'" % (args.task, pkg.name))

            t = builder.mkTaskNode(task.name)

            output = getattr(args, "output", "-")
            if output is None:
                output = "-"

            use_json = getattr(args, "json", False)
            
            if use_json:
                # Capture DOT output to string for JSON wrapping
                dot_buffer = io.StringIO()
                TaskGraphDotWriter(show_params=getattr(args, "show_params", False)).write(
                    t,
                    dot_buffer
                )
                dot_content = dot_buffer.getvalue()
                
                # Output with markers for easy extraction
                result = {
                    "graph": dot_content
                }
                json_output = f"{DFM_GRAPH_BEGIN}\n{json.dumps(result)}\n{DFM_GRAPH_END}"
                
                if output == "-":
                    print(json_output)
                else:
                    with open(output, 'w') as f:
                        f.write(json_output)
            else:
                TaskGraphDotWriter(show_params=getattr(args, "show_params", False)).write(
                    t,
                    output
                )

        return 0
