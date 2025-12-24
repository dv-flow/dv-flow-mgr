"""
Test suite for documentation examples in userguide/expressions.rst
"""
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestExpressionsExamples:
    """Test examples from expressions.rst"""
    
    def test_basic_parameter_reference(self, tmpdir):
        """Test basic parameter reference in expression"""
        flowdv = """
package:
  name: my_pkg
  with:
    version:
      type: str
      value: "1.0"
    debug:
      type: bool
      value: false
  
  tasks:
  - name: build
    with:
      build_type:
        type: str
        value: "debug"
    uses: std.Message
    with:
      msg: "Building version ${{ version }} in ${{ build_type }} mode"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_arithmetic_operations(self, tmpdir):
        """Test arithmetic operations in expressions"""
        flowdv = """
package:
  name: example
  with:
    base_value:
      type: int
      value: 100
  
  tasks:
  - name: task1
    uses: std.Message
    with:
      msg: "Double value: ${{ base_value * 2 }}"
  
  - name: task2
    uses: std.Message
    with:
      msg: "Sum: ${{ base_value + 50 }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_boolean_expressions(self, tmpdir):
        """Test boolean expressions"""
        flowdv = """
package:
  name: example
  with:
    debug:
      type: bool
      value: false
    optimization:
      type: int
      value: 2
  
  tasks:
  - name: check
    uses: std.Message
    iff: ${{ debug and optimization < 2 }}
    with:
      msg: "Debug mode with low optimization"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_string_concatenation(self, tmpdir):
        """Test string concatenation"""
        flowdv = """
package:
  name: example
  with:
    prefix:
      type: str
      value: "build"
    version:
      type: str
      value: "1.0"
  
  tasks:
  - name: task1
    uses: std.Message
    with:
      msg: "${{ prefix }}_v${{ version }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_matrix_variables(self, tmpdir):
        """Test matrix variable references"""
        flowdv = """
package:
  name: matrix_test
  
  tasks:
  - name: test_suite
    strategy:
      matrix:
        test: ["test1", "test2", "test3"]
        seed: [100, 200, 300]
    body:
    - name: run_test
      uses: std.Message
      with:
        msg: "Running ${{ matrix.test }} with seed ${{ matrix.seed }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_conditional_expression(self, tmpdir):
        """Test conditional (ternary) expression"""
        flowdv = """
package:
  name: example
  with:
    debug:
      type: bool
      value: false
  
  tasks:
  - name: build
    uses: std.Message
    with:
      msg: ${{ "debug build" if debug else "release build" }}
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_list_access(self, tmpdir):
        """Test list element access"""
        flowdv = """
package:
  name: example
  with:
    flags:
      type: list
      value: ["-O2", "-Wall", "-Werror"]
  
  tasks:
  - name: task1
    uses: std.Message
    with:
      msg: "First flag: ${{ flags[0] }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_dict_access(self, tmpdir):
        """Test dictionary value access"""
        flowdv = """
package:
  name: example
  with:
    config:
      type: map
      value:
        arch: "x86_64"
        os: "linux"
  
  tasks:
  - name: task2
    uses: std.Message
    with:
      msg: "Architecture: ${{ config['arch'] }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None


@pytest.mark.asyncio
async def test_version_construction_pattern(tmpdir):
    """Test version construction pattern"""
    flowdv = """
package:
  with:
    major:
      type: int
      value: 1
    minor:
      type: int
      value: 0
    patch:
      type: int
      value: 0
    version:
      type: str
      value: "${{ major }}.${{ minor }}.${{ patch }}"
  
  tasks:
  - name: show_version
    uses: std.Message
    with:
      msg: "Version: ${{ version }}"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("show_version")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_path_construction_pattern(tmpdir):
    """Test path construction pattern"""
    flowdv = """
package:
  with:
    install_prefix:
      type: str
      value: "/opt/tools"
    tool_name:
      type: str
      value: "mytool"
    tool_path:
      type: str
      value: "${{ install_prefix }}/${{ tool_name }}"
  
  tasks:
  - name: show_path
    uses: std.Message
    with:
      msg: "Tool path: ${{ tool_path }}"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("show_path")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_conditional_features_pattern(tmpdir):
    """Test conditional features pattern"""
    flowdv = """
package:
  with:
    enable_coverage:
      type: bool
      value: false
    enable_assertions:
      type: bool
      value: true
    debug_mode:
      type: bool
      value: ${{ enable_coverage or enable_assertions }}
  
  tasks:
  - name: show_debug
    uses: std.Message
    with:
      msg: "Debug mode: ${{ debug_mode }}"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("show_debug")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_parameter_selection_pattern(tmpdir):
    """Test parameter selection pattern"""
    flowdv = """
package:
  with:
    simulator:
      type: str
      value: "verilator"
    debug_level:
      type: int
      value: 0
  
  tasks:
  - name: show_sim
    uses: std.Message
    with:
      msg: "Using simulator: ${{ simulator }} with debug=${{ debug_level }}"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("show_sim")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0
