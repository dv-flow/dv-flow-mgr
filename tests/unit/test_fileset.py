import asyncio
import io
import json
import os
import dataclasses as dc
import pytest
from typing import Any, List, Union
import yaml
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner, task, TaskDataResult
from dv_flow.mgr.fileset import FileSet
from dv_flow.mgr.task_data import SeverityE
from pydantic import BaseModel
from shutil import copytree

def test_fileset_1(tmpdir):
    """"""
    datadir = os.path.join(os.path.dirname(__file__), "data/fileset")

    copytree(
        os.path.join(datadir, "test1"), 
        os.path.join(tmpdir, "test1"))
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("test1.files1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert runner.status == 0
    assert out.changed == True

    # Now, re-run using the same run directory.
    # Since the files haven't changed, the output must indicate that
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("test1.files1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert out.changed == False

    # Now, add a file
    with open(os.path.join(tmpdir, "test1", "files1", "file1_3.sv"), "w") as f:
        f.write("// file1_3.sv\n")

    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    task = builder.mkTaskNode("test1.files1")
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(task))
    assert out.changed == True

def test_fileset_input_1(tmpdir):
    """"""
    datadir = os.path.join(os.path.dirname(__file__), "data/fileset")

    copytree(
        os.path.join(datadir, "test1"), 
        os.path.join(tmpdir, "test1"))

    class ConsumeFilesParams(BaseModel):
        files : Union[str,List[Any]] = """
        ${{ in | jq('[ .[] | select(.type == "std.FileSet") ]') }}
        """

    @task(ConsumeFilesParams)
    async def consume_files(runner, input) -> TaskDataResult:
        print("consume_files: %s (%s)" % (str(input.params.files), str(type(input.params.files))))

        fs_l = json.loads(input.params.files)
        fs = FileSet(**(fs_l[0]))

        return TaskDataResult(
            output=[fs]
        )
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "test1", "flow.dv"))
    builder = TaskGraphBuilder(
        pkg_def,
        os.path.join(tmpdir, "rundir"))
    files1 = builder.mkTaskNode("test1.files1")
    cfiles = consume_files(builder, srcdir="srcdir", needs=[files1])

    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(cfiles))

def test_glob_sys(tmpdir):
    flow_dv = """
package:
  name: p1

  tasks:
  - name: glob
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
      incdirs: ["srcdir"]
"""

    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    with open(os.path.join(rundir, "top.sv"), "w") as fp:
        fp.write("\n")
    
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskNode("p1.glob")
    output = asyncio.run(runner.run(task))

    print("output: %s" % str(output))

    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.files) == 1
    assert fs.files[0] == "top.sv"

def test_fileset_base_absolute(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    abs_base = os.path.join(rundir, "absdir")
    os.makedirs(abs_base)
    with open(os.path.join(abs_base, "file.sv"), "w") as fp:
        fp.write("// abs file\n")
    flow_dv = f'''
package:
  name: abs_pkg
  tasks:
  - name: abs
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "{abs_base}"
      include: "*.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("abs_pkg.abs")
    output = asyncio.run(runner.run(task))
    fs = output.output[0]
    assert len(fs.files) == 1
    assert fs.files[0] == "file.sv"

def test_fileset_base_glob_single(tmpdir):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    glob_base = os.path.join(rundir, "globdir")
    os.makedirs(glob_base)
    with open(os.path.join(glob_base, "leaf"), "w") as fp:
        fp.write("// leaf file\n")
    flow_dv = f'''
package:
  name: glob_pkg
  tasks:
  - name: glob
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "{rundir}/glob*/leaf"
      include: ""
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("glob_pkg.glob")
    output = asyncio.run(runner.run(task))
    fs = output.output[0]
    assert fs.basedir.endswith("leaf")

def test_fileset_base_glob_multiple(tmpdir, caplog):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    for i in range(2):
        glob_base = os.path.join(rundir, f"globdir{i}")
        os.makedirs(glob_base)
        with open(os.path.join(glob_base, "leaf"), "w") as fp:
            fp.write("// leaf file\n")
    flow_dv = f'''
package:
  name: glob_pkg
  tasks:
  - name: glob
    uses: std.FileSet
    with:
      type: systemVerilogSource
      base: "{rundir}/globdir*/leaf"
      include: ""
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("glob_pkg.glob")
    with caplog.at_level("ERROR"):
        output = asyncio.run(runner.run(task))
    assert runner.status != 0
    assert any("Multiple directories match glob pattern" in r.message for r in caplog.records)

def test_fileset_attributes_list(tmpdir):
    """Test FileSet with attributes as a list"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    with open(os.path.join(rundir, "file1.sv"), "w") as fp:
        fp.write("// test file\n")
    
    flow_dv = '''
package:
  name: attr_pkg
  tasks:
  - name: with_attrs
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
      attributes:
        - "key1=value1"
        - "key2=value2"
        - "standalone_attr"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("attr_pkg.with_attrs")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.attributes) == 3
    assert "key1=value1" in fs.attributes
    assert "key2=value2" in fs.attributes
    assert "standalone_attr" in fs.attributes

def test_fileset_attributes_string(tmpdir):
    """Test FileSet with attributes as a space-separated string"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    with open(os.path.join(rundir, "file2.sv"), "w") as fp:
        fp.write("// test file\n")
    
    flow_dv = '''
package:
  name: attr_str_pkg
  tasks:
  - name: with_attrs_str
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
      attributes: "attr1=val1 attr2=val2 attr3"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("attr_str_pkg.with_attrs_str")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.attributes) == 3
    assert "attr1=val1" in fs.attributes
    assert "attr2=val2" in fs.attributes
    assert "attr3" in fs.attributes

def test_fileset_no_attributes(tmpdir):
    """Test FileSet without attributes (backward compatibility)"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    with open(os.path.join(rundir, "file3.sv"), "w") as fp:
        fp.write("// test file\n")
    
    flow_dv = '''
package:
  name: no_attr_pkg
  tasks:
  - name: no_attrs
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("no_attr_pkg.no_attrs")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.attributes) == 0

def test_fileset_attributes_key_value_pairs(tmpdir):
    """Test FileSet with various key=value attribute formats"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    with open(os.path.join(rundir, "file4.sv"), "w") as fp:
        fp.write("// test file\n")
    
    flow_dv = '''
package:
  name: kv_pkg
  tasks:
  - name: key_value_attrs
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
      attributes:
        - "sim_only=true"
        - "optimization=O3"
        - "language_version=2017"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("kv_pkg.key_value_attrs")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.attributes) == 3
    assert "sim_only=true" in fs.attributes
    assert "optimization=O3" in fs.attributes
    assert "language_version=2017" in fs.attributes

def test_fileset_multiple_include_patterns(tmpdir):
    """Test FileSet with multiple include patterns"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create test files
    with open(os.path.join(rundir, "file1.sv"), "w") as fp:
        fp.write("// file1.sv\n")
    with open(os.path.join(rundir, "file2.v"), "w") as fp:
        fp.write("// file2.v\n")
    with open(os.path.join(rundir, "file3.sv"), "w") as fp:
        fp.write("// file3.sv\n")
    with open(os.path.join(rundir, "file4.txt"), "w") as fp:
        fp.write("// file4.txt\n")
    
    flow_dv = '''
package:
  name: multi_include_pkg
  tasks:
  - name: multi_include
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "*.sv"
        - "*.v"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("multi_include_pkg.multi_include")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.files) == 3
    assert "file1.sv" in fs.files
    assert "file2.v" in fs.files
    assert "file3.sv" in fs.files
    assert "file4.txt" not in fs.files

def test_fileset_multiple_include_specific_files(tmpdir):
    """Test FileSet with multiple specific file includes (no wildcards)"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create test files
    with open(os.path.join(rundir, "fileA.sv"), "w") as fp:
        fp.write("// fileA.sv\n")
    with open(os.path.join(rundir, "fileB.sv"), "w") as fp:
        fp.write("// fileB.sv\n")
    with open(os.path.join(rundir, "fileC.sv"), "w") as fp:
        fp.write("// fileC.sv\n")
    
    flow_dv = '''
package:
  name: specific_files_pkg
  tasks:
  - name: specific_files
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "fileA.sv"
        - "fileB.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("specific_files_pkg.specific_files")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.files) == 2
    assert "fileA.sv" in fs.files
    assert "fileB.sv" in fs.files
    assert "fileC.sv" not in fs.files

def test_fileset_multiple_include_with_subdirs(tmpdir):
    """Test FileSet with multiple include patterns from subdirectories"""
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create test files in subdirectories
    subdir1 = os.path.join(rundir, "sub1")
    subdir2 = os.path.join(rundir, "sub2")
    os.makedirs(subdir1)
    os.makedirs(subdir2)
    
    with open(os.path.join(subdir1, "mod1.sv"), "w") as fp:
        fp.write("// mod1.sv\n")
    with open(os.path.join(subdir2, "mod2.sv"), "w") as fp:
        fp.write("// mod2.sv\n")
    with open(os.path.join(rundir, "other.sv"), "w") as fp:
        fp.write("// other.sv\n")
    
    flow_dv = '''
package:
  name: subdir_include_pkg
  tasks:
  - name: subdir_includes
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "sub1/mod1.sv"
        - "sub2/mod2.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    task = builder.mkTaskNode("subdir_include_pkg.subdir_includes")
    output = asyncio.run(runner.run(task))
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    assert len(fs.files) == 2
    assert "sub1/mod1.sv" in fs.files
    assert "sub2/mod2.sv" in fs.files
    assert "other.sv" not in fs.files

def test_fileset_debug_two_specific_files(tmpdir, caplog):
    """Debug test: two specific files with detailed logging"""
    import logging
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create exactly two specific files
    with open(os.path.join(rundir, "design.sv"), "w") as fp:
        fp.write("// design file\n")
    with open(os.path.join(rundir, "testbench.sv"), "w") as fp:
        fp.write("// testbench file\n")
    
    flow_dv = '''
package:
  name: debug_pkg
  tasks:
  - name: two_files
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "design.sv"
        - "testbench.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    
    with caplog.at_level(logging.DEBUG, logger="FileSet"):
        task = builder.mkTaskNode("debug_pkg.two_files")
        output = asyncio.run(runner.run(task))
    
    # Print debug info
    print("\nDebug log messages:")
    for record in caplog.records:
        if record.name == "FileSet":
            print(f"  {record.message}")
    
    assert runner.status == 0
    assert len(output.output) == 1
    fs = output.output[0]
    print(f"\nFileset files: {fs.files}")
    print(f"Number of files: {len(fs.files)}")
    
    assert len(fs.files) == 2, f"Expected 2 files, got {len(fs.files)}: {fs.files}"
    assert "design.sv" in fs.files
    assert "testbench.sv" in fs.files

def test_fileset_nonexistent_file_error(tmpdir, caplog):
    """Test FileSet errors when an include pattern matches no files"""
    import logging
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create only one file
    with open(os.path.join(rundir, "exists.sv"), "w") as fp:
        fp.write("// exists\n")
    
    flow_dv = '''
package:
  name: error_pkg
  tasks:
  - name: missing_file
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "exists.sv"
        - "does_not_exist.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    
    with caplog.at_level(logging.ERROR, logger="FileSet"):
        task = builder.mkTaskNode("error_pkg.missing_file")
        output = asyncio.run(runner.run(task))
    
    # Should fail with status=1 (runner returns None on failure)
    assert runner.status == 1
    assert output is None
    
    # Check error was logged
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) >= 1
    assert "does_not_exist.sv" in error_records[0].message
    assert "did not match any files" in error_records[0].message

def test_fileset_all_files_missing_error(tmpdir, caplog):
    """Test FileSet errors when all include patterns match nothing"""
    import logging
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    flow_dv = '''
package:
  name: all_missing_pkg
  tasks:
  - name: all_missing
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "missing1.sv"
        - "missing2.v"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    
    with caplog.at_level(logging.ERROR, logger="FileSet"):
        task = builder.mkTaskNode("all_missing_pkg.all_missing")
        output = asyncio.run(runner.run(task))
    
    # Should fail with status=1
    assert runner.status == 1
    assert output is None
    
    # Should have error logs for both patterns
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) >= 2
    error_messages = [r.message for r in error_records]
    assert any("missing1.sv" in msg for msg in error_messages)
    assert any("missing2.v" in msg for msg in error_messages)

def test_fileset_wildcard_no_match_error(tmpdir, caplog):
    """Test FileSet errors when wildcard pattern matches no files"""
    import logging
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create a file that won't match the pattern
    with open(os.path.join(rundir, "readme.txt"), "w") as fp:
        fp.write("readme\n")
    
    flow_dv = '''
package:
  name: wildcard_pkg
  tasks:
  - name: no_match
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include: "*.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    
    with caplog.at_level(logging.ERROR, logger="FileSet"):
        task = builder.mkTaskNode("wildcard_pkg.no_match")
        output = asyncio.run(runner.run(task))
    
    # Should fail with status=1
    assert runner.status == 1
    assert output is None
    
    # Check error was logged
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) >= 1
    assert "*.sv" in error_records[0].message
    assert "did not match any files" in error_records[0].message

def test_fileset_partial_match_with_error(tmpdir, caplog):
    """Test FileSet processes matching files but still errors on non-matches"""
    import logging
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir)
    
    # Create some files
    with open(os.path.join(rundir, "file1.sv"), "w") as fp:
        fp.write("// file1\n")
    with open(os.path.join(rundir, "file2.sv"), "w") as fp:
        fp.write("// file2\n")
    
    flow_dv = '''
package:
  name: partial_pkg
  tasks:
  - name: partial_match
    uses: std.FileSet
    with:
      type: systemVerilogSource
      include:
        - "file1.sv"
        - "missing.sv"
        - "file2.sv"
'''
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    pkg_def = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    runner = TaskSetRunner(rundir=rundir)
    
    with caplog.at_level(logging.ERROR, logger="FileSet"):
        task = builder.mkTaskNode("partial_pkg.partial_match")
        output = asyncio.run(runner.run(task))
    
    # Should fail with status=1 due to missing file
    assert runner.status == 1
    assert output is None
    
    # Check error was logged for missing file
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) >= 1
    assert "missing.sv" in error_records[0].message
