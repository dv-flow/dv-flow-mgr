import asyncio
import os
from dv_flow.mgr import TaskGraphBuilder, TaskRunner, PackageDef

def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: entry
      tasks:
      - name: create_file
        rundir: inherit
        uses: std.CreateFile
        with:
          filename: hello.txt
          content: |
            Hello World
      - name: glob_txt
        rundir: inherit
        uses: std.FileSet
        needs: [create_file]
        with:
          base: ${{ rundir }}
          include: "*.txt"
          type: textFile
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg_def = PackageDef.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskRunner(rundir=os.path.join(rundir, "rundir"))

    task = builder.mkTaskNode("foo.entry")

    output = asyncio.run(runner.run(task))

    pass