"""
Test suite for documentation examples in userguide/stdlib.rst
"""
import asyncio
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog


class TestStdLibExamples:
    """Test examples from stdlib.rst"""
    
    def test_fileset_example(self, tmpdir):
        """Test std.FileSet example"""
        flowdv = """
package:
    name: fileset.example

    tasks:
    - name: rtlsrc
      uses: std.FileSet
      with:
        include: '*.v'
        base: 'src/rtl'
        type: 'verilogSource'
"""
        rundir = str(tmpdir)
        rtl_dir = os.path.join(rundir, "src", "rtl")
        os.makedirs(rtl_dir)
        
        # Create test files
        with open(os.path.join(rtl_dir, "test1.v"), "w") as f:
            f.write("module test1; endmodule")
        with open(os.path.join(rtl_dir, "test2.v"), "w") as f:
            f.write("module test2; endmodule")
        
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert "rtlsrc" in pkg.task_m
    
    def test_createfile_example(self, tmpdir):
        """Test std.CreateFile example"""
        flowdv = """
package:
    name: create

    tasks:
    - name: TemplateFile
      uses: std.CreateFile
      with:
        type: text
        filename: template.txt
        content: |
          This is a template file
          with multiple lines
          of text.
"""
        rundir = str(tmpdir)
        with open(os.path.join(rundir, "flow.dv"), "w") as fp:
            fp.write(flowdv)
        
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
        assert pkg is not None
        assert "TemplateFile" in pkg.task_m


@pytest.mark.asyncio
async def test_exec_example(tmpdir):
    """Test std.Exec example"""
    flowdv = """
package:
    name: exec.example

    tasks:
    - name: run_script
      uses: std.Exec
      with:
        command: "echo 'Hello from script'"
        shell: bash
        when: always
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("exec.example.run_script")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_setenv_example(tmpdir):
    """Test std.SetEnv example"""
    flowdv = """
package:
    name: setenv.example

    tasks:
    - name: tool_env
      uses: std.SetEnv
      with:
        setenv:
          TOOL_HOME: /opt/tools/my_tool
          PYTHONPATH: "lib/python/site-packages"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("setenv.example.tool_env")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_setenv_glob_expansion(tmpdir):
    """Test std.SetEnv with glob expansion"""
    flowdv = """
package:
    name: glob_test

    tasks:
    - name: lib_paths
      uses: std.SetEnv
      with:
        setenv:
          MY_LIBS: "libs/*/lib"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    # Create directory structure for glob
    libs_dir = os.path.join(srcdir, "libs")
    os.makedirs(os.path.join(libs_dir, "lib1", "lib"))
    os.makedirs(os.path.join(libs_dir, "lib2", "lib"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("glob_test.lib_paths")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_setfiletype_example(tmpdir):
    """Test std.SetFileType example"""
    flowdv = """
package:
    name: setfiletype.example

    tasks:
    - name: verilog_files
      uses: std.FileSet
      with:
        include: "*.v"
        type: verilogSource
    
    - name: reinterpret
      uses: std.SetFileType
      needs: [verilog_files]
      with:
        filetype: systemVerilogSource
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    # Create a test file
    with open(os.path.join(srcdir, "test.v"), "w") as f:
        f.write("module test; endmodule")
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("setfiletype.example.reinterpret")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_incdirs_example(tmpdir):
    """Test std.IncDirs example"""
    flowdv = """
package:
    name: incdirs.example

    tasks:
    - name: rtl_files
      uses: std.FileSet
      with:
        include: "*.sv"
        incdirs:
          - include
          - rtl/include
        type: systemVerilogSource
    
    - name: extract_dirs
      uses: std.IncDirs
      needs: [rtl_files]
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    # Create directory structure
    os.makedirs(os.path.join(srcdir, "include"))
    os.makedirs(os.path.join(srcdir, "rtl", "include"))
    
    with open(os.path.join(srcdir, "test.sv"), "w") as f:
        f.write("module test; endmodule")
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("incdirs.example.extract_dirs")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_message_example(tmpdir):
    """Test std.Message example"""
    flowdv = """
package:
    name: message.example

    tasks:
    - name: hello
      uses: std.Message
      with:
        msg: "Hello, World!"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("message.example.hello")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_message_with_expression(tmpdir):
    """Test std.Message with expression"""
    flowdv = """
package:
  name: example
  with:
    version:
      type: str
      value: "1.0"
  
  tasks:
  - name: version_msg
    uses: std.Message
    with:
      msg: "Building version ${{ version }}"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("example.version_msg")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0


@pytest.mark.asyncio
async def test_complete_stdlib_workflow(tmpdir):
    """Test a complete workflow using multiple stdlib tasks"""
    flowdv = """
package:
  name: complete_workflow
  
  tasks:
  - name: create_file
    uses: std.CreateFile
    with:
      type: text
      filename: data.txt
      content: "Important data"
  
  - name: set_env
    uses: std.SetEnv
    with:
      setenv:
        DATA_FILE: "data.txt"
  
  - name: process
    uses: std.Exec
    needs: [create_file, set_env]
    with:
      command: "cat data.txt"
      shell: bash
  
  - name: report
    uses: std.Message
    needs: [process]
    with:
      msg: "Processing complete"
"""
    rundir = str(tmpdir.mkdir("rundir"))
    srcdir = str(tmpdir.mkdir("src"))
    
    with open(os.path.join(srcdir, "flow.dv"), "w") as fp:
        fp.write(flowdv)
    
    pkg = PackageLoader().load(os.path.join(srcdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, rundir)
    task = builder.mkTaskNode("complete_workflow.report")
    
    runner = TaskSetRunner(rundir=rundir)
    listener = TaskListenerLog()
    runner.add_listener(listener)
    
    await runner.run(task)
    assert listener.status == 0
