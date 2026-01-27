#****************************************************************************
#* test_error_marker_locations.py
#*
#* Tests that verify error markers include accurate source locations.
#* These tests ensure the VSCode extension can show errors at the correct line.
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
"""Tests for accurate error marker source locations.

Current behavior: Error markers point to the task definition line (e.g., "- name: task_a")
rather than the specific line where the error occurs (e.g., the "needs:" line).

This is a known limitation documented in these tests. Future improvement would track
source locations for individual fields like `needs`, `uses`, etc.
"""

import json
import os
import pytest
from argparse import Namespace

from dv_flow.mgr.cmds.cmd_validate import CmdValidate


class TestUndefinedTaskReferenceLocation:
    """Tests for undefined task reference error locations."""
    
    def test_undefined_needs_error_has_location(self, tmpdir, capsys):
        """Test that undefined task in needs has file and line information.
        
        Current behavior: Reports the task definition line (line 5), not the needs line (line 7).
        """
        flow_content = """package:
  name: test_loc

  tasks:
    - name: task_a
      desc: A task that references an undefined task
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
        
        # Find the undefined task error
        undefined_errors = [e for e in data['errors'] 
                          if 'undefined_task' in e.get('message', '').lower() 
                          or 'undefined_task' in str(e)]
        
        assert len(undefined_errors) > 0, f"Expected undefined task error, got: {data['errors']}"
        
        error = undefined_errors[0]
        loc = error.get('location', {})
        
        # Verify we have location information
        assert 'file' in loc, "Error should include file path"
        assert 'line' in loc and loc['line'] is not None, "Error should include line number"
        
        # Current behavior: line 5 (task definition)
        # Ideal behavior would be: line 7 (needs line) 
        assert loc['line'] == 5, f"Currently reports task def line 5, got {loc['line']}"

    def test_undefined_needs_multiline_format(self, tmpdir, capsys):
        """Test undefined task in multiline needs format has location.
        
        Current behavior: Reports the task definition line (line 5).
        Ideal: Would report line 9 (the undefined_task list entry).
        """
        flow_content = """package:
  name: test_loc

  tasks:
    - name: task_a
      desc: A task
      needs:
        - valid_task
        - undefined_task
    
    - name: valid_task
      desc: A valid task
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
        
        undefined_errors = [e for e in data['errors'] 
                          if 'undefined_task' in e.get('message', '').lower()
                          or 'undefined_task' in str(e)]
        
        assert len(undefined_errors) > 0, f"Expected undefined task error, got: {data['errors']}"
        
        error = undefined_errors[0]
        loc = error.get('location', {})
        
        # Verify we have location information  
        assert 'line' in loc and loc['line'] is not None, "Error should include line number"
        # Current behavior: reports task definition line 5
        assert loc['line'] == 5, f"Currently reports task def line 5, got {loc['line']}"


class TestUsesReferenceLocation:
    """Tests for undefined uses reference error locations."""
    
    def test_undefined_uses_error_has_location(self, tmpdir, capsys):
        """Test that undefined uses has location information.
        
        Current behavior: Reports task definition line (line 5).
        Note: 'uses' is often on a different line than 'name'.
        """
        flow_content = """package:
  name: test_loc

  tasks:
    - name: task_a
      uses: NonExistentBaseTask
      desc: A task with undefined base
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
        
        # Find uses-related error
        uses_errors = [e for e in data['errors'] 
                      if 'uses' in e.get('message', '').lower()
                      or 'NonExistentBaseTask' in str(e)]
        
        assert len(uses_errors) > 0, f"Expected uses error, got: {data['errors']}"
        
        error = uses_errors[0]
        loc = error.get('location', {})
        
        assert 'line' in loc and loc['line'] is not None, "Error should include line number"
        # Current behavior: line 5 (task definition)
        assert loc['line'] == 5, f"Currently reports task def line 5, got {loc['line']}"


class TestMarkerLocationAccuracy:
    """Tests verifying marker locations match the actual error position."""
    
    def test_error_has_line_and_column(self, tmpdir, capsys):
        """Test that errors include both line and column information."""
        flow_content = """package:
  name: test_loc

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
        
        errors_with_location = [e for e in data['errors'] if 'location' in e]
        
        # Verify at least one error has location info
        assert len(errors_with_location) > 0, "Expected at least one error with location"
        
        loc = errors_with_location[0]['location']
        assert 'file' in loc, "Location should include file"
        assert 'line' in loc, "Location should include line"
        # Column is included
        assert 'column' in loc, "Location should include column"

    def test_multiple_errors_have_distinct_locations(self, tmpdir, capsys):
        """Test that multiple errors on different tasks have distinct line numbers."""
        # Two undefined tasks on different lines
        flow_content = """package:
  name: test_loc

  tasks:
    - name: task_a
      needs: [undefined_task_1]
    
    - name: task_b
      needs: [undefined_task_2]
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
        
        errors_with_location = [e for e in data['errors'] if 'location' in e and e['location'].get('line')]
        
        # Should have errors for both undefined tasks
        assert len(errors_with_location) >= 2, f"Expected at least 2 errors with location, got {len(errors_with_location)}"
        
        # The lines should be different (one for each task definition)
        lines = sorted([e['location']['line'] for e in errors_with_location])
        
        # task_a is on line 5, task_b is on line 8
        assert lines == [5, 8], f"Expected error lines [5, 8], got {lines}"

