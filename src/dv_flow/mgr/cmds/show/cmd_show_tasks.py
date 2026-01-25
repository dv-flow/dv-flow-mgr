#****************************************************************************
#* cmd_show_tasks.py
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
"""Show tasks sub-command."""

import logging
from typing import ClassVar
from .formatters import TableFormatter, JsonFormatter
from .searcher import Searcher, filter_by_scope, filter_by_package
from .collectors import TaskCollector
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides


class CmdShowTasks:
    """List and search tasks across packages."""
    
    _log: ClassVar = logging.getLogger("CmdShowTasks")
    
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
        
        # Collect tasks
        collector = TaskCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=getattr(args, 'verbose', False)
        )
        tasks = collector.collect()
        
        # Apply filters
        package_filter = getattr(args, 'package', None)
        if package_filter:
            tasks = filter_by_package(tasks, package_filter)
        
        scope_filter = getattr(args, 'scope', None)
        if scope_filter:
            tasks = filter_by_scope(tasks, scope_filter)
        
        # Apply search filters
        searcher = Searcher(
            keyword=getattr(args, 'search', None),
            regex=getattr(args, 'regex', None),
            tag_filter=getattr(args, 'tag', None)
        )
        tasks = [t for t in tasks if searcher.matches(
            t['name'], t.get('desc', ''), t.get('doc', ''), t.get('tags', [])
        )]
        
        # Sort by name
        tasks.sort(key=lambda t: t['name'])
        
        # Format output
        if getattr(args, 'json', False):
            formatter = JsonFormatter('show tasks', {
                'search': getattr(args, 'search', None),
                'regex': getattr(args, 'regex', None),
                'tag': getattr(args, 'tag', None),
                'package': package_filter,
                'scope': scope_filter,
            })
            formatter.set_results(tasks)
            print(formatter.render())
        else:
            if getattr(args, 'verbose', False):
                formatter = TableFormatter(
                    ['Task', 'Base', 'Scope', 'Description'],
                    [35, 20, 10, 30]
                )
                for t in tasks:
                    scope_str = ','.join(t.get('scope', [])) if t.get('scope') else ''
                    formatter.add_row([
                        t['name'],
                        t.get('uses', '') or '',
                        scope_str,
                        (t.get('desc', '') or '')[:30]
                    ])
            else:
                formatter = TableFormatter(['Task', 'Description'], [40, 50])
                for t in tasks:
                    desc = t.get('desc', '') or t.get('doc', '')
                    if desc:
                        desc = desc.split('\n')[0][:50]
                    formatter.add_row([t['name'], desc])
            formatter.print()
        
        return 0
