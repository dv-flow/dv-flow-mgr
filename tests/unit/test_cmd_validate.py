#****************************************************************************
#* test_cmd_validate.py
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
"""Tests for the dfm validate command."""

import json
import os
import pytest
from argparse import Namespace

from dv_flow.mgr.cmds.cmd_validate import CmdValidate


class TestCmdValidate:
    """Test the CmdValidate command."""
    
    def test_validate_valid_flow(self, tmpdir, capsys):
        """Test validation of a valid flow file."""
        flow_content = """
package:
  name: test_valid
  
  tasks:
    - name: build
      scope: root
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        assert "Validation passed" in captured.out
    
    def test_validate_undefined_task(self, tmpdir, capsys):
        """Test validation catches undefined task references."""
        flow_content = """
package:
  name: test_undefined
  
  tasks:
    - name: task_a
      needs: [undefined_task]
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 1  # Should fail
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['valid'] == False
        assert data['error_count'] >= 1
        
        # Check that error mentions undefined task
        error_msgs = [e['message'] for e in data['errors']]
        assert any('undefined_task' in msg for msg in error_msgs)
    
    def test_validate_circular_dependency(self, tmpdir, capsys):
        """Test validation catches circular dependencies."""
        flow_content = """
package:
  name: test_circular
  
  tasks:
    - name: task_a
      needs: [task_b]
    
    - name: task_b
      needs: [task_c]
    
    - name: task_c
      needs: [task_a]
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 1
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['valid'] == False
        
        # Check for circular dependency error
        error_types = [e['type'] for e in data['errors']]
        assert 'CircularDependency' in error_types
    
    def test_validate_unused_task_warning(self, tmpdir, capsys):
        """Test validation warns about unused tasks."""
        flow_content = """
package:
  name: test_unused
  
  tasks:
    - name: used_task
      scope: root
    
    - name: unused_task
      doc: This task is not referenced
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0  # Warnings don't cause failure
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['valid'] == True
        assert data['warning_count'] >= 1
        
        # Check for unused task warning
        warning_types = [w['type'] for w in data['warnings']]
        assert 'UnusedTask' in warning_types
    
    def test_validate_json_output_structure(self, tmpdir, capsys):
        """Test JSON output has correct structure."""
        flow_content = """
package:
  name: test_json
  
  tasks:
    - name: build
      scope: root
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Check required fields
        assert 'valid' in data
        assert 'errors' in data
        assert 'warnings' in data
        assert 'info' in data
        assert 'error_count' in data
        assert 'warning_count' in data
        
        # Check types
        assert isinstance(data['valid'], bool)
        assert isinstance(data['errors'], list)
        assert isinstance(data['warnings'], list)
        assert isinstance(data['info'], list)
    
    def test_validate_no_package_found(self, tmpdir, capsys):
        """Test validation when no flow file is found."""
        cmd = CmdValidate()
        args = Namespace(
            flow_file=None,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)  # Empty directory
        )
        
        result = cmd(args)
        assert result == 1
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['valid'] == False
        assert data['error_count'] >= 1
    
    def test_validate_with_valid_needs(self, tmpdir, capsys):
        """Test validation passes with valid task dependencies."""
        flow_content = """
package:
  name: test_needs
  
  tasks:
    - name: rtl
      scope: root
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: build
      scope: root
      needs: [rtl]
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data['valid'] == True
        assert data['error_count'] == 0


class TestValidationErrorLocations:
    """Test that validation errors include source locations."""
    
    def test_error_includes_file_location(self, tmpdir, capsys):
        """Test that errors include file and line information."""
        flow_content = """
package:
  name: test_location
  
  tasks:
    - name: task_a
      needs: [undefined_task]
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Find error with location
        errors_with_location = [e for e in data['errors'] if 'location' in e]
        assert len(errors_with_location) > 0
        
        # Check location has file info
        loc = errors_with_location[0]['location']
        assert 'file' in loc
        assert flow_file in loc['file'] or 'flow.dv' in loc['file']
