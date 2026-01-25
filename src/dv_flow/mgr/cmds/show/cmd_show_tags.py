#****************************************************************************
#* cmd_show_tags.py
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
"""Show tags sub-command."""

import logging
from typing import ClassVar, Dict, List, Any
from .formatters import TableFormatter, JsonFormatter
from .searcher import Searcher
from .collectors import TypeCollector, TaskCollector
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides


class CmdShowTags:
    """List available tag types and their usage."""
    
    _log: ClassVar = logging.getLogger("CmdShowTags")
    
    def __call__(self, args):
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
        
        # Collect tag types (types deriving from std.Tag)
        type_collector = TypeCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=getattr(args, 'verbose', False),
            tags_only=True
        )
        tag_types = type_collector.collect()
        
        # Count tag usage across tasks
        usage_counts = self._count_tag_usage(pkg, loader, tag_types)
        
        # Apply search filters
        searcher = Searcher(
            keyword=getattr(args, 'search', None),
            regex=getattr(args, 'regex', None),
            tag_filter=None
        )
        tag_types = [t for t in tag_types if searcher.matches(
            t['name'], '', t.get('doc', ''), []
        )]
        
        # Sort by name
        tag_types.sort(key=lambda t: t['name'])
        
        # Add usage counts to results
        for t in tag_types:
            t['usage_count'] = usage_counts.get(t['name'], 0)
        
        # Format output
        if getattr(args, 'json', False):
            formatter = JsonFormatter('show tags', {
                'search': getattr(args, 'search', None),
            })
            formatter.set_results(tag_types)
            print(formatter.render())
        else:
            formatter = TableFormatter(
                ['Tag Type', 'Base', 'Usage', 'Description'],
                [30, 15, 6, 35]
            )
            for t in tag_types:
                doc = t.get('doc', '') or ''
                if doc:
                    doc = doc.split('\n')[0][:35]
                formatter.add_row([
                    t['name'],
                    t.get('uses', '') or '-',
                    str(t.get('usage_count', 0)),
                    doc
                ])
            formatter.print()
        
        return 0
    
    def _count_tag_usage(self, pkg, loader, tag_types: List[Dict]) -> Dict[str, int]:
        """Count how many tasks/packages use each tag type."""
        counts: Dict[str, int] = {t['name']: 0 for t in tag_types}
        
        # Get all tasks
        task_collector = TaskCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=False
        )
        tasks = task_collector.collect()
        
        # Count tag usage
        for task in tasks:
            for tag in task.get('tags', []):
                tag_name = self._extract_tag_name(tag)
                if tag_name in counts:
                    counts[tag_name] += 1
                # Also check for partial matches
                for full_name in counts.keys():
                    if full_name.endswith('.' + tag_name) or full_name == tag_name:
                        counts[full_name] += 1
                        break
        
        return counts
    
    def _extract_tag_name(self, tag: Any) -> str:
        """Extract tag type name from various representations."""
        if isinstance(tag, str):
            return tag
        elif isinstance(tag, dict):
            return list(tag.keys())[0] if tag else ''
        else:
            return getattr(tag, 'name', str(tag))
