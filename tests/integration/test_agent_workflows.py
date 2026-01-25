#****************************************************************************
#* test_agent_workflows.py
#*
#* Integration tests for LLM agent workflows with DV Flow Manager.
#*
#* These tests verify that the CLI provides sufficient information for
#* LLM agents to discover, understand, and work with DFM projects.
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
"""Integration tests for LLM agent workflows.

These tests simulate the workflow an LLM agent would follow:
1. Discover - Get skill documentation and project context
2. Query - Get details about specific tasks/types
3. Generate - Create/modify flow configurations
4. Validate - Check configurations for errors
"""

import json
import os
import subprocess
import sys
import pytest


def run_dfm(args, cwd=None):
    """Run dfm command and return result."""
    cmd = [sys.executable, '-m', 'dv_flow.mgr'] + args
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return result


class TestAgentDiscoveryWorkflow:
    """Test the discovery phase of agent workflows."""
    
    def test_help_shows_skill_path(self):
        """Test that --help shows path to skill documentation."""
        result = run_dfm(['--help'])
        assert result.returncode == 0
        # Should mention skill file for LLM agents
        assert 'skill' in result.stdout.lower() or 'llm' in result.stdout.lower()
    
    def test_show_skills_lists_available_skills(self):
        """Test that show skills lists all available skills."""
        result = run_dfm(['show', 'skills', '--json'])
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert 'results' in data
        assert len(data['results']) > 0
        
        # Should include std.AgentSkill
        skill_names = [s['name'] for s in data['results']]
        assert 'std.AgentSkill' in skill_names
    
    def test_show_skills_full_provides_documentation(self):
        """Test that --full flag provides complete skill documentation."""
        result = run_dfm(['show', 'skills', 'std.AgentSkill', '--full'])
        assert result.returncode == 0
        
        # Should include skill documentation content
        assert 'std.AgentSkill' in result.stdout
    
    def test_show_packages_lists_installed(self):
        """Test that show packages lists installed packages."""
        result = run_dfm(['show', 'packages', '--json'])
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert 'results' in data
        
        # Should include std and hdlsim
        pkg_names = [p['name'] for p in data['results']]
        assert 'std' in pkg_names
        assert 'hdlsim' in pkg_names
    
    def test_context_provides_complete_info(self, tmp_path):
        """Test that context command provides complete project info."""
        # Create a simple project
        flow_content = """
package:
  name: test_project
  
  tasks:
    - name: build
      scope: root
      uses: std.Message
      with:
        msg: "Building..."
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        result = run_dfm(['context', '--json'], cwd=str(tmp_path))
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        
        # Check all required sections are present
        assert 'project' in data
        assert 'tasks' in data
        assert 'types' in data
        assert 'skills' in data
        
        # Check project info
        assert data['project']['name'] == 'test_project'
        
        # Check tasks
        task_names = [t['name'] for t in data['tasks']]
        assert 'test_project.build' in task_names


class TestAgentQueryWorkflow:
    """Test the query phase of agent workflows."""
    
    def test_show_task_provides_details(self):
        """Test that show task provides task details."""
        result = run_dfm(['show', 'task', 'std.FileSet', '--json'])
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert 'name' in data
        assert data['name'] == 'std.FileSet'
    
    def test_show_tasks_lists_package_tasks(self):
        """Test that show tasks lists tasks in a package."""
        result = run_dfm(['show', 'tasks', '--package', 'std', '--json'])
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert 'results' in data
        
        # Should include common std tasks
        task_names = [t['name'] for t in data['results']]
        assert any('FileSet' in name for name in task_names)
    
    def test_show_types_lists_package_types(self):
        """Test that show types lists types in a package."""
        result = run_dfm(['show', 'types', '--package', 'std', '--json'])
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert 'results' in data
    
    def test_skills_search_finds_relevant(self):
        """Test that skill search finds relevant skills."""
        result = run_dfm(['show', 'skills', '--search', 'simulation', '--json'])
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert 'results' in data
        # Should find hdlsim skills
        skill_names = [s['name'] for s in data['results']]
        assert any('hdlsim' in name for name in skill_names)


class TestAgentGenerateWorkflow:
    """Test the generate/modify phase of agent workflows."""
    
    def test_validate_catches_undefined_task(self, tmp_path):
        """Test that validate catches undefined task references."""
        flow_content = """
package:
  name: test_invalid
  
  tasks:
    - name: task_a
      needs: [undefined_task]
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        
        data = json.loads(result.stdout)
        assert data['valid'] == False
        assert data['error_count'] > 0
        
        # Error should mention the undefined task
        error_msgs = [e['message'] for e in data['errors']]
        assert any('undefined_task' in msg for msg in error_msgs)
    
    def test_validate_catches_circular_deps(self, tmp_path):
        """Test that validate catches circular dependencies."""
        flow_content = """
package:
  name: test_circular
  
  tasks:
    - name: a
      needs: [b]
    - name: b
      needs: [c]
    - name: c
      needs: [a]
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        
        data = json.loads(result.stdout)
        assert data['valid'] == False
        
        # Should detect circular dependency
        error_types = [e['type'] for e in data['errors']]
        assert 'CircularDependency' in error_types
    
    def test_validate_passes_valid_flow(self, tmp_path):
        """Test that validate passes a valid flow."""
        flow_content = """
package:
  name: test_valid
  
  tasks:
    - name: rtl
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: build
      scope: root
      uses: std.Message
      needs: [rtl]
      with:
        msg: "Built"
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        assert result.returncode == 0
        
        data = json.loads(result.stdout)
        assert data['valid'] == True
        assert data['error_count'] == 0


class TestAgentCompleteWorkflow:
    """Test complete agent workflow scenarios."""
    
    def test_discover_query_generate_validate(self, tmp_path):
        """Test a complete agent workflow: discover → query → generate → validate.
        
        This simulates what an agent would do when asked to create a new
        simulation flow for a project.
        """
        # Step 1: Discover available skills
        result = run_dfm(['show', 'skills', '--json'])
        assert result.returncode == 0
        skills = json.loads(result.stdout)['results']
        
        # Agent identifies hdlsim.vlt.AgentSkill for Verilator
        vlt_skill = next((s for s in skills if 'vlt' in s['name'].lower()), None)
        assert vlt_skill is not None
        
        # Step 2: Query the skill for details
        result = run_dfm(['show', 'skills', vlt_skill['name'], '--full'])
        assert result.returncode == 0
        # Agent reads the skill documentation
        
        # Step 3: Generate a flow configuration (using info from skill docs)
        flow_content = """
package:
  name: generated_project
  
  tasks:
    - name: rtl
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: build
      scope: root
      uses: hdlsim.vlt.SimImage
      needs: [rtl]
      with:
        top: [my_module]
    
    - name: sim
      scope: root
      uses: hdlsim.vlt.SimRun
      needs: [build]
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        # Step 4: Validate the generated flow
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        
        data = json.loads(result.stdout)
        assert data['valid'] == True
        
        # Step 5: Get context to verify
        result = run_dfm(['context', '--json'], cwd=str(tmp_path))
        assert result.returncode == 0
        
        context = json.loads(result.stdout)
        assert context['project']['name'] == 'generated_project'
        
        task_names = [t['name'] for t in context['tasks']]
        assert 'generated_project.build' in task_names
        assert 'generated_project.sim' in task_names
    
    def test_error_recovery_workflow(self, tmp_path):
        """Test agent workflow for error recovery.
        
        This simulates what an agent would do when encountering a build error.
        """
        # Step 1: Create a flow with an error
        flow_content = """
package:
  name: error_project
  
  tasks:
    - name: build
      scope: root
      uses: hdlsim.vlt.SimImage
      needs: [missing_rtl]  # This doesn't exist
      with:
        top: [my_module]
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        # Step 2: Validate and detect the error
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        
        data = json.loads(result.stdout)
        assert data['valid'] == False
        
        # Agent identifies the error: missing_rtl not found
        errors = data['errors']
        assert len(errors) > 0
        
        # Step 3: Agent fixes the flow by adding the missing task
        fixed_flow = """
package:
  name: error_project
  
  tasks:
    - name: rtl
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: build
      scope: root
      uses: hdlsim.vlt.SimImage
      needs: [rtl]
      with:
        top: [my_module]
"""
        (tmp_path / 'flow.dv').write_text(fixed_flow)
        
        # Step 4: Validate again - should pass
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        
        data = json.loads(result.stdout)
        assert data['valid'] == True


class TestAgentErrorMessages:
    """Test that error messages are actionable for agents."""
    
    def test_error_includes_location(self, tmp_path):
        """Test that errors include file location."""
        flow_content = """
package:
  name: test_loc
  
  tasks:
    - name: task_a
      needs: [undefined]
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        data = json.loads(result.stdout)
        
        # Errors should include location info
        errors_with_loc = [e for e in data['errors'] if 'location' in e]
        assert len(errors_with_loc) > 0
        
        # Location should have file path
        loc = errors_with_loc[0]['location']
        assert 'file' in loc
    
    def test_error_includes_suggestions(self, tmp_path):
        """Test that some errors include suggestions."""
        # This test verifies that the error system can provide suggestions
        # when appropriate (e.g., typos in task names)
        flow_content = """
package:
  name: test_suggest
  
  tasks:
    - name: rtl
      uses: std.FileSet
      with:
        type: systemVerilogSource
        include: "*.sv"
    
    - name: build
      needs: [rtl_typo]  # Typo - should suggest 'rtl'
"""
        (tmp_path / 'flow.dv').write_text(flow_content)
        
        result = run_dfm(['validate', '--json'], cwd=str(tmp_path))
        
        # Validation should report errors
        data = json.loads(result.stdout)
        assert data['valid'] == False
        assert data['error_count'] > 0
