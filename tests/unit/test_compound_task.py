import asyncio
import json
import os
import pytest
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

def test_parameter_compound_leaf_dflt(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: entry
      with:
        p1:
          type: str
          value: "v1"
      body:
      - name: t1
        shell: pytask
        run: task.py::Task
        with:
          p1: 
            type: str
            value: "${{ this.p1 }}"
"""
    task_py = """
import os
from dv_flow.mgr import TaskDataResult

async def Task(ctxt, input):
    with open(os.path.join(ctxt.rundir, "task.out"), "w") as fp:
      fp.write("p1: %s" % input.params.p1)
      return TaskDataResult()
"""
    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "task.py"), "w") as fp:
        fp.write(task_py)

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
    assert os.path.isfile(os.path.join(rundir, "rundir/foo.entry/foo.entry.t1/task.out"))
    with open(os.path.join(rundir, "rundir/foo.entry/foo.entry.t1/task.out"), "r") as fp:
        line = fp.read().strip()
        assert line == "p1: v1"

def test_parameter_compound_leaf_ref_parent(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: entry
      with:
        p1:
          type: str
          value: "v1"
      body:
      - name: t1
        shell: pytask
        run: task.py::Task
        with:
          p2: 
            type: str
            value: "${{ this.p1 }}"
"""
    task_py = """
import os
from dv_flow.mgr import TaskDataResult

async def Task(ctxt, input):
    with open(os.path.join(ctxt.rundir, "task.out"), "w") as fp:
      fp.write("p2: %s" % input.params.p2)
      return TaskDataResult()
"""
    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "task.py"), "w") as fp:
        fp.write(task_py)

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
    assert os.path.isfile(os.path.join(rundir, "rundir/foo.entry/foo.entry.t1/task.out"))
    with open(os.path.join(rundir, "rundir/foo.entry/foo.entry.t1/task.out"), "r") as fp:
        line = fp.read().strip()
        assert line == "p2: v1"

@pytest.mark.skip
def test_compound_need(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: file1
      uses: std.CreateFile
      with:
        filename: file1.tst
        content: |
          file1
        type: textFile
    - name: file2
      uses: std.CreateFile
      with:
        filename: file2.tst
        content: |
          file2
        type: textFile
    - name: file3
      uses: std.CreateFile
      with:
        filename: file3.tst
        content: |
          file3
        type: textFile
    - name: Compound1
      needs: [file1, file2, file3]
      body:
      - name: Init
        shell: pytask
        run: |
          with open(os.path.join(input.rundir, "init.txt"), "w") as fp:
            fp.write("%d inputs\\n" % len(input.inputs))
          return TaskDataResult(status=0)
    - name: entry
      needs: [Compound1]
      body:
      - name: Sub
        shell: pytask
        run: |
          with open("sub.txt", "w") as fp:
            fp.write("%d inputs\\n" % len(input.inputs))
          return TaskDataResult(status=0)
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    for m in collector.markers:
        print("Marker: %s" % m.msg)
    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    # TaskGraphDotWriter().write(
    #     t1, 
    #     os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    for out in output.output:
        print("Out: %s" % str(out))
    assert len(output.output) == 1
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

@pytest.mark.skip
def test_compound_need_inh(tmpdir):
    pkg_dv = """
package:
  name: pkg
  tasks:
  - name: Compound1
    body:
    - name: Init
      shell: pytask
      run: |
        with open("init.txt", "w") as fp:
          fp.write("%d inputs\\n" % len(input.inputs))
        return TaskDataResult(status=0)
  - name: entry
    body:
    - name: Sub
      shell: pytask
      run: |
        with open("sub.txt", "w") as fp:
          fp.write("%d inputs\\n" % len(input.inputs))
        return TaskDataResult(status=0)
"""
    flow_dv = """
package:
    name: foo
    imports:
    - pkg.dv

    tasks:
    - name: file1
      uses: std.CreateFile
      with:
        filename: file1.tst
        content: |
          file1
        type: textFile
    - name: file2
      uses: std.CreateFile
      with:
        filename: file2.tst
        content: |
          file2
        type: textFile
    - name: file3
      uses: std.CreateFile
      with:
        filename: file3.tst
        content: |
          file3
        type: textFile
    - name: Compound1
      uses: pkg.Compound1
      needs: [file1, file2, file3]
    - name: entry
      uses: pkg.entry
      needs: [Compound1]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "pkg.dv"), "w") as fp:
        fp.write(pkg_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    for m in collector.markers:
        print("Marker: %s" % m.msg)
    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    # TaskGraphDotWriter().write(
    #     t1, 
    #     os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    for out in output.output:
        print("Out: %s" % str(out))
    assert len(output.output) == 1
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

@pytest.mark.skip
def test_compound_need_inh_src(tmpdir):
    pkg_dv = """
package:
  name: pkg
  tasks:
  - name: Compound1
    body:
    - name: Init
      shell: pytask
      run: |
        with open(os.path.join(input.rundir, "init.txt"), "w") as fp:
          fp.write("%d inputs\\n" % len(input.inputs))
        return TaskDataResult(status=0)
  - name: entry
    body:
    - name: Sub
      shell: pytask
      run: |
        with open(os.path.join(input.rundir, "sub.txt"), "w") as fp:
          fp.write("%d inputs\\n" % len(input.inputs))
        return TaskDataResult(status=0)
"""
    flow_dv = """
package:
    name: foo
    imports:
    - pkg.dv

    tasks:
    - name: file1
      uses: std.FileSet
      with:
        type: textFile
        base: ${{ srcdir }}
        include: file1.txt
    - name: Compound1
      uses: pkg.Compound1
      needs: [file1]
    - name: entry
      uses: pkg.entry
      needs: [Compound1]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "pkg.dv"), "w") as fp:
        fp.write(pkg_dv)
    with open(os.path.join(rundir, "file1.txt"), "w") as fp:
        fp.write("file1.txt\n")

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    for m in collector.markers:
        print("Marker: %s" % m.msg)
    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    # TaskGraphDotWriter().write(
    #     t1, 
    #     os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    for out in output.output:
        print("Out: %s" % str(out))
    assert len(output.output) == 1
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

def test_compound_srcdir_ref(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: entry
      body:
      - name: t1
        rundir: inherit
        shell: bash
        run: |
          echo "srcdir: ${{ srcdir }}" > file1.txt
      - name: t2
        rundir: inherit
        needs: [t1]
        uses: std.FileSet
        with:
          type: textFile
          base: ${{ rundir }}
          include: "*.txt"

"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    for m in collector.markers:
        print("Marker: %s" % m.msg)
    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="entry")

    # TaskGraphDotWriter().write(
    #     t1, 
    #     os.path.join(rundir, "graph.dot"))

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    for out in output.output:
        print("Out: %s" % str(out))
    assert len(output.output) == 1
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1

    with open(os.path.join(output.output[0].basedir, output.output[0].files[0]), "r") as fp:
        content = fp.read().strip()
        assert content.find("srcdir:") != -1
        path = content[content.find(":")+1:].strip()
        assert path == str(tmpdir)
