#****************************************************************************
#* test_show_skills.py
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
"""Tests for the dfm show skills command."""

import json
import os
import pytest
from argparse import Namespace
from io import StringIO
from unittest.mock import patch

from dv_flow.mgr.cmds.show.cmd_show_skills import CmdShowSkills
from dv_flow.mgr.cmds.show.collectors import SkillCollector
from dv_flow.mgr import PackageLoader


class TestCmdShowSkills:
    """Test the CmdShowSkills command."""
    
    def test_show_skills_basic(self, capsys):
        """Test basic skill listing without arguments."""
        cmd = CmdShowSkills()
        args = Namespace(
            name=None,
            search=None,
            package=None,
            full=False,
            json=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        # Should list at least std.AgentSkill
        assert 'std.AgentSkill' in captured.out or 'No skills found' in captured.out
    
    def test_show_skills_json(self, capsys):
        """Test JSON output format."""
        cmd = CmdShowSkills()
        args = Namespace(
            name=None,
            search=None,
            package=None,
            full=False,
            json=True,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        # Should be valid JSON
        data = json.loads(captured.out)
        assert 'command' in data
        assert data['command'] == 'show skills'
        assert 'results' in data
        assert 'count' in data
        assert isinstance(data['results'], list)
    
    def test_show_skills_specific_skill(self, capsys):
        """Test showing a specific skill."""
        cmd = CmdShowSkills()
        args = Namespace(
            name='std.AgentSkill',
            search=None,
            package=None,
            full=False,
            json=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        assert 'std.AgentSkill' in captured.out or 'Skill' in captured.out
    
    def test_show_skills_full_doc(self, capsys):
        """Test showing full documentation for a skill."""
        cmd = CmdShowSkills()
        args = Namespace(
            name='std.AgentSkill',
            search=None,
            package=None,
            full=True,
            json=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        # Should show documentation
        assert 'std.AgentSkill' in captured.out
        # Should show full doc content
        assert 'agent' in captured.out.lower() or 'skill' in captured.out.lower()
    
    def test_show_skills_package_filter(self, capsys):
        """Test filtering by package."""
        cmd = CmdShowSkills()
        args = Namespace(
            name=None,
            search=None,
            package='std',
            full=False,
            json=True,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        # All results should be from 'std' package
        for skill in data['results']:
            assert skill['package'] == 'std'
    
    def test_show_skills_not_found(self, capsys):
        """Test showing a skill that doesn't exist."""
        cmd = CmdShowSkills()
        args = Namespace(
            name='nonexistent.Skill',
            search=None,
            package=None,
            full=False,
            json=False,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 1  # Should fail
        
        captured = capsys.readouterr()
        assert 'not found' in captured.out


class TestSkillCollector:
    """Test the SkillCollector class."""
    
    def test_collector_finds_std_skill(self):
        """Test that collector finds the std.AgentSkill."""
        collector = SkillCollector(
            pkg=None,
            loader=None,
            include_installed=True,
            verbose=False
        )
        
        skills = collector.collect()
        
        # Should find at least std.AgentSkill
        skill_names = [s['name'] for s in skills]
        assert 'std.AgentSkill' in skill_names
    
    def test_collector_finds_hdlsim_skills(self):
        """Test that collector finds hdlsim package skills."""
        collector = SkillCollector(
            pkg=None,
            loader=None,
            include_installed=True,
            verbose=False
        )
        
        skills = collector.collect()
        skill_names = [s['name'] for s in skills]
        
        # Should find hdlsim skills if package is properly installed
        # This is conditional since hdlsim is an optional dependency
        if any('hdlsim' in name for name in skill_names):
            assert 'hdlsim.vlt.AgentSkill' in skill_names
            assert 'hdlsim.vcs.AgentSkill' in skill_names
            assert 'hdlsim.xsm.AgentSkill' in skill_names
            assert 'hdlsim.mti.AgentSkill' in skill_names
        else:
            # If hdlsim isn't available, at least verify std.AgentSkill exists
            assert 'std.AgentSkill' in skill_names
    
    def test_collector_verbose_mode(self):
        """Test that verbose mode includes skill_doc."""
        collector = SkillCollector(
            pkg=None,
            loader=None,
            include_installed=True,
            verbose=True
        )
        
        skills = collector.collect()
        
        # In verbose mode, should include skill_doc
        for skill in skills:
            if skill['name'] == 'std.AgentSkill':
                assert 'skill_doc' in skill or 'uses' in skill
    
    def test_collector_is_default_flag(self):
        """Test that is_default flag is set correctly."""
        collector = SkillCollector(
            pkg=None,
            loader=None,
            include_installed=True,
            verbose=False
        )
        
        skills = collector.collect()
        
        for skill in skills:
            if skill['short_name'] == 'AgentSkill':
                assert skill['is_default'] == True
            else:
                assert skill['is_default'] == False


class TestProjectSkills:
    """Test skills defined in project flow.dv files."""
    
    def test_project_skill_detection(self, tmpdir):
        """Test that skills defined in a project are detected."""
        flow_content = """
package:
  name: test_project
  
  types:
    - name: MySkill
      uses: std.AgentSkill
      doc: |
        Test skill for unit testing.
      with:
        files:
          type: list
          value: []
        content:
          type: str
          value: "A test skill"
        urls:
          type: list
          value: []
"""
        flow_file = os.path.join(tmpdir, "flow.dv")
        with open(flow_file, "w") as f:
            f.write(flow_content)
        
        # Load the package
        loader = PackageLoader(marker_listeners=[], param_overrides={})
        pkg = loader.load(flow_file)
        
        # Collect skills
        collector = SkillCollector(
            pkg=pkg,
            loader=loader,
            include_installed=False,  # Only project skills
            verbose=True
        )
        
        skills = collector.collect()
        
        # Should find MySkill
        skill_names = [s['name'] for s in skills]
        assert 'test_project.MySkill' in skill_names
        
        # Check skill properties
        my_skill = next(s for s in skills if s['name'] == 'test_project.MySkill')
        assert my_skill['desc'] == "A test skill"


class TestSkillSearch:
    """Test skill search functionality."""
    
    def test_search_by_keyword(self, capsys):
        """Test searching skills by keyword."""
        cmd = CmdShowSkills()
        args = Namespace(
            name=None,
            search='agent',
            package=None,
            full=False,
            json=True,
            verbose=False,
            param_overrides=[],
            config=None,
            root=None
        )
        
        result = cmd(args)
        assert result == 0
        
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        
        # All results should match 'agent' keyword
        for skill in data['results']:
            search_text = f"{skill['name']} {skill.get('desc', '')} {skill.get('skill_doc', '')}".lower()
            assert 'agent' in search_text
