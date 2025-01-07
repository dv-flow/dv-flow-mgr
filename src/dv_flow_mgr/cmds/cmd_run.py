import asyncio
import os
from ..session import Session

class CmdRun(object):

    def __call__(self, args):
        srcdir = os.getcwd()
        rundir = os.path.join(srcdir, "rundir")

        session = Session(srcdir, rundir)

        package = session.load(srcdir)

        graphs = []
        for task in args.tasks:
            if task.find(".") == -1:
                task = package.name + "." + task
            subgraph = session.mkTaskGraph(task)
            graphs.append(subgraph)

        awaitables = [subgraph.do_run() for subgraph in graphs]
        out = asyncio.gather(*awaitables)

