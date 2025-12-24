"""
Test suite for documentation examples in userguide/tasks_developing.rst
"""
import asyncio
import os
import sys
import pytest
import dataclasses as dc
from dv_flow.mgr import (
    PackageLoader, TaskGraphBuilder, TaskSetRunner,
    PyTask, TaskRunCtxt, TaskDataInput, TaskDataResult
)
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestTasksDevelopingExamples:
    """Test examples from tasks_developing.rst"""
    
    def test_inline_pytask(self, tmpdir):
        """Test inline pytask implementation"""
        flowdv = """
package:
  name: my_tool
  tasks:
  - name: my_task
    with:
      msg:
        type: str
        value: "Hello"
    shell: pytask
    run: |
      print("Message: %s" % input.params.msg)
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert "my_task" in pkg.task_m
    
    def test_matrix_strategy(self, tmpdir):
        """Test matrix strategy for task expansion"""
        flowdv = """
package:
  name: my_pkg
  
  tasks:
  - name: SayHi
    strategy:
      matrix:
        who: ["Adam", "Mary", "Joe"]
    body:
      - name: Output
        uses: std.Message
        with:
          msg: "Hello ${{ matrix.who }}!"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("my_pkg.SayHi")
        
        assert task is not None


class TestPyTaskClassExample:
    """Test PyTask class-based examples"""
    
    def test_pytask_class_definition(self, tmpdir):
        """Test PyTask class definition and usage"""
        
        # Define a PyTask class
        @dc.dataclass
        class MyCompiler(PyTask):
            desc = "Compiles HDL sources"
            
            @dc.dataclass
            class Params:
                sources: list = dc.field(default_factory=list)
                optimization: str = "O2"
                debug: bool = False
            
            async def __call__(self):
                # Access parameters
                msg = f"Compiling {len(self.params.sources)} files with -{self.params.optimization}"
                if self.params.debug:
                    msg += " (debug mode)"
                print(msg)
                return None
        
        # Create test module
        module_code = '''
import dataclasses as dc
from dv_flow.mgr import PyTask

@dc.dataclass
class MyCompiler(PyTask):
    desc = "Compiles HDL sources"
    
    @dc.dataclass
    class Params:
        sources: list = dc.field(default_factory=list)
        optimization: str = "O2"
        debug: bool = False
    
    async def __call__(self):
        msg = f"Compiling {len(self.params.sources)} files with -{self.params.optimization}"
        if self.params.debug:
            msg += " (debug mode)"
        return None
'''
        
        # Write module to file
        module_dir = str(tmpdir.mkdir("my_package"))
        with open(os.path.join(module_dir, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(module_dir, "my_module.py"), "w") as f:
            f.write(module_code)
        
        # Add to path
        sys.path.insert(0, str(tmpdir))
        
        try:
            # Create flow using the PyTask
            flowdv = f"""
package:
  name: my_tools
  
  tasks:
  - name: compile
    shell: pytask
    run: my_package.my_module.MyCompiler
    with:
      sources:
        - src/file1.v
        - src/file2.v
      optimization: "O3"
      debug: true
"""
            rundir = str(tmpdir.mkdir("rundir"))
            with open(os.path.join(rundir, "flow.dv"), "w") as fp:
                fp.write(flowdv)
            
            pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
            assert pkg is not None
            assert "compile" in pkg.task_m
        finally:
            sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_external_pytask_execution(tmpdir):
    """Test external pytask implementation with execution"""
    
    # Create a module with a task implementation
    module_code = '''
import dataclasses as dc
from dv_flow.mgr import TaskDataResult

async def MyTask(ctxt, input):
    """Simple task that prints a message"""
    print(f"Message: {input.params.msg}")
    return TaskDataResult(
        status=0,
        changed=True
    )
'''
    
    module_dir = str(tmpdir.mkdir("test_pkg"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "test_module.py"), "w") as f:
        f.write(module_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: my_tool
  tasks:
  - name: my_task
    shell: pytask
    run: test_pkg.test_module.MyTask
    with:
      msg:
        type: str
        value: "Hello from external task!"
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("my_tool.my_task")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_generate_strategy(tmpdir):
    """Test task graph generation with generate strategy"""
    
    # Create generator function
    generator_code = '''
def GenGraph(ctxt, input):
    """Generate multiple message tasks"""
    count = input.params.count
    for i in range(count):
        task = ctxt.mkTaskNode(
            "std.Message",
            name=ctxt.mkName(f"SayHi{i}"),
            msg=f"Hello World {i+1}!"
        )
        ctxt.addTask(task)
'''
    
    module_dir = str(tmpdir.mkdir("gen_pkg"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "gen_mod.py"), "w") as f:
        f.write(generator_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: my_pkg
  
  tasks:
  - name: SayHi
    with:
      count:
        type: int
        value: 3
    strategy:
      generate:
        run: gen_pkg.gen_mod.GenGraph
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("my_pkg.SayHi")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))
