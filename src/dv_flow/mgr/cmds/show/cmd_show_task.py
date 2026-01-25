#****************************************************************************
#* cmd_show_task.py
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
"""Show task detail sub-command."""

import json
import logging
import os
from typing import ClassVar, Optional, Dict, Any, List, Set
from .formatters import DetailFormatter
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides
from ...ext_rgy import ExtRgy


class CmdShowTask:
    """Display detailed information about a specific task."""
    
    _log: ClassVar = logging.getLogger("CmdShowTask")
    
    def __call__(self, args):
        task_name = args.name
        
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
        
        # Find the task
        task_info = self._find_task(task_name, pkg, loader)
        
        if task_info is None:
            print(f"Error: Task '{task_name}' not found")
            return 1
        
        # Get needs chain if requested
        needs_depth = getattr(args, 'needs', None)
        if needs_depth is not None and pkg and loader:
            needs_info = self._get_needs_chain(task_name, pkg, loader, needs_depth)
            task_info['needs_chain'] = needs_info
        
        # Format output
        if getattr(args, 'json', False):
            print(json.dumps(task_info, indent=2))
        else:
            self._print_task_details(task_info, getattr(args, 'verbose', False), 
                                     show_needs_chain=(needs_depth is not None))
        
        return 0
    
    def _find_task(self, task_name: str, pkg, loader) -> Optional[Dict[str, Any]]:
        """Find a task by name."""
        # Parse task name
        if '.' in task_name:
            pkg_name, short_name = task_name.rsplit('.', 1)
        else:
            # Assume project package
            if pkg:
                pkg_name = pkg.name
                short_name = task_name
            else:
                return None
        
        # Search in project package (Package object with task_m)
        if pkg and pkg.name == pkg_name:
            if hasattr(pkg, 'task_m') and pkg.task_m:
                full_task_name = f"{pkg_name}.{short_name}"
                if full_task_name in pkg.task_m:
                    task = pkg.task_m[full_task_name]
                    return self._task_to_info(task, pkg_name)
        
        # Search in installed packages
        rgy = ExtRgy.inst()
        if pkg_name in rgy._pkg_m:
            try:
                provider = rgy._pkg_m[pkg_name]
                # Create loader if needed
                if loader is None:
                    from ...package_loader import PackageLoader
                    loader = PackageLoader(marker_listeners=[], param_overrides={})
                
                loaded_pkg = provider.findPackage(pkg_name, loader)
                if loaded_pkg and hasattr(loaded_pkg, 'task_m') and loaded_pkg.task_m:
                    full_task_name = f"{pkg_name}.{short_name}"
                    if full_task_name in loaded_pkg.task_m:
                        task = loaded_pkg.task_m[full_task_name]
                        return self._task_to_info(task, pkg_name)
            except Exception as e:
                self._log.debug(f"Could not load package {pkg_name}: {e}")
        
        return None
    
    def _task_to_info(self, task, pkg_name: str) -> Dict[str, Any]:
        """Convert Task object to detailed info dict."""
        short_name = task.name.split('.')[-1] if '.' in task.name else task.name
        
        scope = []
        if getattr(task, 'is_root', False):
            scope.append('root')
        if getattr(task, 'is_export', False):
            scope.append('export')
        if getattr(task, 'is_local', False):
            scope.append('local')
        
        # Get description from taskdef if available
        desc = ''
        doc = ''
        if hasattr(task, 'taskdef') and task.taskdef:
            desc = getattr(task.taskdef, 'desc', '') or ''
            doc = getattr(task.taskdef, 'doc', '') or ''
        
        info = {
            'name': task.name,
            'short_name': short_name,
            'package': pkg_name,
            'desc': desc,
            'doc': doc,
            'uses': task.uses.name if hasattr(task, 'uses') and task.uses else None,
            'scope': scope,
            'tags': self._tags_to_list(getattr(task, 'tags', [])),
            'params': self._get_params(task),
            'needs': [n.name if hasattr(n, 'name') else str(n) for n in getattr(task, 'needs', [])],
            'rundir': str(task.rundir.value) if hasattr(task, 'rundir') and task.rundir else 'unique',
            'passthrough': str(task.passthrough) if hasattr(task, 'passthrough') and task.passthrough else None,
            'consumes': str(task.consumes) if hasattr(task, 'consumes') and task.consumes else None,
        }
        
        return info
    
    def _get_params(self, task) -> Dict[str, Dict[str, Any]]:
        """Extract parameters from a task."""
        params = {}
        if hasattr(task, 'param_defs') and task.param_defs:
            for name, pdef in task.param_defs.definitions.items():
                ptype = task.param_defs.types.get(name, 'any')
                params[name] = {
                    'type': str(ptype) if ptype else 'any',
                    'value': pdef.value if hasattr(pdef, 'value') else '',
                    'doc': (pdef.doc or pdef.desc or '') if hasattr(pdef, 'doc') else ''
                }
        return params
    
    def _tags_to_list(self, tags):
        """Convert tags to list."""
        if not tags:
            return []
        result = []
        for tag in tags:
            if isinstance(tag, str):
                result.append(tag)
            elif isinstance(tag, dict):
                result.append(tag)
            else:
                result.append(str(tag))
        return result
    
    def _get_needs_chain(self, task_name: str, pkg, loader, max_depth: int) -> List[Dict[str, Any]]:
        """Get the needs chain for a task using TaskGraphBuilder.
        
        Args:
            task_name: Fully qualified task name
            pkg: The loaded package
            loader: The package loader
            max_depth: Maximum depth to traverse (-1 for unlimited)
        
        Returns:
            List of needs info dicts with structure showing the chain
        """
        from ...task_graph_builder import TaskGraphBuilder
        import toposort
        
        try:
            rundir = os.path.join(pkg.basedir, "rundir")
            builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader)
            
            # Build the task node
            task_node = builder.mkTaskNode(task_name)
            
            # Collect needs recursively
            needs_chain = []
            visited: Set[str] = set()
            
            def collect_needs(node, depth: int) -> List[Dict[str, Any]]:
                if max_depth >= 0 and depth > max_depth:
                    return []
                
                result = []
                for need_tuple in node.needs:
                    need_node = need_tuple[0]  # needs are (node, ...) tuples
                    need_name = need_node.name
                    
                    if need_name in visited:
                        # Already visited, just reference it
                        result.append({
                            'name': need_name,
                            'depth': depth,
                            'circular_ref': True
                        })
                        continue
                    
                    visited.add(need_name)
                    
                    need_info = {
                        'name': need_name,
                        'depth': depth,
                    }
                    
                    # Recursively get sub-needs
                    sub_needs = collect_needs(need_node, depth + 1)
                    if sub_needs:
                        need_info['needs'] = sub_needs
                    
                    result.append(need_info)
                
                return result
            
            visited.add(task_name)
            needs_chain = collect_needs(task_node, 1)
            
            return needs_chain
            
        except Exception as e:
            self._log.debug(f"Error building needs chain: {e}")
            return []
    
    def _print_task_details(self, info: Dict[str, Any], verbose: bool, show_needs_chain: bool = False):
        """Print task details in human-readable format."""
        formatter = DetailFormatter()
        
        formatter.add_field("Task", info['name'])
        formatter.add_field("Package", info['package'])
        formatter.add_field("Base", info.get('uses') or '-')
        
        scope_str = ', '.join(info.get('scope', [])) if info.get('scope') else '-'
        formatter.add_field("Scope", scope_str)
        
        if info.get('desc'):
            formatter.add_section("Description", info['desc'])
        
        if info.get('doc'):
            formatter.add_section("Documentation", info['doc'])
        
        formatter.add_params("Parameters", info.get('params', {}))
        
        if info.get('tags'):
            tag_strs = []
            for tag in info['tags']:
                if isinstance(tag, str):
                    tag_strs.append(tag)
                elif isinstance(tag, dict):
                    for k, v in tag.items():
                        tag_strs.append(f"{k}: {v}")
                else:
                    tag_strs.append(str(tag))
            formatter.add_list("Tags", tag_strs)
        else:
            formatter.add_list("Tags", [])
        
        # Show needs chain if requested
        if show_needs_chain and info.get('needs_chain'):
            formatter.print()
            self._print_needs_chain_header()
            self._print_needs_chain(info['needs_chain'], indent=2)
        else:
            if info.get('needs'):
                formatter.add_list("Direct Needs", info['needs'])
            else:
                formatter.add_list("Direct Needs", [])
            formatter.print()
    
    def _print_needs_chain_header(self):
        """Print the needs chain header."""
        from .formatters import is_terminal
        if is_terminal():
            from rich.console import Console
            console = Console()
            console.print("\n[bold yellow]Needs Chain:[/bold yellow]")
        else:
            print("\nNeeds Chain:")
    
    def _print_needs_chain(self, needs: List[Dict[str, Any]], indent: int = 0):
        """Print the needs chain with indentation showing hierarchy."""
        from .formatters import is_terminal
        
        if is_terminal():
            from rich.console import Console
            console = Console()
            prefix = " " * indent
            for need in needs:
                name = need['name']
                circular = need.get('circular_ref', False)
                
                if circular:
                    console.print(f"{prefix}[green]•[/green] [cyan]{name}[/cyan] [dim](circular ref)[/dim]")
                else:
                    console.print(f"{prefix}[green]•[/green] [cyan]{name}[/cyan]")
                    if need.get('needs'):
                        self._print_needs_chain(need['needs'], indent + 2)
        else:
            prefix = " " * indent
            for need in needs:
                name = need['name']
                circular = need.get('circular_ref', False)
                
                if circular:
                    print(f"{prefix}- {name} (circular ref)")
                else:
                    print(f"{prefix}- {name}")
                    if need.get('needs'):
                        self._print_needs_chain(need['needs'], indent + 2)
