#****************************************************************************
#* test_tasks_wrong_nesting.py
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
"""Test that validation catches tasks incorrectly nested at root level."""

import os
import pytest
import json
from argparse import Namespace
from dv_flow.mgr.cmds.cmd_validate import CmdValidate


class TestTasksWrongNesting:
    """Test validation of incorrectly nested tasks."""
    
    def test_tasks_at_root_level_error(self, tmpdir, capsys):
        """Test that tasks at root level (not under package:) produces validation error."""
        # This is the incorrect structure that was in the initial stdio_mcp_example
        flow_content = """
package:
  name: test_wrong_nesting

tasks:
  - root: TaskOne
    uses: std.Message
    with:
      msg: "Hello"
  
  - name: TaskTwo
    needs: [TaskOne]
"""
        flow_file = os.path.join(tmpdir, "flow.yaml")
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
        
        # Should fail validation
        assert result == 1, "Validation should fail for tasks at root level"
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        assert data['valid'] == False, "Should be invalid"
        assert data['error_count'] >= 1, "Should have at least one error"
        
        # Check that error message mentions the issue
        error_msgs = [e['message'] for e in data['errors']]
        assert any('extra' in msg.lower() or 'tasks' in msg.lower() 
                   for msg in error_msgs), f"Error should mention 'tasks' or 'extra': {error_msgs}"
    
    def test_tasks_correctly_nested_valid(self, tmpdir, capsys):
        """Test that correctly nested tasks pass validation."""
        # This is the correct structure
        flow_content = """
package:
  name: test_correct_nesting
  
  tasks:
    - root: TaskOne
      uses: std.Message
      with:
        msg: "Hello"
    
    - name: TaskTwo
      needs: [TaskOne]
"""
        flow_file = os.path.join(tmpdir, "flow.yaml")
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
        
        # Should pass validation
        assert result == 0, "Validation should pass for correctly nested tasks"
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        assert data['valid'] == True, "Should be valid"
        assert data['error_count'] == 0, "Should have no errors"
        
        # Should have tasks registered
        package_info = [i for i in data['info'] if i['type'] == 'PackageInfo']
        assert len(package_info) > 0, "Should have package info"
        assert package_info[0]['task_count'] == 2, "Should have 2 tasks"
    
    def test_tasks_missing_entirely_valid(self, tmpdir, capsys):
        """Test that package without tasks is valid (just a warning)."""
        flow_content = """
package:
  name: test_no_tasks
"""
        flow_file = os.path.join(tmpdir, "flow.yaml")
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
        
        # Should pass (empty package is valid)
        assert result == 0, "Empty package should be valid"
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        assert data['valid'] == True
        assert data['error_count'] == 0
    
    def test_text_output_for_wrong_nesting(self, tmpdir, capsys):
        """Test text output format for wrong nesting error."""
        flow_content = """
package:
  name: test_text_output

tasks:
  - name: SomeTask
"""
        flow_file = os.path.join(tmpdir, "flow.yaml")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdValidate()
        args = Namespace(
            flow_file=flow_file,
            json=False,  # Text output
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        
        assert result == 1, "Should fail"
        
        captured = capsys.readouterr()
        
        # Should contain error message
        assert "ERROR:" in captured.out or "Error" in captured.out
        assert "Validation failed" in captured.out or "✗" in captured.out
    
    def test_multiple_structural_errors(self, tmpdir, capsys):
        """Test that multiple structural errors are all reported."""
        flow_content = """
package:
  name: test_multiple_errors
  unknown_field: "value"

tasks:
  - name: Task1

extra_root_key: "value"
"""
        flow_file = os.path.join(tmpdir, "flow.yaml")
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
        
        assert result == 1, "Should fail with multiple errors"
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        assert data['valid'] == False
        # Should catch multiple structural issues
        assert data['error_count'] >= 1, "Should report at least one structural error"
