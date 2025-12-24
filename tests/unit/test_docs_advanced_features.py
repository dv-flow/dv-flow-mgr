"""
Test suite for documentation examples in userguide/advanced_features.rst
"""
import asyncio
import os
import sys
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestAdvancedFeaturesExamples:
    """Test examples from advanced_features.rst"""
    
    def test_selective_override(self, tmpdir):
        """Test selective override pattern"""
        flowdv = """
package:
  name: my_project
  with:
    use_fast_sim:
      type: bool
      value: false
  
  tasks:
  - name: sim
    uses: std.Message
    with:
      msg: "Normal simulation"
  
  configs:
  - name: fast
    with:
      use_fast_sim:
        value: true
    tasks:
    - name: sim_fast
      override: sim
      with:
        msg: "Fast simulation"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert len(pkg.pkg_def.configs) == 1
    
    def test_layered_overrides(self, tmpdir):
        """Test layered override pattern"""
        flowdv = """
package:
  name: project
  
  tasks:
  - name: compile
    uses: std.Message
    with:
      msg: "Normal compile"
  
  configs:
  - name: base_debug
    tasks:
    - name: compile_debug
      override: compile
      with:
        msg: "Debug compile"
  
  - name: instrumented
    uses: base_debug
    tasks:
    - name: compile_instrumented
      override: compile
      with:
        msg: "Instrumented compile"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert len(pkg.pkg_def.configs) == 2
    
    def test_conditional_override(self, tmpdir):
        """Test conditional override pattern"""
        flowdv = """
package:
  name: project
  with:
    platform:
      type: str
      value: "linux"
  
  tasks:
  - name: toolchain
    uses: std.Message
    with:
      msg: "Default toolchain"
  
  - name: toolchain_linux
    override: toolchain
    iff: ${{ platform == "linux" }}
    uses: std.Message
    with:
      msg: "Linux toolchain"
  
  - name: toolchain_windows
    override: toolchain
    iff: ${{ platform == "windows" }}
    uses: std.Message
    with:
      msg: "Windows toolchain"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_fan_out_fan_in(self, tmpdir):
        """Test fan-out/fan-in dataflow pattern"""
        flowdv = """
package:
  name: fanout_test
  
  tasks:
  - name: source
    uses: std.Message
    with:
      msg: "Source data"
  
  - name: lint
    uses: std.Message
    needs: [source]
    with:
      msg: "Linting"
  
  - name: compile
    uses: std.Message
    needs: [source]
    with:
      msg: "Compiling"
  
  - name: synthesize
    uses: std.Message
    needs: [source]
    with:
      msg: "Synthesizing"
  
  - name: report
    uses: std.Message
    needs: [lint, compile, synthesize]
    with:
      msg: "Generating report"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("fanout_test.report")
        
        assert task is not None
        assert len(task.needs) == 3
    
    def test_selective_dataflow(self, tmpdir):
        """Test selective dataflow with consumes patterns"""
        flowdv = """
package:
  name: selective_test
  
  tasks:
  - name: all_sources
    uses: std.FileSet
    with:
      include: "*.sv"
      type: systemVerilogSource
  
  - name: compile_rtl
    uses: std.Message
    needs: [all_sources]
    consumes:
    - type: std.FileSet
    with:
      msg: "Compiling RTL"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None


@pytest.mark.asyncio
async def test_programmatic_generation(tmpdir):
    """Test programmatic graph construction"""
    
    generator_code = '''
def GenerateTestSuite(ctxt, input):
    """Generate tests from a list"""
    tests = ["test1", "test2", "test3"]
    
    for test in tests:
        test_task = ctxt.mkTaskNode(
            "std.Message",
            name=ctxt.mkName(f"test_{test}"),
            msg=f"Running {test}"
        )
        ctxt.addTask(test_task)
'''
    
    module_dir = str(tmpdir.mkdir("test_gen"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "gen.py"), "w") as f:
        f.write(generator_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: gen_test
  
  tasks:
  - name: test_suite
    strategy:
      generate:
        run: test_gen.gen.GenerateTestSuite
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("gen_test.test_suite")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_parameterized_generation(tmpdir):
    """Test parameterized generation"""
    
    generator_code = '''
def GenerateParallelTasks(ctxt, input):
    """Generate N parallel tasks"""
    count = input.params.task_count
    mode = input.params.mode
    
    for i in range(count):
        task = ctxt.mkTaskNode(
            "std.Message",
            name=ctxt.mkName(f"task_{i}"),
            msg=f"Task {i} in {mode} mode"
        )
        ctxt.addTask(task)
'''
    
    module_dir = str(tmpdir.mkdir("par_gen"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "gen.py"), "w") as f:
        f.write(generator_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: par_test
  
  tasks:
  - name: parallel_work
    with:
      task_count:
        type: int
        value: 5
      mode:
        type: str
        value: "fast"
    strategy:
      generate:
        run: par_gen.gen.GenerateParallelTasks
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("par_test.parallel_work")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_dependency_management(tmpdir):
    """Test dynamic dependency creation"""
    
    generator_code = '''
def GeneratePipeline(ctxt, input):
    """Generate a pipeline of dependent tasks"""
    stages = [
        {"name": "stage1", "type": "std.Message", "params": {"msg": "Stage 1"}},
        {"name": "stage2", "type": "std.Message", "params": {"msg": "Stage 2"}},
        {"name": "stage3", "type": "std.Message", "params": {"msg": "Stage 3"}},
    ]
    prev_task = None
    
    for stage in stages:
        needs = [prev_task] if prev_task else None
        task = ctxt.mkTaskNode(
            stage['type'],
            name=ctxt.mkName(stage['name']),
            needs=needs,
            **stage.get('params', {})
        )
        ctxt.addTask(task)
        prev_task = task
'''
    
    module_dir = str(tmpdir.mkdir("pipe_gen"))
    with open(os.path.join(module_dir, "__init__.py"), "w") as f:
        f.write("")
    with open(os.path.join(module_dir, "gen.py"), "w") as f:
        f.write(generator_code)
    
    sys.path.insert(0, str(tmpdir))
    
    try:
        flowdv = """
package:
  name: pipe_test
  
  tasks:
  - name: pipeline
    strategy:
      generate:
        run: pipe_gen.gen.GeneratePipeline
"""
        rundir = str(tmpdir.mkdir("rundir"))
        srcdir = str(tmpdir.mkdir("src"))
        
        with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
        builder = TaskGraphBuilder(pkg, rundir)
        task = builder.mkTaskNode("pipe_test.pipeline")
        
        runner = TaskSetRunner(rundir=rundir)
        listener = TaskListenerLog()
        runner.add_listener(listener)
        
        await runner.run(task)
        assert listener.status == 0
    finally:
        sys.path.remove(str(tmpdir))


@pytest.mark.asyncio
async def test_data_transformation_pipeline(tmpdir):
    """Test data transformation with selective passthrough"""
    flowdv = """
package:
  name: transform_test
  
  tasks:
  - name: gather_sources
    uses: std.FileSet
    with:
      include: "*.txt"
      type: text
  
  - name: transform
    uses: std.Message
    needs: [gather_sources]
    passthrough: none
    with:
      msg: "Transforming data"
  
  - name: compile
    uses: std.Message
    needs: [transform]
    with:
      msg: "Compiling transformed data"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    # Create test file
    with open(os.path.join(srcdir, "test.txt"), "w") as f:
        f.write("test data")
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("transform_test.compile")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0
