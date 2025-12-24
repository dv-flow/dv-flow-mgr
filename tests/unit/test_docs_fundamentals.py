"""
Test suite for documentation examples in userguide/fundamentals.rst
"""
import asyncio
import os
import pytest
import tempfile
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestFundamentalsExamples:
    """Test examples from fundamentals.rst"""
    
    def test_basic_task_with_uses(self, tmpdir):
        """Test basic task with uses and parameters"""
        flowdv = """
package:
  name: p1
  tasks:
    - name: SayHello
      uses: std.Message
      with:
        msg: "Hello World!"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert pkg.name == "p1"
        assert "p1.SayHello" in pkg.task_m
        
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("p1.SayHello")
        assert task is not None
    
    def test_dataflow_example(self, tmpdir):
        """Test basic dataflow with FileSet and needs"""
        flowdv = """
package:
  name: p1
  tasks:
    - name: rtl_files
      uses: std.FileSet
      with:
        base: "src/rtl"
        include: "*.sv"
        type: systemVerilogSource
    - name: sim
      uses: std.Message
      needs: [rtl_files]
      with:
        msg: "Building simulation"
"""
        rundir = str(tmpdir)
        os.makedirs(os.path.join(rundir, "src/rtl"))
        
        # Create some test files
        with open(os.path.join(rundir, "src/rtl/test1.sv"), "w") as f:
            f.write("module test1; endmodule")
        with open(os.path.join(rundir, "src/rtl/test2.sv"), "w") as f:
            f.write("module test2; endmodule")
        
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("p1.sim")
        
        assert task is not None
        assert len(task.needs) == 1
    
    def test_type_definition(self, tmpdir):
        """Test custom type definition"""
        flowdv = """
package:
  name: my_types
  
  types:
  - name: CompilerOptions
    with:
      optimization:
        type: str
        value: "-O2"
      warnings:
        type: list
        value: []
  
  - name: DebugOptions
    uses: CompilerOptions
    with:
      debug_level:
        type: int
        value: 0
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert "CompilerOptions" in pkg.type_m
        assert "DebugOptions" in pkg.type_m
        
        # Check inheritance
        debug_type = pkg.type_m["DebugOptions"]
        assert debug_type.uses is not None
        assert debug_type.uses.name == "my_types.CompilerOptions"
    
    def test_expression_syntax(self, tmpdir):
        """Test expression evaluation"""
        flowdv = """
package:
  name: my_pkg
  with:
    debug:
      type: bool
      value: false
    optimization:
      type: str
      value: "O2"
  
  tasks:
  - name: compile
    uses: std.Message
    with:
      msg: "Compiling with -${{ optimization }} debug=${{ debug }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("my_pkg.compile")
        
        assert task is not None
        # Expression should be evaluated during task creation
        assert hasattr(task.params, 'msg')
    
    def test_feeds_relationship(self, tmpdir):
        """Test feeds (inverse of needs)"""
        flowdv = """
package:
  name: example
  
  tasks:
  - name: sources
    uses: std.Message
    feeds: [compile]
    with:
      msg: "Gathering sources"
  
  - name: compile
    uses: std.Message
    with:
      msg: "Compiling"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        
        # Check that feeds creates the dependency
        compile_task = builder.mkTaskNode("example.compile")
        assert compile_task is not None
        assert len(compile_task.needs) == 1


@pytest.mark.asyncio
async def test_complete_flow_example(tmpdir):
    """Test a complete working flow with execution"""
    flowdv = """
package:
  name: complete_example
  
  tasks:
  - name: message1
    uses: std.Message
    with:
      msg: "Step 1: Initialization"
  
  - name: message2
    uses: std.Message
    needs: [message1]
    with:
      msg: "Step 2: Processing"
  
  - name: message3
    uses: std.Message
    needs: [message2]
    with:
      msg: "Step 3: Complete"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("complete_example.message3")
    
    # Create runner and execute
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    
    assert listener.status == 0
