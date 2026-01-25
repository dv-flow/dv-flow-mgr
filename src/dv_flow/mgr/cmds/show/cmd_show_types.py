#****************************************************************************
#* cmd_show_types.py
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
"""Show types sub-command."""

import logging
from typing import ClassVar
from .formatters import TableFormatter, JsonFormatter
from .searcher import Searcher, filter_by_package
from .collectors import TypeCollector
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides


class CmdShowTypes:
    """List and search data types and tags."""
    
    _log: ClassVar = logging.getLogger("CmdShowTypes")
    
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
        
        # Collect types
        collector = TypeCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=getattr(args, 'verbose', False),
            tags_only=getattr(args, 'tags_only', False),
            data_items_only=getattr(args, 'data_items_only', False)
        )
        types = collector.collect()
        
        # Apply filters
        package_filter = getattr(args, 'package', None)
        if package_filter:
            types = filter_by_package(types, package_filter)
        
        # Apply search filters
        searcher = Searcher(
            keyword=getattr(args, 'search', None),
            regex=getattr(args, 'regex', None),
            tag_filter=None  # Types don't have tags themselves
        )
        types = [t for t in types if searcher.matches(
            t['name'], '', t.get('doc', ''), []
        )]
        
        # Sort by name
        types.sort(key=lambda t: t['name'])
        
        # Format output
        if getattr(args, 'json', False):
            formatter = JsonFormatter('show types', {
                'search': getattr(args, 'search', None),
                'regex': getattr(args, 'regex', None),
                'package': package_filter,
                'tags_only': getattr(args, 'tags_only', False),
                'data_items_only': getattr(args, 'data_items_only', False),
            })
            formatter.set_results(types)
            print(formatter.render())
        else:
            formatter = TableFormatter(
                ['Type', 'Base Type', 'Description'],
                [30, 20, 40]
            )
            for t in types:
                doc = t.get('doc', '') or ''
                if doc:
                    doc = doc.split('\n')[0][:40]
                formatter.add_row([
                    t['name'],
                    t.get('uses', '') or '-',
                    doc
                ])
            formatter.print()
        
        return 0
