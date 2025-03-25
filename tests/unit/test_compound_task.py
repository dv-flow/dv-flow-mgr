import asyncio
import os
from dv_flow.mgr import TaskGraphBuilder, TaskRunner, PackageDef
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter

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

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    pass

def test_smoke_2(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: TaskType1
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
    - name: Task1
      uses: TaskType1

    - name: Task2
      uses: TaskType1

    - name: entry
      needs: [Task1, Task2]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg_def = PackageDef.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    pass

def test_smoke_3(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: TaskType1
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
#        needs: [create_file]
        with:
          base: ${{ rundir }}
          include: "*.txt"
          type: textFile
    - name: Task1
      uses: TaskType1

    - name: Task2
      uses: TaskType1

    - name: entry
      needs: [Task1, Task2]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg_def = PackageDef.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

def test_uses_leaf(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: entry
      uses: std.CreateFile
      rundir: inherit
      with:
        filename: hello.txt
        content: |
          Hello World
      tasks:
        - name: GetFiles
          uses: std.FileSet
          needs: [super]
          with:
            type: textFile
            base: ${{ rundir }}
            include: "*.txt"
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    pkg_def = PackageDef.load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))