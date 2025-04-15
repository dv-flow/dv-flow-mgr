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

def test_smoke_ext_need(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: ext
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
        needs: [create_file, ext]
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

def test_nested_task(tmpdir):
    flow_dv = """
package:
    name: foo

    tasks:
    - name: nested
      body:
      - name: create_file_i
        rundir: inherit
        uses: std.CreateFile
        with:
          filename: hello.txt
          content: |
            Hello World
      - name: glob_txt_i
        rundir: inherit
        uses: std.FileSet
        needs: [create_file_i]
        passthrough: none
        with:
          base: ${{ rundir }}
          include: "*.txt"
          type: textFile

    - name: entry
      body:
      - name: create_file
        rundir: inherit
        uses: std.CreateFile
        with:
          filename: hello.txt
          content: |
            Hello World
      - name: N1
        uses: nested
        needs: [create_file]
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
    assert len(output.output) == 2
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1
