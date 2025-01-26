import asyncio
import os
import logging
from typing import ClassVar
from ..task_graph_runner import TaskGraphRunner
from ..util import loadProjPkgDef
from ..task_graph_builder import TaskGraphBuilder
from ..task_graph_runner_local import TaskGraphRunnerLocal
from ..pkg_rgy import PkgRgy


class CmdRun(object):
    _log : ClassVar = logging.getLogger("CmdRun")

    def __call__(self, args):

        # First, find the project we're working with
        pkg = loadProjPkgDef(os.getcwd())

        if pkg is None:
            raise Exception("Failed to find a 'flow.dv' file that defines a package in %s or its parent directories" % os.getcwd())

        self._log.debug("Root flow file defines package: %s" % pkg.name)

        if len(args.tasks) > 0:
            pass
        else:
            # Print out available tasks
            tasks = []
            for task in pkg.tasks:
                tasks.append(task)
            for frag in pkg.fragment_l:
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

            pass

        # Create a session around <pkg>
        # Need to select a backend
        # Need somewhere to store project config data
        # Maybe separate into a task-graph builder and a task-graph runner

        # TODO: allow user to specify run root -- maybe relative to some fixed directory?
        rundir = os.path.join(pkg.basedir, "rundir")

        builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir)
        runner = TaskGraphRunnerLocal(rundir)

        tasks = []

        for spec in args.tasks:
            if spec.find('.') == -1:
                spec = pkg.name + "." + spec
            task = builder.mkTaskGraph(spec)
            tasks.append(task)

        asyncio.run(runner.run(tasks))

#        rgy = PkgRgy.inst()
#        rgy.registerPackage(pkg)


        # srcdir = os.getcwd()

        # session = Session(srcdir, rundir)

        # package = session.load(srcdir)

        # graphs = []
        # for task in args.tasks:
        #     if task.find(".") == -1:
        #         task = package.name + "." + task
        #     subgraph = session.mkTaskGraph(task)
        #     graphs.append(subgraph)

        # awaitables = [subgraph.do_run() for subgraph in graphs]
        # print("%d awaitables" % len(awaitables))

        # out = asyncio.get_event_loop().run_until_complete(asyncio.gather(*awaitables))

        # print("out: %s" % str(out))

