#****************************************************************************
#* prompt_builder.py
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
"""System prompt builder - generates system prompts from agent context."""

import logging
from typing import List, Dict, Any
from .context_builder import AgentContext


class SystemPromptBuilder:
    """Generates system prompt from agent context."""
    
    _log = logging.getLogger("SystemPromptBuilder")
    
    def build_prompt(self, context: AgentContext) -> str:
        """Generate complete system prompt.
        
        Args:
            context: Agent context with skills, personas, tools, references
        
        Returns:
            System prompt as string
        """
        sections = []
        
        # 1. Project Overview
        sections.append(self._build_project_section(context.project_info))
        
        # 2. Available DFM Commands
        sections.append(self._build_dfm_commands_section())
        
        # 3. Skills Section
        if context.skills:
            sections.append(self._build_skills_section(context.skills))
        
        # 4. Persona Section
        if context.personas:
            sections.append(self._build_persona_section(context.personas))
        
        # 5. References Section
        if context.references:
            sections.append(self._build_references_section(context.references))
        
        # 6. Tools Section
        if context.tools:
            sections.append(self._build_tools_section(context.tools))
        
        return "\n\n".join(sections)
    
    def _build_project_section(self, project_info: Dict[str, Any]) -> str:
        """Build project information section."""
        lines = [
            "# DV Flow Manager Project Context",
            "",
            "## Project Information",
            f"- **Name:** {project_info.get('name', 'unknown')}",
        ]
        
        if desc := project_info.get('desc'):
            lines.append(f"- **Description:** {desc}")
        
        if basedir := project_info.get('basedir'):
            lines.append(f"- **Root Directory:** {basedir}")
        
        return "\n".join(lines)
    
    def _build_dfm_commands_section(self) -> str:
        """Build DFM commands section."""
        return """## Available DFM Commands

You have access to the `dfm` command-line tool with these commands:

- **dfm run [tasks...]** - Run workflow tasks
- **dfm show tasks** - List available tasks
- **dfm show task <name>** - Get task details
- **dfm show types** - List available types
- **dfm show skills** - List available agent skills
- **dfm context** - Get full project context in JSON
- **dfm validate** - Validate flow files

When running dfm commands, you can use parameter overrides with `-D NAME=VALUE`."""
    
    def _build_skills_section(self, skills: List[Dict[str, Any]]) -> str:
        """Build skills section."""
        lines = [
            "## Skills",
            "",
            "The following skills are available to assist you:",
            ""
        ]
        
        for skill in skills:
            lines.append(f"### {skill['name']}")
            
            if desc := skill.get('desc'):
                lines.append(f"{desc}")
                lines.append("")
            
            # Include file content
            for file_info in skill.get('files', []):
                lines.append(f"**Skill Documentation from {file_info['path']}:**")
                lines.append("```")
                lines.append(file_info['content'])
                lines.append("```")
                lines.append("")
            
            # Include inline content
            if content := skill.get('content'):
                lines.append(f"**Skill Content:**")
                lines.append("```")
                lines.append(content)
                lines.append("```")
                lines.append("")
            
            # Include URLs
            if urls := skill.get('urls'):
                lines.append("**Additional Resources:**")
                for url in urls:
                    lines.append(f"- {url}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _build_persona_section(self, personas: List[Dict[str, Any]]) -> str:
        """Build persona section."""
        lines = [
            "## Persona",
            "",
            "You should adopt the following persona(s):",
            ""
        ]
        
        for persona in personas:
            if persona_text := persona.get('persona'):
                lines.append(persona_text)
                lines.append("")
            elif desc := persona.get('desc'):
                lines.append(desc)
                lines.append("")
        
        return "\n".join(lines)
    
    def _build_references_section(self, references: List[Dict[str, Any]]) -> str:
        """Build references section."""
        lines = [
            "## Reference Documentation",
            "",
            "The following reference materials are available:",
            ""
        ]
        
        for ref in references:
            lines.append(f"### {ref['name']}")
            
            if desc := ref.get('desc'):
                lines.append(f"{desc}")
                lines.append("")
            
            # Include file content
            for file_info in ref.get('files', []):
                lines.append(f"**From {file_info['path']}:**")
                lines.append("```")
                lines.append(file_info['content'])
                lines.append("```")
                lines.append("")
            
            # Include inline content
            if content := ref.get('content'):
                lines.append(f"**Content:**")
                lines.append("```")
                lines.append(content)
                lines.append("```")
                lines.append("")
            
            # Include URLs
            if urls := ref.get('urls'):
                lines.append("**External References:**")
                for url in urls:
                    lines.append(f"- {url}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _build_tools_section(self, tools: List[Dict[str, Any]]) -> str:
        """Build tools/MCP servers section."""
        lines = [
            "## Available Tools",
            "",
            "The following tools and MCP servers are configured:",
            ""
        ]
        
        for tool in tools:
            lines.append(f"### {tool['name']}")
            
            if desc := tool.get('desc'):
                lines.append(f"{desc}")
                lines.append("")
            
            if command := tool.get('command'):
                lines.append(f"**Command:** `{command}`")
                
                if args := tool.get('args'):
                    args_str = " ".join(args)
                    lines.append(f"**Args:** `{args_str}`")
                
                lines.append("")
            
            if url := tool.get('url'):
                lines.append(f"**URL:** {url}")
                lines.append("")
        
        return "\n".join(lines)
