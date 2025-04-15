import asyncio
import json
import os
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter
from .marker_collector import MarkerCollector

def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: entry
      body:
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
        passthrough: none
        with:
          base: ${{ rundir }}
          include: "*.txt"
          type: textFile
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    for out in output.output:
        print("Out: %s" % str(out))
    assert len(output.output) == 1
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

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
        passthrough: none
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
      passthrough: all
      consumes: none
      needs: [Task1, Task2]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

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

    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

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

    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert output is not None

def test_name_resolution_pkg(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: TopLevelTask
      uses: std.CreateFile
      with:
        filename: TopLevelTask.txt
        content: "TopLevelTask.txt"

    - name: entry
      body:
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
        needs: [create_file, TopLevelTask]
        passthrough: none
        with:
          base: ${{ rundir }}
          include: "*.txt"
          type: textFile
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg_def = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(rundir, "flow.dv"))
    assert len(marker_collector.markers) == 0

    print("Package:\n%s\n" % json.dumps(pkg_def.dump(), indent=2))

    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert len(output.output) == 1
    assert output.output[0].src == 'foo.entry.glob_txt'
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

def test_compound_input_auto_bind(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: TopLevelTask
      uses: std.CreateFile
      with:
        filename: TopLevelTask.txt
        content: "TopLevelTask.txt"

    - name: entry
      needs: [TopLevelTask]
      body:
      - name: mytask
        passthrough: all
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg_def = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(rundir, "flow.dv"))
    assert len(marker_collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert len(output.output) == 1
    assert output.output[0].src == 'foo.TopLevelTask'
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

def test_compound_input_auto_bind_consumes_all(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: TopLevelTask
      uses: std.CreateFile
      with:
        filename: TopLevelTask.txt
        content: "TopLevelTask.txt"

    - name: entry
      needs: [TopLevelTask]
      body:
      - name: mytask
        shell: pytask
        run: |
          with open(os.path.join(input.rundir, "mytask.txt"), "w") as fp:
            fp.write("inputs: %d" % len(input.inputs))
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg_def = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(rundir, "flow.dv"))
    assert len(marker_collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    # No output, since the inputting task consumes all
    assert len(output.output) == 0

    assert os.path.isfile(os.path.join(rundir, "rundir/foo.entry/foo.entry.mytask/mytask.txt"))
    content = open(os.path.join(rundir, "rundir/foo.entry/foo.entry.mytask/mytask.txt"), "r").read().strip()
    assert content == "inputs: 1"

def test_compound_input_auto_bind_chain(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: TopLevelTask
      uses: std.CreateFile
      with:
        filename: TopLevelTask.txt
        content: "TopLevelTask.txt"

    - name: entry
      needs: [TopLevelTask]
      body:
      - name: mytask1
        passthrough: all
      - name: mytask2
        passthrough: all
        needs: [mytask1]
      - name: mytask3
        passthrough: all
        needs: [mytask2]
      - name: mytask4
        passthrough: all
        needs: [mytask3]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    marker_collector = MarkerCollector()
    pkg_def = PackageLoader(
        marker_listeners=[marker_collector]).load(
            os.path.join(rundir, "flow.dv"))
    assert len(marker_collector.markers) == 0

    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry")

    TaskGraphDotWriter().write(
        t1, 
        os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert len(output.output) == 1
    assert output.output[0].src == 'foo.TopLevelTask'
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1
