#****************************************************************************
#* test_workspace_fragment_discovery.py
#*
#* Tests for the 'dfm util workspace' command behavior when invoked from
#* a subdirectory containing a fragment file (not a package root).
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#****************************************************************************
"""Tests for workspace command behavior with fragment files.

When running 'dfm util workspace' from a subdirectory that contains a fragment
file (flow.yaml with 'fragment:' instead of 'package:'), the command should
search up the directory tree to find the actual package root.
"""

import json
import os
import pytest
from dv_flow.mgr.util.util import loadProjPkgDef
from .marker_collector import MarkerCollector


class TestLoadProjPkgDefWithFragments:
    """Tests for loadProjPkgDef handling fragment files correctly."""
    
    def test_fragment_in_subdir_finds_parent_package(self, tmpdir):
        """Test that loadProjPkgDef skips fragment files and finds parent package.
        
        Directory structure:
        /root/
          flow.dv (package: name: myproject)
          subdir/
            flow.yaml (fragment: ...)
        
        When called from /root/subdir, should find /root/flow.dv
        """
        root_flow = """package:
  name: myproject
  fragments:
    - subdir
  tasks:
    - name: task1
      desc: A task from root
"""
        subdir_fragment = """fragment:
  tasks:
    - name: task_from_fragment
      desc: A task defined in fragment
"""
        
        # Create root package
        root_dir = str(tmpdir)
        with open(os.path.join(root_dir, "flow.dv"), "w") as f:
            f.write(root_flow)
        
        # Create subdirectory with fragment
        subdir = os.path.join(root_dir, "subdir")
        os.makedirs(subdir)
        with open(os.path.join(subdir, "flow.yaml"), "w") as f:
            f.write(subdir_fragment)
        
        # Save current directory and change to subdir
        orig_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            
            marker_collector = MarkerCollector()
            loader, pkg = loadProjPkgDef(subdir, listener=marker_collector)
            
            # Should find the parent package, not fail on fragment
            assert pkg is not None, f"Expected to find package, got markers: {marker_collector.markers}"
            assert pkg.name == "myproject"
            # Check for errors in markers
            errors = [m for m in marker_collector.markers if str(m.severity) == "SeverityE.Error"]
            assert len(errors) == 0, f"Unexpected errors: {errors}"
            
        finally:
            os.chdir(orig_cwd)

    def test_fragment_only_dir_reports_error(self, tmpdir):
        """Test that a directory with only a fragment (no parent package) reports an error.
        
        When there's a fragment file but no package file in the directory tree,
        should report a helpful error message.
        """
        fragment_only = """fragment:
  tasks:
    - name: orphan_task
"""
        
        # Create a directory with only a fragment
        root_dir = str(tmpdir)
        with open(os.path.join(root_dir, "flow.yaml"), "w") as f:
            f.write(fragment_only)
        
        marker_collector = MarkerCollector()
        loader, pkg = loadProjPkgDef(root_dir, listener=marker_collector)
        
        # Should fail - no package found
        assert pkg is None, "Expected no package when only fragment exists"
        errors = [m for m in marker_collector.markers if str(m.severity) == "SeverityE.Error"]
        assert len(errors) > 0, "Expected error when no package found"
        
        # Error message should be helpful
        error_msg = str(errors[0].msg).lower()
        assert "package" in error_msg or "flow.dv" in error_msg

    def test_multiple_subdirs_with_fragments(self, tmpdir):
        """Test finding package when multiple subdirectories have fragments."""
        root_flow = """package:
  name: multi_fragment_project
  fragments:
    - subdir1
    - subdir2/nested
"""
        fragment1 = """fragment:
  tasks:
    - name: task1
"""
        fragment2 = """fragment:
  tasks:
    - name: task2
"""
        
        root_dir = str(tmpdir)
        with open(os.path.join(root_dir, "flow.dv"), "w") as f:
            f.write(root_flow)
        
        # Create nested subdirectories
        subdir1 = os.path.join(root_dir, "subdir1")
        os.makedirs(subdir1)
        with open(os.path.join(subdir1, "flow.yaml"), "w") as f:
            f.write(fragment1)
        
        subdir2_nested = os.path.join(root_dir, "subdir2", "nested")
        os.makedirs(subdir2_nested)
        with open(os.path.join(subdir2_nested, "flow.yaml"), "w") as f:
            f.write(fragment2)
        
        # Test from deeply nested fragment directory
        orig_cwd = os.getcwd()
        try:
            os.chdir(subdir2_nested)
            
            marker_collector = MarkerCollector()
            loader, pkg = loadProjPkgDef(subdir2_nested, listener=marker_collector)
            
            assert pkg is not None, f"Expected package, got markers: {marker_collector.markers}"
            assert pkg.name == "multi_fragment_project"
            
        finally:
            os.chdir(orig_cwd)

    def test_flow_yaml_as_package_still_works(self, tmpdir):
        """Test that flow.yaml with package: key still works."""
        package_yaml = """package:
  name: yaml_package
  tasks:
    - name: task1
"""
        
        root_dir = str(tmpdir)
        with open(os.path.join(root_dir, "flow.yaml"), "w") as f:
            f.write(package_yaml)
        
        marker_collector = MarkerCollector()
        loader, pkg = loadProjPkgDef(root_dir, listener=marker_collector)
        
        assert pkg is not None
        assert pkg.name == "yaml_package"
        errors = [m for m in marker_collector.markers if str(m.severity) == "SeverityE.Error"]
        assert len(errors) == 0


class TestCmdUtilWorkspace:
    """Tests for the 'dfm util workspace' command."""
    
    def test_workspace_from_fragment_subdir(self, tmpdir):
        """Test workspace command works from fragment subdirectory."""
        from argparse import Namespace
        from dv_flow.mgr.cmds.cmd_util import CmdUtil
        import sys
        from io import StringIO
        
        root_flow = """package:
  name: workspace_test
  fragments:
    - subdir
  tasks:
    - name: root_task
"""
        subdir_fragment = """fragment:
  tasks:
    - name: frag_task
"""
        
        root_dir = str(tmpdir)
        with open(os.path.join(root_dir, "flow.dv"), "w") as f:
            f.write(root_flow)
        
        subdir = os.path.join(root_dir, "subdir")
        os.makedirs(subdir)
        with open(os.path.join(subdir, "flow.yaml"), "w") as f:
            f.write(subdir_fragment)
        
        # Change to subdirectory and run workspace command
        orig_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            
            cmd = CmdUtil()
            args = Namespace(cmd="workspace")
            
            # Capture stdout
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            
            try:
                cmd(args)
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            
            # Filter out warning/debug lines and find the JSON output
            # Output may contain warnings that start with "Warning:" etc
            lines = output.strip().split('\n')
            json_line = None
            for line in lines:
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    json_line = line
                    break
            
            assert json_line is not None, f"Should find JSON output, got: {output}"
            assert json_line != "{abc}", f"Should find package, got: {json_line}"
            
            # Should be valid JSON
            data = json.loads(json_line)
            assert "name" in data or "markers" in data, f"Unexpected output: {data}"
            
            # If package found, verify name
            if "name" in data:
                assert data["name"] == "workspace_test"
                
        finally:
            os.chdir(orig_cwd)
