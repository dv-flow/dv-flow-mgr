#****************************************************************************
#* cmd_show_packages.py
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
"""Show packages sub-command."""

import logging
from typing import ClassVar
from .formatters import TableFormatter, JsonFormatter
from .searcher import Searcher
from .collectors import PackageCollector
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides


class CmdShowPackages:
    """List and search available packages."""
    
    _log: ClassVar = logging.getLogger("CmdShowPackages")
    
    def __call__(self, args):
        # Try to load project context (optional)
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
        
        # Collect packages
        collector = PackageCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=getattr(args, 'verbose', False)
        )
        packages = collector.collect()
        
        # Apply search filters
        searcher = Searcher(
            keyword=getattr(args, 'search', None),
            regex=getattr(args, 'regex', None),
            tag_filter=getattr(args, 'tag', None)
        )
        packages = [p for p in packages if searcher.matches(
            p['name'], p.get('desc', ''), p.get('doc', ''), p.get('tags', [])
        )]
        
        # Sort by name
        packages.sort(key=lambda p: p['name'])
        
        # Format output
        if getattr(args, 'json', False):
            formatter = JsonFormatter('show packages', {
                'search': getattr(args, 'search', None),
                'regex': getattr(args, 'regex', None),
                'tag': getattr(args, 'tag', None),
            })
            formatter.set_results(packages)
            print(formatter.render())
        else:
            if getattr(args, 'verbose', False):
                formatter = TableFormatter(
                    ['Package', 'Source', 'Tasks', 'Types', 'Description'],
                    [25, 10, 6, 6, 40]
                )
                for p in packages:
                    formatter.add_row([
                        p['name'],
                        p.get('source', ''),
                        str(p.get('task_count', '-')),
                        str(p.get('type_count', '-')),
                        (p.get('desc', '') or '')[:40]
                    ])
            else:
                formatter = TableFormatter(['Package', 'Description'], [30, 50])
                for p in packages:
                    formatter.add_row([p['name'], p.get('desc', '') or ''])
            formatter.print()
        
        return 0
