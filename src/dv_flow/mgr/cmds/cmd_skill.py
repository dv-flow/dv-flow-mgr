#****************************************************************************
#* cmd_skill.py
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
import os

# Short description of DV Flow Manager for LLM consumption
SKILL_DESCRIPTION = """\
DV Flow Manager (dfm) is a YAML-based build system and execution engine \
designed for silicon design and verification projects. It orchestrates tasks \
through declarative workflows with dataflow-based dependency management.

For detailed information, see the skill documentation at:
{skill_path}
"""

class CmdSkill(object):

    def __call__(self, args):
        # Get the path to skill.md in the share directory
        share_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "share")
        skill_path = os.path.join(share_dir, "skill.md")
        
        print(SKILL_DESCRIPTION.format(skill_path=skill_path))
        
        return 0
