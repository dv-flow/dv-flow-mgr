#****************************************************************************
#* cmd_context.py
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
"""Context command - outputs comprehensive project information for LLM agents."""

import json
import logging
import os
from typing import ClassVar, List, Dict, Any, Optional
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..ext_rgy import ExtRgy
from .util import get_rootdir


class CmdContext:
    """Output comprehensive project context for LLM agent consumption.
    
    This command provides all the information an LLM agent needs to understand
    and work with a DV Flow Manager project, including:
    - Project structure
    - Package information
    - Available tasks
    - Available types
    - Configurations
    - Imported packages
    """
    
    _log: ClassVar = logging.getLogger("CmdContext")
    
    def __call__(self, args):
        # Try to load project
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
            if getattr(args, 'json', False):
                print(json.dumps({
                    'error': str(e),
                    'project': None
                }, indent=2))
            else:
                print(f"Error loading project: {e}")
            return 1
        
        if pkg is None:
            if getattr(args, 'json', False):
                print(json.dumps({
                    'error': 'No flow.dv/flow.yaml/flow.toml found',
                    'project': None
                }, indent=2))
            else:
                print("No flow.dv/flow.yaml/flow.toml found in current directory or parent directories")
            return 1
        
        # Build context
        context = self._build_context(pkg, loader, args)
        
        if getattr(args, 'json', False):
            print(json.dumps(context, indent=2))
        else:
            self._print_text_context(context)
        
        return 0
    
    def _build_context(self, pkg, loader, args) -> Dict[str, Any]:
        """Build comprehensive project context."""
        include_imports = getattr(args, 'imports', False)
        include_installed = getattr(args, 'installed', False)
        verbose = getattr(args, 'verbose', False)
        
        context = {
            'project': self._get_project_info(pkg),
            'tasks': self._get_tasks_info(pkg, verbose),
            'types': self._get_types_info(pkg, verbose),
            'configs': self._get_configs_info(pkg),
            'imports': self._get_imports_info(pkg),
        }
        
        # Optionally include full import details
        if include_imports and hasattr(pkg, 'pkg_m'):
            context['imported_packages'] = {}
            for name, subpkg in pkg.pkg_m.items():
                context['imported_packages'][name] = {
                    'tasks': list(subpkg.task_m.keys()) if hasattr(subpkg, 'task_m') and subpkg.task_m else [],
                    'types': list(subpkg.type_m.keys()) if hasattr(subpkg, 'type_m') and subpkg.type_m else [],
                }
        
        # Optionally include installed packages
        if include_installed:
            context['installed_packages'] = self._get_installed_packages()
        
        # Add skills info
        context['skills'] = self._get_skills_info(pkg, loader)
        
        return context
    
    def _get_project_info(self, pkg) -> Dict[str, Any]:
        """Get basic project information."""
        info = {
            'name': pkg.name,
            'basedir': getattr(pkg, 'basedir', '') or '',
        }
        
        # Get parameters
        if hasattr(pkg, 'paramT') and pkg.paramT:
            params = {}
            for name in pkg.paramT.model_fields:
                value = getattr(pkg.paramT, name, None)
                params[name] = str(value) if value is not None else None
            if params:
                info['params'] = params
        
        return info
    
    def _get_tasks_info(self, pkg, verbose: bool = False) -> List[Dict[str, Any]]:
        """Get information about tasks in the package."""
        tasks = []
        
        if not hasattr(pkg, 'task_m') or not pkg.task_m:
            return tasks
        
        for task_name, task in pkg.task_m.items():
            # Only include tasks from the root package
            if not task_name.startswith(pkg.name + '.'):
                continue
            
            task_info = {
                'name': task_name,
                'short_name': task_name.split('.')[-1],
                'desc': getattr(task, 'desc', '') or '',
                'scope': [],
            }
            
            # Determine scope
            if getattr(task, 'is_root', False):
                task_info['scope'].append('root')
            if getattr(task, 'is_export', False):
                task_info['scope'].append('export')
            if getattr(task, 'is_local', False):
                task_info['scope'].append('local')
            
            # Get uses (base task)
            if hasattr(task, 'uses') and task.uses:
                task_info['uses'] = task.uses.name if hasattr(task.uses, 'name') else str(task.uses)
            
            # Get needs
            needs = []
            for need in getattr(task, 'needs', []) or []:
                if need is None:
                    continue
                if hasattr(need, 'name'):
                    needs.append(need.name)
                elif isinstance(need, tuple) and len(need) > 0:
                    needs.append(need[0].name if hasattr(need[0], 'name') else str(need[0]))
            if needs:
                task_info['needs'] = needs
            
            if verbose:
                task_info['doc'] = getattr(task, 'doc', '') or ''
                
                # Get parameters
                if hasattr(task, 'param_defs') and task.param_defs:
                    params = {}
                    for name, pdef in task.param_defs.definitions.items():
                        params[name] = {
                            'type': str(task.param_defs.types.get(name, 'any')),
                            'doc': getattr(pdef, 'doc', '') or ''
                        }
                    if params:
                        task_info['params'] = params
            
            tasks.append(task_info)
        
        return sorted(tasks, key=lambda t: t['name'])
    
    def _get_types_info(self, pkg, verbose: bool = False) -> List[Dict[str, Any]]:
        """Get information about types in the package."""
        types = []
        
        if not hasattr(pkg, 'type_m') or not pkg.type_m:
            return types
        
        for type_name, type_obj in pkg.type_m.items():
            # Only include types from the root package
            if not type_name.startswith(pkg.name + '.'):
                continue
            
            type_info = {
                'name': type_name,
                'short_name': type_name.split('.')[-1],
            }
            
            if hasattr(type_obj, 'uses') and type_obj.uses:
                type_info['uses'] = type_obj.uses.name if hasattr(type_obj.uses, 'name') else str(type_obj.uses)
            
            if verbose:
                type_info['doc'] = getattr(type_obj, 'doc', '') or ''
            
            types.append(type_info)
        
        return sorted(types, key=lambda t: t['name'])
    
    def _get_configs_info(self, pkg) -> List[Dict[str, Any]]:
        """Get information about configurations."""
        configs = []
        
        if hasattr(pkg, 'pkg_def') and pkg.pkg_def and hasattr(pkg.pkg_def, 'configs'):
            for config in pkg.pkg_def.configs:
                config_info = {
                    'name': config.name,
                }
                if hasattr(config, 'params') and config.params:
                    config_info['params'] = dict(config.params)
                configs.append(config_info)
        
        return configs
    
    def _get_imports_info(self, pkg) -> List[Dict[str, Any]]:
        """Get information about imports."""
        imports = []
        
        if hasattr(pkg, 'pkg_def') and pkg.pkg_def and hasattr(pkg.pkg_def, 'imports'):
            for imp in pkg.pkg_def.imports:
                import_info = {
                    'name': imp.name if hasattr(imp, 'name') else str(imp),
                }
                if hasattr(imp, 'alias') and imp.alias:
                    import_info['as'] = imp.alias
                imports.append(import_info)
        
        return imports
    
    def _get_installed_packages(self) -> List[str]:
        """Get list of installed packages."""
        rgy = ExtRgy.inst()
        return list(rgy._pkg_m.keys())
    
    def _get_skills_info(self, pkg, loader) -> List[Dict[str, Any]]:
        """Get information about available skills."""
        skills = []
        
        # Import here to avoid circular dependency
        from .show.collectors import SkillCollector
        
        collector = SkillCollector(
            pkg=pkg,
            loader=loader,
            include_installed=True,
            verbose=False
        )
        
        for skill in collector.collect():
            skills.append({
                'name': skill['name'],
                'desc': skill.get('desc', ''),
                'package': skill.get('package', ''),
            })
        
        return skills
    
    def _print_text_context(self, context: Dict[str, Any]):
        """Print context in human-readable format."""
        # Project info
        project = context.get('project', {})
        print(f"Project: {project.get('name', 'unknown')}")
        print(f"  Base directory: {project.get('basedir', 'unknown')}")
        
        if project.get('params'):
            print("  Parameters:")
            for name, value in project['params'].items():
                print(f"    {name}: {value}")
        
        print()
        
        # Tasks
        tasks = context.get('tasks', [])
        print(f"Tasks ({len(tasks)}):")
        for task in tasks:
            scope_str = f" [{', '.join(task.get('scope', []))}]" if task.get('scope') else ""
            print(f"  {task['name']}{scope_str}")
            if task.get('desc'):
                print(f"    {task['desc']}")
            if task.get('needs'):
                print(f"    needs: {', '.join(task['needs'])}")
        
        print()
        
        # Types
        types = context.get('types', [])
        if types:
            print(f"Types ({len(types)}):")
            for t in types:
                uses_str = f" (uses: {t['uses']})" if t.get('uses') else ""
                print(f"  {t['name']}{uses_str}")
        
        # Configs
        configs = context.get('configs', [])
        if configs:
            print(f"\nConfigurations ({len(configs)}):")
            for config in configs:
                print(f"  {config['name']}")
        
        # Imports
        imports = context.get('imports', [])
        if imports:
            print(f"\nImports ({len(imports)}):")
            for imp in imports:
                alias_str = f" as {imp['as']}" if imp.get('as') else ""
                print(f"  {imp['name']}{alias_str}")
        
        # Skills
        skills = context.get('skills', [])
        if skills:
            print(f"\nAvailable Skills ({len(skills)}):")
            for skill in skills:
                print(f"  {skill['name']}: {skill.get('desc', '')}")
