"""
Test suite for documentation examples in userguide/tasks_using.rst
"""
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestTasksUsingExamples:
    """Test examples from tasks_using.rst"""
    
    def test_conditional_task_iff(self, tmpdir):
        """Test conditional task execution with iff"""
        flowdv = """
package:
  name: my_ip
  with:
    debug_level:
      type: int
      value: 0
  
  tasks:
  - name: SimOptions
    uses: std.Message
    body:
    - name: SimOptionsDebug
      uses: std.Message
      iff: ${{ debug_level > 0 }}
      with:
        msg: "Debug mode enabled"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("my_ip.SimOptions")
        
        assert task is not None
    
    def test_task_override(self, tmpdir):
        """Test task override mechanism"""
        flowdv = """
package:
  name: my_project
  
  tasks:
  - name: sim
    uses: std.Message
    with:
      msg: "Normal simulation"
  
  - name: sim_debug
    override: sim
    with:
      msg: "Debug simulation"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        
        # Check that override is registered
        assert "sim" in pkg.task_m
        assert "sim_debug" in pkg.task_m
    
    def test_consumes_pattern(self, tmpdir):
        """Test consumes pattern matching"""
        flowdv = """
package:
  name: test_consumes
  
  tasks:
  - name: sources
    uses: std.FileSet
    with:
      include: "*.sv"
      type: systemVerilogSource
  
  - name: compile
    uses: std.Message
    needs: [sources]
    consumes:
    - type: std.FileSet
    with:
      msg: "Compiling"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("test_consumes.compile")
        
        assert task is not None
    
    def test_passthrough_modes(self, tmpdir):
        """Test passthrough parameter"""
        flowdv = """
package:
  name: test_passthrough
  
  tasks:
  - name: process
    uses: std.Message
    passthrough: all
    with:
      msg: "Processing"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("test_passthrough.process")
        
        assert task is not None
    
    def test_rundir_unique(self, tmpdir):
        """Test unique rundir mode"""
        flowdv = """
package:
  name: test_rundir
  
  tasks:
  - name: task1
    rundir: unique
    uses: std.Message
    with:
      msg: "Unique directory"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("test_rundir.task1")
        
        assert task is not None
        assert task.rundir_mode.value == "unique"
    
    def test_rundir_inherit(self, tmpdir):
        """Test inherit rundir mode with compound task"""
        flowdv = """
package:
  name: test_inherit
  
  tasks:
  - name: CreateTestFiles
    rundir: inherit
    body:
    - name: create_file1
      uses: std.CreateFile
      with:
        filename: test1.txt
        type: text
        content: "Test file 1"
    
    - name: create_file2
      uses: std.CreateFile
      with:
        filename: test2.txt
        type: text
        content: "Test file 2"
    
    - name: gather
      uses: std.FileSet
      needs: [create_file1, create_file2]
      with:
        include: "*.txt"
        type: text
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("test_inherit.CreateTestFiles")
        
        assert task is not None


@pytest.mark.asyncio
async def test_dataitem_task(tmpdir):
    """Test DataItem task usage"""
    flowdv = """
package:
  name: dataitem_test
  
  types:
  - name: SimOptions
    with:
      trace:
        type: bool
        value: false
  
  tasks:
  - name: sim_opts
    uses: SimOptions
    with:
      trace: true
  
  - name: use_opts
    uses: std.Message
    needs: [sim_opts]
    with:
      msg: "Using simulation options"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("dataitem_test.use_opts")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_compound_task_execution(tmpdir):
    """Test compound task with body"""
    flowdv = """
package:
  name: compound_test
  
  tasks:
  - name: parent
    body:
    - name: child1
      uses: std.Message
      with:
        msg: "Child 1"
    - name: child2
      uses: std.Message
      needs: [child1]
      with:
        msg: "Child 2"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("compound_test.parent")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0
