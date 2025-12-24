"""
Test suite for documentation examples in userguide/packages.rst
"""
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestPackagesExamples:
    """Test examples from packages.rst"""
    
    def test_minimal_package(self, tmpdir):
        """Test minimal package definition"""
        flowdv = """
package:
    name: my_project

    tasks:
    - name: task1
      uses: std.Message
      with:
        msg: "Hello from my_project!"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert pkg.name == "my_project"
        assert "task1" in pkg.task_m
    
    def test_package_imports_by_path(self, tmpdir):
        """Test importing packages by path"""
        # Create sub-package
        subdir = tmpdir.mkdir("subdir")
        sub_flowdv = """
package:
    name: my_lib
    
    tasks:
    - name: some_task
      uses: std.Message
      with:
        msg: "From my_lib"
"""
        with open(os.path.join(str(subdir), "flow.dv"), "w") as f:
            f.write(sub_flowdv)
        
        # Create main package
        flowdv = """
package:
    name: top

    imports:
    - subdir/flow.dv

    tasks:
    - name: use_imported
      uses: my_lib.some_task
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(str(tmpdir), "flow.dv"))
        assert pkg is not None
        assert "my_lib" in pkg.pkg_m
    
    def test_package_import_with_alias(self, tmpdir):
        """Test importing with alias"""
        flowdv = """
package:
    name: proj

    imports:
    - name: std
      as: stdlib

    tasks:
    - name: build
      uses: stdlib.Message
      with:
        msg: "Using aliased import"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
    
    def test_package_parameters(self, tmpdir):
        """Test package with parameters"""
        flowdv = """
package:
    name: configurable_ip
    
    with:
      debug:
        type: int
        value: 0
      width:
        type: int
        value: 32

    tasks:
    - name: build
      uses: std.Message
      with:
        msg: "Building with width=${{ width }}, debug=${{ debug }}"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert pkg.paramT is not None
    
    def test_package_fragments(self, tmpdir):
        """Test package fragments"""
        # Create main package
        flowdv = """
package:
    name: big_project

    fragments:
    - src/rtl/flow.dv

    tasks:
    - name: top_task
      uses: std.Message
      with:
        msg: "Top task"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flowdv)
        
        # Create fragment
        rtl_dir = tmpdir.mkdir("src").mkdir("rtl")
        fragment = """
fragment:
    tasks:
    - name: build
      uses: std.Message
      with:
        msg: "From fragment"
"""
        with open(os.path.join(str(rtl_dir), "flow.dv"), "w") as f:
            f.write(fragment)
        
        pkg = PackageLoader().load(os.path.join(str(tmpdir), "flow.dv"))
        assert pkg is not None
        # Fragment tasks should be in the package
        assert "build" in pkg.task_m
    
    def test_package_configuration(self, tmpdir):
        """Test package configurations"""
        flowdv = """
package:
  name: my_project
  
  with:
    debug:
      type: bool
      value: false
  
  tasks:
  - name: build
    uses: std.Message
    with:
      msg: "Building in default mode"
  
  configs:
  - name: debug
    with:
      debug:
        value: true
    
    tasks:
    - name: build_debug
      override: build
      with:
        msg: "Building in debug mode"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert len(pkg.pkg_def.configs) == 1
        assert pkg.pkg_def.configs[0].name == "debug"
    
    def test_package_extensions(self, tmpdir):
        """Test package extensions in configurations"""
        flowdv = """
package:
  name: my_project
  
  tasks:
  - name: compile
    uses: std.Message
    with:
      msg: "Compiling"
  
  configs:
  - name: coverage
    extensions:
    - task: compile
      with:
        coverage:
          type: bool
          value: true
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert len(pkg.pkg_def.configs) == 1
        assert len(pkg.pkg_def.configs[0].extensions) == 1
    
    def test_package_parameters(self, tmpdir):
        """Test package parameters usage"""
        flowdv = """
package:
  name: proj
  with:
    version:
      type: str
      value: "1.0"
    debug:
      type: bool
      value: false
  
  tasks:
  - name: build
    uses: std.Message
    with:
      msg: "Building version ${{ version }} (debug=${{ debug }})"
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None


@pytest.mark.asyncio
async def test_package_with_configuration_execution(tmpdir):
    """Test executing a package with a configuration"""
    flowdv = """
package:
  name: config_test
  
  with:
    mode:
      type: str
      value: "normal"
  
  tasks:
  - name: run
    uses: std.Message
    with:
      msg: "Running in ${{ mode }} mode"
  
  configs:
  - name: fast
    with:
      mode:
        value: "fast"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    # Load without config
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("config_test.run")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_multi_package_flow(tmpdir):
    """Test flow with multiple imported packages"""
    # Create lib1 package
    lib1_dir = tmpdir.mkdir("lib1")
    lib1_flow = """
package:
    name: lib1
    
    tasks:
    - name: process
      uses: std.Message
      with:
        msg: "Processing in lib1"
"""
    with open(os.path.join(str(lib1_dir), "flow.dv"), "w") as f:
        f.write(lib1_flow)
    
    # Create lib2 package
    lib2_dir = tmpdir.mkdir("lib2")
    lib2_flow = """
package:
    name: lib2
    
    tasks:
    - name: analyze
      uses: std.Message
      with:
        msg: "Analyzing in lib2"
"""
    with open(os.path.join(str(lib2_dir), "flow.dv"), "w") as f:
        f.write(lib2_flow)
    
    # Create main package
    main_flow = """
package:
    name: main
    
    imports:
    - lib1
    - lib2
    
    tasks:
    - name: task1
      uses: lib1.process
    
    - name: task2
      uses: lib2.analyze
      needs: [task1]
"""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
        f.write(main_flow)
    
    rundir = str(tmpdir.mkdir("rundir"))
    pkg = PackageLoader().load(os.path.join(str(tmpdir), "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("main.task2")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0
