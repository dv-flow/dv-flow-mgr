#****************************************************************************
#* cmd_show_package.py
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
"""Show package detail sub-command."""

import json
import logging
from typing import ClassVar, Optional, Dict, Any
from .formatters import DetailFormatter
from ..util import get_rootdir
from ...util import loadProjPkgDef, parse_parameter_overrides
from ...ext_rgy import ExtRgy


class CmdShowPackage:
    """Display detailed information about a specific package."""
    
    _log: ClassVar = logging.getLogger("CmdShowPackage")
    
    def __call__(self, args):
        pkg_name = args.name
        
        # Try to load project context
        proj_pkg = None
        loader = None
        try:
            loader, proj_pkg = loadProjPkgDef(
                get_rootdir(args),
                parameter_overrides=parse_parameter_overrides(getattr(args, 'param_overrides', [])),
                config=getattr(args, 'config', None)
            )
        except Exception as e:
            self._log.debug(f"No project context: {e}")
        
        # Find the package
        pkg_info = self._find_package(pkg_name, proj_pkg, loader)
        
        if pkg_info is None:
            print(f"Error: Package '{pkg_name}' not found")
            return 1
        
        # Format output
        if getattr(args, 'json', False):
            print(json.dumps(pkg_info, indent=2))
        else:
            self._print_package_details(pkg_info, getattr(args, 'verbose', False))
        
        return 0
    
    def _find_package(self, pkg_name: str, proj_pkg, loader) -> Optional[Dict[str, Any]]:
        """Find a package by name."""
        # Check if it's the project package
        if proj_pkg and proj_pkg.name == pkg_name:
            return self._pkg_to_info(proj_pkg, is_project=True)
        
        # Search in installed packages
        rgy = ExtRgy.inst()
        if pkg_name in rgy._pkg_m:
            try:
                provider = rgy._pkg_m[pkg_name]
                # Create loader if needed
                if loader is None:
                    from ...package_loader import PackageLoader
                    loader = PackageLoader(marker_listeners=[], param_overrides={})
                
                pkg = provider.findPackage(pkg_name, loader)
                if pkg:
                    return self._pkg_to_info(pkg, is_project=False)
                # Fallback to basic info
                return {
                    'name': pkg_name,
                    'basedir': getattr(provider, '_path', ''),
                    'source': 'installed',
                    'tasks': [],
                    'types': [],
                    'configs': [],
                    'params': {},
                }
            except Exception as e:
                self._log.debug(f"Could not load package {pkg_name}: {e}")
        
        return None
    
    def _pkg_to_info(self, pkg, is_project: bool = False) -> Dict[str, Any]:
        """Convert Package or PackageDef to detailed info dict."""
        # Handle Package object (has task_m, type_m)
        if hasattr(pkg, 'task_m'):
            tasks = list(pkg.task_m.keys()) if pkg.task_m else []
            types = list(pkg.type_m.keys()) if hasattr(pkg, 'type_m') and pkg.type_m else []
        else:
            # PackageDef
            tasks = [t.name for t in pkg.tasks] if hasattr(pkg, 'tasks') else []
            types = [t.name for t in pkg.types] if hasattr(pkg, 'types') else []
        
        info = {
            'name': pkg.name,
            'basedir': getattr(pkg, 'basedir', '') or '',
            'source': 'project' if is_project else 'installed',
            'uses': getattr(pkg, 'uses', None),
            'tasks': tasks,
            'types': types,
            'configs': [c.name for c in getattr(pkg, 'configs', [])],
            'imports': [str(i) if isinstance(i, str) else getattr(i, 'path', str(i)) for i in getattr(pkg, 'imports', [])],
            'params': self._params_to_dict(getattr(pkg, 'params', {})),
            'tags': self._tags_to_list(getattr(pkg, 'tags', [])),
        }
        
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
                    'doc': value.doc if hasattr(value, 'doc') else ''
                }
            else:
                result[name] = {'value': value}
        return result
    
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
    
    def _print_package_details(self, info: Dict[str, Any], verbose: bool):
        """Print package details in human-readable format."""
        formatter = DetailFormatter()
        
        formatter.add_field("Package", info['name'])
        formatter.add_field("Base", info.get('uses') or '-')
        formatter.add_field("Location", info.get('basedir') or '-')
        formatter.add_field("Source", info.get('source', '-'))
        
        formatter.add_params("Parameters", info.get('params', {}))
        
        tasks = info.get('tasks', [])
        if verbose:
            formatter.add_list("Tasks", tasks)
        else:
            task_str = f"{len(tasks)} tasks"
            if tasks:
                preview = ', '.join(tasks[:5])
                if len(tasks) > 5:
                    preview += ', ...'
                task_str = f"{len(tasks)}: {preview}"
            formatter.add_field("\nTasks", task_str)
        
        types = info.get('types', [])
        if verbose:
            formatter.add_list("Types", types)
        else:
            type_str = f"{len(types)} types"
            if types:
                preview = ', '.join(types[:5])
                if len(types) > 5:
                    preview += ', ...'
                type_str = f"{len(types)}: {preview}"
            formatter.add_field("Types", type_str)
        
        configs = info.get('configs', [])
        if configs:
            formatter.add_list("Configurations", configs)
        
        imports = info.get('imports', [])
        if imports:
            formatter.add_list("Imports", imports)
        
        formatter.print()
