#****************************************************************************
#* cmd_show_skills.py
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
"""Show skills sub-command - lists and queries agent skills."""

import logging
from typing import ClassVar, Optional
from .formatters import TableFormatter, JsonFormatter, DetailFormatter
from .searcher import Searcher, filter_by_package
from .collectors import SkillCollector
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides


class CmdShowSkills:
    """List and search agent skills defined as DataSet types tagged with AgentSkillTag.
    
    Skills are capabilities that can be discovered and utilized by AI agents.
    Each package can define one or more skills, with 'AgentSkill' being the 
    recommended default skill name.
    """
    
    _log: ClassVar = logging.getLogger("CmdShowSkills")
    
    def __call__(self, args):
        # Get optional specific skill name
        skill_name = getattr(args, 'name', None)
        
        # Try to load project context
        pkg = None
        loader = None
        try:
            loader, pkg = loadProjPkgDef(
                get_rootdir(args),
                parameter_overrides=parse_parameter_overrides(getattr(args, 'param_overrides', [])),
                config=getattr(args, 'config', None)
            )
        except Exception as e:
            self._log.debug(f"No project context: {e}")
        
        # Collect skills
        collector = SkillCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=getattr(args, 'verbose', False) or getattr(args, 'full', False)
        )
        skills = collector.collect()
        
        # If specific skill requested, find it
        if skill_name:
            return self._show_single_skill(args, skills, skill_name)
        
        # Apply filters
        package_filter = getattr(args, 'package', None)
        if package_filter:
            skills = filter_by_package(skills, package_filter)
        
        # Apply search filters
        searcher = Searcher(
            keyword=getattr(args, 'search', None),
            regex=None,
            tag_filter=None
        )
        skills = [s for s in skills if searcher.matches(
            s['name'], s.get('desc', ''), s.get('skill_doc', ''), []
        )]
        
        # Sort by name
        skills.sort(key=lambda s: s['name'])
        
        # Format output
        if getattr(args, 'json', False):
            formatter = JsonFormatter('show skills', {
                'search': getattr(args, 'search', None),
                'package': package_filter,
            })
            formatter.set_results(skills)
            print(formatter.render())
        else:
            if not skills:
                print("No skills found.")
                return 0
            
            # Table view
            formatter = TableFormatter(
                ['Skill', 'Description'],
                [40, 50]
            )
            for s in skills:
                desc = s.get('desc', '') or ''
                if len(desc) > 50:
                    desc = desc[:47] + '...'
                formatter.add_row([s['name'], desc])
            formatter.print()
        
        return 0
    
    def _show_single_skill(self, args, skills, skill_name: str) -> int:
        """Show detailed information for a single skill."""
        # Find the skill
        skill = None
        for s in skills:
            if s['name'] == skill_name:
                skill = s
                break
            # Also match by short name
            if s['name'].endswith('.' + skill_name):
                skill = s
                break
        
        if not skill:
            print(f"Skill '{skill_name}' not found.")
            print("\nAvailable skills:")
            for s in sorted(skills, key=lambda x: x['name']):
                print(f"  {s['name']}")
            return 1
        
        # JSON output
        if getattr(args, 'json', False):
            formatter = JsonFormatter('show skills', {'name': skill_name})
            formatter.set_results([skill])
            print(formatter.render())
            return 0
        
        # Full documentation view
        if getattr(args, 'full', False):
            self._print_full_skill(skill)
        else:
            self._print_skill_summary(skill)
        
        return 0
    
    def _print_skill_summary(self, skill: dict):
        """Print a summary view of the skill."""
        formatter = DetailFormatter()
        formatter.add_field("Skill", skill['name'])
        formatter.add_field("Package", skill.get('package', ''))
        formatter.add_field("Description", skill.get('desc', ''))
        formatter.add_field("Is Default", "Yes" if skill.get('is_default', False) else "No")
        
        formatter.print()
        
        if skill.get('skill_doc'):
            print("\n(Use --full to see complete documentation)")
    
    def _print_full_skill(self, skill: dict):
        """Print full skill documentation."""
        print(f"# {skill['name']}")
        print(f"Package: {skill.get('package', '')}")
        if skill.get('is_default'):
            print("(Default skill for this package)")
        print()
        
        if skill.get('desc'):
            print(f"**{skill['desc']}**")
            print()
        
        if skill.get('skill_doc'):
            print(skill['skill_doc'])
        else:
            print("(No detailed documentation available)")
