"""
Comprehensive tests for built-in variable expansion.

Tests that all built-in variables (rootdir, srcdir, rundir, root, env, etc.)
are properly expanded in various contexts.
"""
import os
import asyncio
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner
from .marker_collector import MarkerCollector


def test_rootdir_expansion(tmpdir):
    """Test that ${{ rootdir }} expands to package directory"""
    flow_dv = """
package:
    name: test_pkg
    with:
        root_path:
            type: str
            value: ${{ rootdir }}
    tasks:
    - name: test_task
      with:
          task_rootdir:
              type: str
              value: ${{ rootdir }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    # rootdir should be the directory containing flow.dv
    expected_rootdir = str(tmpdir)
    
    assert hasattr(node.params, "task_rootdir")
    assert getattr(node.params, "task_rootdir") == expected_rootdir


def test_srcdir_expansion(tmpdir):
    """Test that ${{ srcdir }} expands to source directory"""
    flow_dv = """
package:
    name: test_pkg
    with:
        src_path:
            type: str
            value: ${{ srcdir }}
    tasks:
    - name: test_task
      with:
          task_srcdir:
              type: str
              value: ${{ srcdir }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    # srcdir should be the directory containing flow.dv
    expected_srcdir = str(tmpdir)
    
    assert hasattr(node.params, "task_srcdir")
    assert getattr(node.params, "task_srcdir") == expected_srcdir


def test_root_expansion(tmpdir):
    """Test that ${{ root }} expands to package file path"""
    flow_dv = """
package:
    name: test_pkg
    with:
        root_file:
            type: str
            value: ${{ root }}
    tasks:
    - name: test_task
      with:
          task_root:
              type: str
              value: ${{ root }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    # root should be the full path to flow.dv
    expected_root = os.path.join(tmpdir, "flow.dv")
    
    assert hasattr(node.params, "task_root")
    assert getattr(node.params, "task_root") == expected_root


def test_env_expansion(tmpdir):
    """Test that ${{ env.VAR }} expands to environment variable"""
    os.environ["TEST_VAR_FOR_DV_FLOW"] = "test_value_123"
    
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: test_task
      with:
          env_var:
              type: str
              value: ${{ env.TEST_VAR_FOR_DV_FLOW }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    assert hasattr(node.params, "env_var")
    assert getattr(node.params, "env_var") == "test_value_123"
    
    # Clean up
    del os.environ["TEST_VAR_FOR_DV_FLOW"]


def test_rundir_expansion_in_shell(tmpdir):
    """Test that ${{ rundir }} expands correctly in shell tasks"""
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: test_task
      shell: bash
      run: |
        echo "rundir is: ${{ rundir }}" > output.txt
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))
    
    node = builder.mkTaskNode("test_pkg.test_task")
    output = asyncio.run(runner.run(node))
    
    assert runner.status == 0
    
    # Check that output.txt was created with the rundir path
    output_file = os.path.join(node.rundir, "output.txt")
    assert os.path.exists(output_file)
    
    with open(output_file, "r") as f:
        content = f.read()
    
    # Should contain the actual rundir path, not the literal string
    assert "${{ rundir }}" not in content
    assert node.rundir in content


def test_all_builtin_vars_in_compound_task(tmpdir):
    """Test multiple built-in variables in compound task context"""
    os.environ["TEST_COMPOUND_VAR"] = "compound_value"
    
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: compound_task
      with:
          pkg_root:
              type: str
              value: ${{ root }}
          pkg_rootdir:
              type: str
              value: ${{ rootdir }}
          pkg_srcdir:
              type: str
              value: ${{ srcdir }}
          env_val:
              type: str
              value: ${{ env.TEST_COMPOUND_VAR }}
      body:
      - name: subtask
        with:
            sub_root:
                type: str
                value: ${{ this.pkg_root }}
            sub_rootdir:
                type: str
                value: ${{ this.pkg_rootdir }}
            sub_srcdir:
                type: str
                value: ${{ this.pkg_srcdir }}
            sub_env:
                type: str
                value: ${{ this.env_val }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.compound_task")

    # Check parent task params
    assert hasattr(node.params, "pkg_root")
    assert getattr(node.params, "pkg_root") == os.path.join(tmpdir, "flow.dv")
    
    assert hasattr(node.params, "pkg_rootdir")
    assert getattr(node.params, "pkg_rootdir") == str(tmpdir)
    
    assert hasattr(node.params, "pkg_srcdir")
    assert getattr(node.params, "pkg_srcdir") == str(tmpdir)
    
    assert hasattr(node.params, "env_val")
    assert getattr(node.params, "env_val") == "compound_value"
    
    # Check subtask params (via 'this' reference)
    assert len(node.tasks) == 2  # input + subtask
    subtask_node = node.tasks[-1]
    
    assert hasattr(subtask_node.params, "sub_root")
    assert getattr(subtask_node.params, "sub_root") == os.path.join(tmpdir, "flow.dv")
    
    assert hasattr(subtask_node.params, "sub_rootdir")
    assert getattr(subtask_node.params, "sub_rootdir") == str(tmpdir)
    
    assert hasattr(subtask_node.params, "sub_srcdir")
    assert getattr(subtask_node.params, "sub_srcdir") == str(tmpdir)
    
    assert hasattr(subtask_node.params, "sub_env")
    assert getattr(subtask_node.params, "sub_env") == "compound_value"
    
    # Clean up
    del os.environ["TEST_COMPOUND_VAR"]


def test_rundir_in_fileset_base(tmpdir):
    """Test that ${{ rundir }} works in FileSet base parameter"""
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: create_file
      rundir: inherit
      uses: std.CreateFile
      with:
          filename: test.txt
          content: "test content"
    - name: find_file
      rundir: inherit
      uses: std.FileSet
      needs: [create_file]
      passthrough: none
      with:
          base: ${{ rundir }}
          include: "*.txt"
          type: textFile
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))
    
    node = builder.mkTaskNode("test_pkg.find_file")
    output = asyncio.run(runner.run(node))
    
    assert runner.status == 0
    assert len(output.output) == 1
    assert output.output[0].type == 'std.FileSet'
    assert len(output.output[0].files) == 1


def test_srcdir_in_pytask_import(tmpdir):
    """Test that ${{ srcdir }} works in pytask imports"""
    # Create a Python module to import
    python_code = """
async def MyTask(ctxt, input):
    from dv_flow.mgr.task_data import TaskDataResult
    return TaskDataResult(status=0)
"""
    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(python_code)

    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: test_task
      shell: pytask
      run: ${{ srcdir }}/my_module.py::MyTask
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))
    
    node = builder.mkTaskNode("test_pkg.test_task")
    output = asyncio.run(runner.run(node))
    
    assert runner.status == 0


def test_builtin_vars_in_imports(tmpdir):
    """Test that rootdir and srcdir work in package imports"""
    # Create an imported package
    pkg1_dv = """
package:
    name: pkg1
    with:
        imported_var:
            type: str
            value: "from_pkg1"
"""
    with open(os.path.join(tmpdir, "pkg1.dv"), "w") as f:
        f.write(pkg1_dv)

    # Create main package that uses rootdir/srcdir in import
    flow_dv = """
package:
    name: main_pkg
    imports:
    - ${{ rootdir }}/pkg1.dv
    tasks:
    - name: test_task
      with:
          imported:
              type: str
              value: ${{ pkg1.imported_var }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("main_pkg.test_task")

    assert hasattr(node.params, "imported")
    assert getattr(node.params, "imported") == "from_pkg1"


def test_env_in_uses_expansion(tmpdir):
    """Test that environment variables work in uses field"""
    os.environ["TASK_BASE_NAME"] = "CreateFile"
    
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: test_task
      rundir: inherit
      uses: std.${{ env.TASK_BASE_NAME }}
      with:
          filename: test.txt
          content: "content"
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    # Should resolve to std.CreateFile
    assert len(markers.markers) == 0, f"Markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))
    
    node = builder.mkTaskNode("test_pkg.test_task")
    output = asyncio.run(runner.run(node))
    
    assert runner.status == 0
    
    # Clean up
    del os.environ["TASK_BASE_NAME"]


def test_multiple_env_vars(tmpdir):
    """Test multiple environment variable expansions"""
    os.environ["PREFIX"] = "prefix"
    os.environ["SUFFIX"] = "suffix"
    
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: test_task
      with:
          combined:
              type: str
              value: "${{ env.PREFIX }}_middle_${{ env.SUFFIX }}"
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    assert hasattr(node.params, "combined")
    assert getattr(node.params, "combined") == "prefix_middle_suffix"
    
    # Clean up
    del os.environ["PREFIX"]
    del os.environ["SUFFIX"]


def test_rundir_preserved_for_runtime(tmpdir):
    """Test that rundir is preserved as a template for runtime expansion"""
    flow_dv = """
package:
    name: test_pkg
    with:
        static_rundir:
            type: str
            value: ${{ rundir }}
    tasks:
    - name: test_task
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    # rundir at package level should be preserved as template
    # since it's only known at runtime
    assert len(markers.markers) == 0


def test_srcdir_vs_rootdir_same_for_root_package(tmpdir):
    """Test that srcdir and rootdir are the same for root package"""
    flow_dv = """
package:
    name: test_pkg
    with:
        src:
            type: str
            value: ${{ srcdir }}
        root:
            type: str
            value: ${{ rootdir }}
    tasks:
    - name: test_task
      with:
          src_copy:
              type: str
              value: ${{ src }}
          root_copy:
              type: str
              value: ${{ root }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0
    
    # For root package, srcdir and rootdir should be the same
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")
    
    # Check that the task received the package params with resolved paths
    assert hasattr(node.params, 'src_copy')
    assert hasattr(node.params, 'root_copy')
    
    # Both should point to the same directory (tmpdir)
    assert getattr(node.params, 'src_copy') == str(tmpdir)
    assert getattr(node.params, 'root_copy') == str(tmpdir)


def test_nested_env_and_rootdir(tmpdir):
    """Test nested expansion with env and rootdir"""
    os.environ["SUBDIR"] = "mysubdir"
    
    flow_dv = """
package:
    name: test_pkg
    tasks:
    - name: test_task
      with:
          full_path:
              type: str
              value: "${{ rootdir }}/${{ env.SUBDIR }}/file.txt"
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 0
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_task")

    assert hasattr(node.params, "full_path")
    expected = f"{tmpdir}/mysubdir/file.txt"
    assert getattr(node.params, "full_path") == expected
    
    # Clean up
    del os.environ["SUBDIR"]
