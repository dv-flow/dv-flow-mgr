#****************************************************************************
#* test_cmd_context.py
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
"""Tests for the dfm context command."""

import json
import os
import pytest
from argparse import Namespace

from dv_flow.mgr.cmds.cmd_context import CmdContext


class TestCmdContext:
    """Test the CmdContext command."""
    
    def test_context_basic(self, tmpdir, capsys):
        """Test basic context output."""
        flow_content = """
package:
  name: test_context
  
  tasks:
    - name: build
      scope: root
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=False,
            imports=False,
            installed=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        assert 'test_context' in captured.out
        assert 'build' in captured.out
    
    def test_context_json_output(self, tmpdir, capsys):
        """Test JSON context output."""
        flow_content = """
package:
  name: test_json_context
  
  with:
    param1:
      type: str
      value: "default"
  
  tasks:
    - name: task1
      scope: root
    
    - name: task2
      needs: [task1]
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=False,
            installed=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Check required fields
        assert 'project' in data
        assert 'tasks' in data
        assert 'types' in data
        assert 'configs' in data
        assert 'imports' in data
        assert 'skills' in data
        
        # Check project info
        assert data['project']['name'] == 'test_json_context'
        
        # Check tasks
        task_names = [t['name'] for t in data['tasks']]
        assert 'test_json_context.task1' in task_names
        assert 'test_json_context.task2' in task_names
    
    def test_context_with_imports(self, tmpdir, capsys):
        """Test context output includes imports info."""
        flow_content = """
package:
  name: test_imports
  
  tasks:
    - name: files
      scope: root
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=True,
            installed=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Check imports
        # There may or may not be imports depending on the flow structure
        # Just verify the imports field exists
        assert 'imports' in data
    
    def test_context_with_installed(self, tmpdir, capsys):
        """Test context output with installed packages."""
        flow_content = """
package:
  name: test_installed
  
  tasks:
    - name: build
      scope: root
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=False,
            installed=True,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Check installed_packages
        assert 'installed_packages' in data
        assert isinstance(data['installed_packages'], list)
        # std should always be installed
        assert 'std' in data['installed_packages']
    
    def test_context_with_configs(self, tmpdir, capsys):
        """Test context output includes configs field."""
        flow_content = """
package:
  name: test_configs
  
  tasks:
    - name: build
      scope: root
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=False,
            installed=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Check configs field exists
        assert 'configs' in data
        assert isinstance(data['configs'], list)
    
    def test_context_includes_skills(self, tmpdir, capsys):
        """Test context output includes skills."""
        flow_content = """
package:
  name: test_skills
  
  tasks:
    - name: build
      scope: root
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=False,
            installed=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Check skills
        assert 'skills' in data
        assert isinstance(data['skills'], list)
        
        # Should include at least std.AgentSkill
        skill_names = [s['name'] for s in data['skills']]
        assert 'std.AgentSkill' in skill_names
    
    def test_context_no_project(self, tmpdir, capsys):
        """Test context when no project is found."""
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=False,
            installed=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=str(tmpdir)  # Empty directory
        )
        
        result = cmd(args)
        assert result == 1
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert 'error' in data
        assert data['project'] is None
    
    def test_context_verbose_includes_docs(self, tmpdir, capsys):
        """Test verbose mode includes documentation."""
        flow_content = """
package:
  name: test_verbose
  
  tasks:
    - name: build
      scope: root
      doc: |
        This is the build task documentation.
        It explains what the task does.
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        cmd = CmdContext()
        args = Namespace(
            json=True,
            imports=False,
            installed=False,
            verbose=True,
            param_overrides=[],
            config=None,
            root=str(tmpdir)
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # Find the build task
        build_task = None
        for task in data['tasks']:
            if task['short_name'] == 'build':
                build_task = task
                break
        
        assert build_task is not None
        assert 'doc' in build_task
        assert 'documentation' in build_task['doc']
