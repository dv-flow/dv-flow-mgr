"""
Tests for srcdir variable in fragments and imports.

The srcdir variable must always be set to the directory containing the 
current package or fragment file being processed.
"""
import os
import pytest
from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from .marker_collector import MarkerCollector


def test_srcdir_in_fragment(tmpdir):
    """Test that srcdir is set to fragment's directory when loading fragment"""
    # Create a subdirectory for the fragment
    frag_dir = tmpdir.mkdir("fragments")
    
    # Create a fragment that uses srcdir
    fragment_dv = """
fragment:
    name: test_frag
    tasks:
    - name: frag_task
      with:
          frag_srcdir:
              type: str
              value: ${{ srcdir }}
"""
    with open(os.path.join(frag_dir, "fragment.dv"), "w") as f:
        f.write(fragment_dv)
    
    # Create main package that imports the fragment
    flow_dv = """
package:
    name: test_pkg
    fragments:
    - fragments/fragment.dv
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))
    
    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    node = builder.mkTaskNode("test_pkg.test_frag.frag_task")
    
    # srcdir should be the fragment's directory, not the main package's directory
    expected_srcdir = str(frag_dir)
    
    assert hasattr(node.params, "frag_srcdir")
    actual_srcdir = getattr(node.params, "frag_srcdir")
    assert actual_srcdir == expected_srcdir, \
        f"Expected srcdir to be {expected_srcdir}, but got {actual_srcdir}"


def test_srcdir_in_nested_fragments(tmpdir):
    """Test srcdir with nested fragments in different directories"""
    # Create directory structure
    frag1_dir = tmpdir.mkdir("fragments")
    frag2_dir = frag1_dir.mkdir("subfragments")
    
    # Create second-level fragment
    fragment2_dv = """
fragment:
    name: nested_frag
    tasks:
    - name: nested_task
      with:
          nested_srcdir:
              type: str
              value: ${{ srcdir }}
"""
    with open(os.path.join(frag2_dir, "fragment2.dv"), "w") as f:
        f.write(fragment2_dv)
    
    # Create first-level fragment that loads second-level fragment
    fragment1_dv = """
fragment:
    name: parent_frag
    fragments:
    - subfragments/fragment2.dv
    tasks:
    - name: parent_task
      with:
          parent_srcdir:
              type: str
              value: ${{ srcdir }}
"""
    with open(os.path.join(frag1_dir, "fragment1.dv"), "w") as f:
        f.write(fragment1_dv)
    
    # Create main package
    flow_dv = """
package:
    name: test_pkg
    fragments:
    - fragments/fragment1.dv
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))
    
    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    
    # Check parent fragment task
    parent_node = builder.mkTaskNode("test_pkg.parent_frag.parent_task")
    assert hasattr(parent_node.params, "parent_srcdir")
    parent_srcdir = getattr(parent_node.params, "parent_srcdir")
    assert parent_srcdir == str(frag1_dir), \
        f"Expected parent srcdir to be {frag1_dir}, but got {parent_srcdir}"
    
    # Check nested fragment task
    nested_node = builder.mkTaskNode("test_pkg.nested_frag.nested_task")
    assert hasattr(nested_node.params, "nested_srcdir")
    nested_srcdir = getattr(nested_node.params, "nested_srcdir")
    assert nested_srcdir == str(frag2_dir), \
        f"Expected nested srcdir to be {frag2_dir}, but got {nested_srcdir}"


def test_srcdir_in_import(tmpdir):
    """Test that srcdir is set to imported package's directory"""
    # Create a subdirectory for the imported package
    import_dir = tmpdir.mkdir("imported")
    
    # Create imported package that uses srcdir
    imported_dv = """
package:
    name: imported_pkg
    with:
        import_srcdir:
            type: str
            value: ${{ srcdir }}
    tasks:
    - name: imported_task
      with:
          task_srcdir:
              type: str
              value: ${{ srcdir }}
"""
    with open(os.path.join(import_dir, "flow.dv"), "w") as f:
        f.write(imported_dv)
    
    # Create main package that imports the other package
    flow_dv = """
package:
    name: main_pkg
    imports:
    - imported/flow.dv
    tasks:
    - name: main_task
      with:
          imported_var:
              type: str
              value: ${{ imported_pkg.import_srcdir }}
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))
    
    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    
    # Check that the imported package's srcdir is the import directory
    node = builder.mkTaskNode("main_pkg.main_task")
    assert hasattr(node.params, "imported_var")
    actual_srcdir = getattr(node.params, "imported_var")
    assert actual_srcdir == str(import_dir), \
        f"Expected imported srcdir to be {import_dir}, but got {actual_srcdir}"


def test_srcdir_main_vs_fragment(tmpdir):
    """Test that main package and fragment have different srcdir values"""
    # Create fragment directory
    frag_dir = tmpdir.mkdir("fragments")
    
    # Create fragment
    fragment_dv = """
fragment:
    name: test_frag
    tasks:
    - name: frag_task
      with:
          frag_srcdir:
              type: str
              value: ${{ srcdir }}
"""
    with open(os.path.join(frag_dir, "fragment.dv"), "w") as f:
        f.write(fragment_dv)
    
    # Create main package
    flow_dv = """
package:
    name: test_pkg
    with:
        main_srcdir:
            type: str
            value: ${{ srcdir }}
    fragments:
    - fragments/fragment.dv
    tasks:
    - name: main_task
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
    
    # Main package task should have main directory as srcdir
    main_node = builder.mkTaskNode("test_pkg.main_task")
    assert hasattr(main_node.params, "task_srcdir")
    main_srcdir = getattr(main_node.params, "task_srcdir")
    assert main_srcdir == str(tmpdir), \
        f"Expected main srcdir to be {tmpdir}, but got {main_srcdir}"
    
    # Fragment task should have fragment directory as srcdir
    frag_node = builder.mkTaskNode("test_pkg.test_frag.frag_task")
    assert hasattr(frag_node.params, "frag_srcdir")
    frag_srcdir = getattr(frag_node.params, "frag_srcdir")
    assert frag_srcdir == str(frag_dir), \
        f"Expected frag srcdir to be {frag_dir}, but got {frag_srcdir}"
    
    # Verify they are different
    assert main_srcdir != frag_srcdir, \
        "Main package and fragment should have different srcdir values"


def test_srcdir_in_fragment_pytask(tmpdir):
    """Test that srcdir works correctly in fragment pytask imports"""
    # Create fragment directory with Python module
    frag_dir = tmpdir.mkdir("fragments")
    
    python_code = """
async def MyTask(ctxt, input):
    from dv_flow.mgr.task_data import TaskDataResult
    return TaskDataResult(status=0, output=[{"path": __file__}])
"""
    with open(os.path.join(frag_dir, "my_module.py"), "w") as f:
        f.write(python_code)
    
    # Create fragment that uses srcdir to reference the Python module
    fragment_dv = """
fragment:
    name: test_frag
    tasks:
    - name: pytask_test
      shell: pytask
      run: ${{ srcdir }}/my_module.py::MyTask
"""
    with open(os.path.join(frag_dir, "fragment.dv"), "w") as f:
        f.write(fragment_dv)
    
    # Create main package
    flow_dv = """
package:
    name: test_pkg
    fragments:
    - fragments/fragment.dv
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow_dv)
    
    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(
        os.path.join(tmpdir, "flow.dv"))
    
    # Should not have errors - srcdir should resolve to fragment directory
    assert len(markers.markers) == 0, f"Unexpected markers: {[m.msg for m in markers.markers]}"
    
    # Verify the path was expanded correctly
    # The task should be able to execute successfully, which means srcdir was resolved correctly
    task = pkg.task_m['test_pkg.test_frag.pytask_test']
    expected_path = os.path.join(frag_dir, "my_module.py") + "::MyTask"
    assert task.run == expected_path, \
        f"Expected run path to be {expected_path}, but got {task.run}"
