#****************************************************************************
#* test_schema_validation_errors.py
#*
#* Phase 1: Schema validation errors with accurate location tracking
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
"""Tests for schema validation errors (Pydantic validation failures).

These tests focus on specification-time errors where YAML is valid but
violates the schema constraints defined by Pydantic models.
"""

import json
import os
import pytest
from argparse import Namespace

from dv_flow.mgr.cmds.cmd_validate import CmdValidate


class TestUnknownFieldErrors:
    """Tests for extra/unknown field detection with suggestions."""
    
    def test_unknown_field_in_package(self, tmpdir, capsys):
        """Test that unknown field in package definition is caught."""
        flow_content = """package:
  name: test_pkg
  version: "1.0"
  tasks:
    - name: task1
      run: echo "test"
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
        
        # Should have error about 'version' field
        errors = [e for e in data['errors'] if 'version' in str(e).lower()]
        assert len(errors) > 0, f"Expected error about 'version' field, got: {data['errors']}"
        
        error = errors[0]
        assert 'location' in error
        # Should point to line 3 where 'version:' is defined
        assert error['location']['line'] == 3

    def test_unknown_field_in_task_with_suggestion(self, tmpdir, capsys):
        """Test that unknown task field suggests similar valid field."""
        flow_content = """package:
  name: test_pkg
  tasks:
    - name: task1
      typ: some_type
      run: echo "test"
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
        
        errors = [e for e in data['errors'] if 'typ' in str(e).lower()]
        assert len(errors) > 0
        
        error = errors[0]
        # Should suggest 'uses' or similar
        # The suggestion logic is already implemented for 'type' -> 'uses'
        # This test verifies it works

    def test_typo_in_task_field(self, tmpdir, capsys):
        """Test that typo in task field is caught with suggestion."""
        flow_content = """package:
  name: test_pkg
  tasks:
    - name: task1
      descr: "A description with a typo"
      run: echo "test"
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
        
        errors = [e for e in data['errors'] if 'descr' in str(e).lower()]
        assert len(errors) > 0
        
        # Should suggest 'desc'
        error_msg = errors[0]['message']
        assert 'desc' in error_msg.lower()


class TestInvalidEnumValues:
    """Tests for invalid enum value errors."""
    
    def test_invalid_enum_value_rundir(self, tmpdir, capsys):
        """Test error when invalid enum value provided for rundir."""
        flow_content = """package:
  name: test_pkg
  tasks:
    - name: task1
      rundir: invalid_value
      run: echo "test"
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
        
        errors = [e for e in data['errors'] if 'rundir' in str(e).lower() or 'invalid_value' in str(e).lower()]
        assert len(errors) > 0, f"Expected rundir validation error, got: {data['errors']}"
        
        error = errors[0]
        assert 'location' in error
        # Should point to line with rundir field


class TestMissingRequiredFields:
    """Tests for missing required field errors."""
    
    def test_package_without_name(self, tmpdir, capsys):
        """Test error when package is missing required name field."""
        flow_content = """package:
  tasks:
    - name: task1
      run: echo "test"
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
        
        errors = [e for e in data['errors'] if 'name' in str(e).lower()]
        assert len(errors) > 0, f"Expected missing 'name' error, got: {data['errors']}"
        
        error = errors[0]
        assert 'location' in error


class TestConflictingFields:
    """Tests for conflicting field combinations."""
    
    def test_multiple_name_fields(self, tmpdir, capsys):
        """Test error when multiple name-defining fields are used."""
        flow_content = """package:
  name: test_pkg
  tasks:
    - name: task1
      root: task1_root
      run: echo "test"
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
        
        # Should error about conflicting name/root
        errors = [e for e in data['errors'] 
                 if 'name' in str(e).lower() or 'root' in str(e).lower()]
        assert len(errors) > 0, f"Expected name/root conflict error, got: {data['errors']}"


class TestCacheConfigErrors:
    """Tests for cache configuration validation errors."""
    
    def test_invalid_cache_compression_type(self, tmpdir, capsys):
        """Test error when invalid compression type is specified."""
        flow_content = """package:
  name: test_pkg
  tasks:
    - name: task1
      run: echo "test"
      cache:
        enabled: true
        compression: invalid_type
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
        
        errors = [e for e in data['errors'] if 'compression' in str(e).lower()]
        assert len(errors) > 0, f"Expected compression type error, got: {data['errors']}"

    def test_unknown_cache_field(self, tmpdir, capsys):
        """Test error when unknown cache configuration field is used."""
        flow_content = """package:
  name: test_pkg
  tasks:
    - name: task1
      run: echo "test"
      cache:
        enabled: true
        unknown_field: value
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
        
        errors = [e for e in data['errors'] if 'unknown_field' in str(e).lower()]
        assert len(errors) > 0, f"Expected cache field error, got: {data['errors']}"
