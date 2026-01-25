#****************************************************************************
#* cmd_show_project.py
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
"""Show project sub-command."""

import json
import logging
import os
from typing import ClassVar, Dict, Any, List
from .formatters import DetailFormatter
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides


class CmdShowProject:
    """Display information about the current project."""
    
    _log: ClassVar = logging.getLogger("CmdShowProject")
    
    def __call__(self, args):
        # Load project context (required for this command)
        pkg = None
        loader = None
        try:
            loader, pkg = loadProjPkgDef(
                get_rootdir(args),
                parameter_overrides=parse_parameter_overrides(getattr(args, 'param_overrides', [])),
                config=getattr(args, 'config', None)
            )
        except Exception as e:
            print(f"Error: Not in a project directory or could not load project: {e}")
            return 1
        
        if pkg is None:
            print("Error: Not in a project directory")
            return 1
        
        # Build project info
        project_info = self._build_project_info(pkg, loader, args)
        
        # Format output
        if getattr(args, 'json', False):
            print(json.dumps(project_info, indent=2))
        else:
            self._print_project_details(project_info, args)
        
        return 0
    
    def _build_project_info(self, pkg, loader, args) -> Dict[str, Any]:
        """Build project information dict."""
        info = {
            'name': pkg.name,
            'location': getattr(pkg, 'basedir', '') or os.getcwd(),
            'config': getattr(args, 'config', None) or 'default',
        }
        
        # Parameters - Package might not have params attribute
        info['params'] = self._params_to_dict(getattr(pkg, 'params', {}))
        
        # Tasks - Handle Package object (has task_m) with visibility info
        root_tasks = []
        export_tasks = []
        local_tasks = []
        
        if hasattr(pkg, 'task_m') and pkg.task_m:
            for name, task in pkg.task_m.items():
                task_info = {
                    'name': name,
                    'desc': getattr(task, 'desc', '') or '',
                    'uses': task.uses.name if task.uses else None,
                }
                if getattr(task, 'is_root', False):
                    root_tasks.append(task_info)
                elif getattr(task, 'is_export', False):
                    export_tasks.append(task_info)
                elif getattr(task, 'is_local', False):
                    local_tasks.append(task_info)
                else:
                    # Default visibility - treat as export
                    export_tasks.append(task_info)
        else:
            for t in getattr(pkg, 'tasks', []):
                task_info = {
                    'name': f"{pkg.name}.{t.name}",
                    'desc': getattr(t, 'desc', '') or '',
                    'uses': getattr(t, 'uses', None),
                }
                scope = getattr(t, 'scope', None)
                if t.root or (scope and 'root' in scope):
                    root_tasks.append(task_info)
                elif t.export or (scope and 'export' in scope):
                    export_tasks.append(task_info)
                elif t.local or (scope and 'local' in scope):
                    local_tasks.append(task_info)
                else:
                    export_tasks.append(task_info)
        
        info['root_tasks'] = root_tasks
        info['export_tasks'] = export_tasks
        info['local_tasks'] = local_tasks
        info['tasks'] = [t['name'] for t in root_tasks + export_tasks + local_tasks]
        info['task_count'] = len(info['tasks'])
        
        # Types
        if hasattr(pkg, 'type_m') and pkg.type_m:
            types = list(pkg.type_m.keys())
        else:
            types = [t.name for t in getattr(pkg, 'types', [])]
        info['types'] = types
        info['type_count'] = len(types)
        
        # Imports
        if getattr(args, 'imports', False) or getattr(args, 'verbose', False):
            info['imports'] = self._get_imports(pkg)
        else:
            info['import_count'] = len(getattr(pkg, 'imports', []))
        
        # Configs
        if getattr(args, 'configs', False) or getattr(args, 'verbose', False):
            info['configs'] = [{'name': c.name} for c in getattr(pkg, 'configs', [])]
        else:
            info['config_count'] = len(getattr(pkg, 'configs', []))
        
        return info
    
    def _params_to_dict(self, params) -> Dict[str, Dict[str, Any]]:
        """Convert params to dict format."""
        if not params:
            return {}
        result = {}
        for name, value in params.items():
            if isinstance(value, dict):
                result[name] = value
            elif hasattr(value, 'type'):
                result[name] = {
                    'type': str(value.type) if value.type else 'any',
                    'value': value.value if hasattr(value, 'value') else '',
                }
            else:
                result[name] = {'value': value}
        return result
    
    def _get_imports(self, pkg) -> List[Dict[str, Any]]:
        """Get import information."""
        imports = []
        pkg_imports = getattr(pkg, 'imports', []) or []
        for imp in pkg_imports:
            if isinstance(imp, str):
                imports.append({'path': imp})
            else:
                imports.append({
                    'path': imp.path if hasattr(imp, 'path') else str(imp),
                    'alias': getattr(imp, 'alias', None),
                    'config': getattr(imp, 'config', None),
                })
        return imports
    
    def _print_project_details(self, info: Dict[str, Any], args):
        """Print project details in human-readable format."""
        from .formatters import is_terminal
        
        formatter = DetailFormatter()
        
        formatter.add_field("Project", info['name'])
        formatter.add_field("Location", info['location'])
        formatter.add_field("Config", info['config'])
        
        formatter.add_params("Parameters", info.get('params', {}))
        
        # Print header fields first
        formatter.print()
        
        # Root tasks (runnable) - show prominently with descriptions
        root_tasks = info.get('root_tasks', [])
        if is_terminal():
            from rich.console import Console
            console = Console()
            
            if root_tasks:
                console.print("[bold cyan]Runnable Tasks (root):[/bold cyan]")
                for t in root_tasks:
                    desc = t.get('desc', '')
                    if desc:
                        console.print(f"  [green]*[/green] {t['name']}: {desc}")
                    else:
                        console.print(f"  [green]*[/green] {t['name']}")
            else:
                console.print("[bold cyan]Runnable Tasks (root):[/bold cyan] [dim](none)[/dim]")
        else:
            if root_tasks:
                print("Runnable Tasks (root):")
                for t in root_tasks:
                    desc = t.get('desc', '')
                    if desc:
                        print(f"  * {t['name']}: {desc}")
                    else:
                        print(f"  * {t['name']}")
            else:
                print("Runnable Tasks (root): (none)")
        
        # Other tasks
        export_tasks = info.get('export_tasks', [])
        local_tasks = info.get('local_tasks', [])
        
        if getattr(args, 'verbose', False):
            if export_tasks:
                print("\nOther Tasks:")
                for t in export_tasks:
                    desc = t.get('desc', '')
                    if desc:
                        print(f"    {t['name']}: {desc}")
                    else:
                        print(f"    {t['name']}")
            if local_tasks:
                print("\nLocal Tasks:")
                for t in local_tasks:
                    print(f"    {t['name']}")
        else:
            other_count = len(export_tasks) + len(local_tasks)
            if other_count > 0:
                other_preview = ', '.join([t['name'] for t in export_tasks[:6]])
                if len(export_tasks) > 6:
                    other_preview += ', ...'
                print(f"\nOther Tasks: {other_count}: {other_preview}")
        
        # Imports
        if 'imports' in info:
            import_strs = []
            for imp in info['imports']:
                s = imp.get('path', '')
                if imp.get('alias'):
                    s += f" as {imp['alias']}"
                if imp.get('config'):
                    s += f" (config: {imp['config']})"
                import_strs.append(s)
            print(f"Imported Packages: {', '.join(import_strs)}")
        else:
            print(f"Imported Packages: {info.get('import_count', 0)}")
        
        # Configs
        if 'configs' in info:
            config_names = [c['name'] for c in info['configs']]
            print(f"Configurations: {', '.join(config_names)}")
        else:
            print(f"Configurations: {info.get('config_count', 0)}")
