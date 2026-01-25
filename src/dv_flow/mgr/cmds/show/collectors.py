#****************************************************************************
#* collectors.py
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
"""Data collectors for show commands."""

import logging
from typing import List, Dict, Any, Optional, Set
from ...ext_rgy import ExtRgy
from ...package_def import PackageDef
from ...task_def import TaskDef
from ...type_def import TypeDef


class PackageCollector:
    """Collect package information from registry and project."""
    
    _log = logging.getLogger("PackageCollector")
    
    def __init__(self, 
                 pkg: Optional[Any] = None,  # Can be Package or PackageDef
                 loader=None,
                 include_installed: bool = True,
                 verbose: bool = False):
        self._pkg = pkg
        self._loader = loader
        self._include_installed = include_installed
        self._verbose = verbose
    
    def collect(self) -> List[Dict[str, Any]]:
        """Return list of package info dicts."""
        packages = []
        seen_names: Set[str] = set()
        
        # Project package first (if present)
        if self._pkg:
            info = self._pkg_to_info(self._pkg, is_project=True)
            packages.append(info)
            seen_names.add(self._pkg.name)
        
        # Installed packages from ExtRgy
        if self._include_installed:
            rgy = ExtRgy.inst()
            for name, provider in rgy._pkg_m.items():
                if name in seen_names:
                    continue
                seen_names.add(name)
                
                try:
                    # Try to get package info without full load
                    info = self._provider_to_info(name, provider)
                    packages.append(info)
                except Exception as e:
                    self._log.debug(f"Could not load package {name}: {e}")
                    packages.append({
                        'name': name,
                        'desc': '',
                        'doc': '',
                        'tags': [],
                        'basedir': '',
                        'source': 'installed'
                    })
        
        return packages
    
    def _pkg_to_info(self, pkg, is_project: bool = False) -> Dict[str, Any]:
        """Convert Package or PackageDef to info dict."""
        # Handle Package object (has task_m, type_m)
        if hasattr(pkg, 'task_m'):
            task_count = len(pkg.task_m) if pkg.task_m else 0
            type_count = len(pkg.type_m) if hasattr(pkg, 'type_m') and pkg.type_m else 0
            tasks = list(pkg.task_m.keys()) if pkg.task_m else []
            types = list(pkg.type_m.keys()) if hasattr(pkg, 'type_m') and pkg.type_m else []
        else:
            # PackageDef object
            task_count = len(pkg.tasks) if hasattr(pkg, 'tasks') else 0
            type_count = len(pkg.types) if hasattr(pkg, 'types') else 0
            tasks = [t.name for t in pkg.tasks] if hasattr(pkg, 'tasks') else []
            types = [t.name for t in pkg.types] if hasattr(pkg, 'types') else []
        
        info = {
            'name': pkg.name,
            'desc': getattr(pkg, 'desc', '') or '',  
            'doc': '',   
            'tags': self._tags_to_list(getattr(pkg, 'tags', [])),
            'basedir': getattr(pkg, 'basedir', '') or '',
            'source': 'project' if is_project else 'imported',
            'task_count': task_count,
            'type_count': type_count,
        }
        
        if self._verbose:
            info['params'] = self._params_to_dict(getattr(pkg, 'params', {}))
            info['tasks'] = tasks
            info['types'] = types
            info['configs'] = [c.name for c in getattr(pkg, 'configs', [])]
            info['imports'] = [str(i) for i in getattr(pkg, 'imports', [])]
        
        return info
    
    def _provider_to_info(self, name: str, provider) -> Dict[str, Any]:
        """Convert package provider to info dict."""
        basedir = ''
        desc = ''
        
        if hasattr(provider, '_path'):
            basedir = provider._path
        
        # Try to load the package to get the description
        try:
            if self._loader is not None:
                pkg = provider.findPackage(name, self._loader)
                if pkg:
                    desc = getattr(pkg, 'desc', '') or ''
        except Exception as e:
            self._log.debug(f"Could not load package {name} for description: {e}")
        
        return {
            'name': name,
            'desc': desc,
            'doc': '',
            'tags': [],
            'basedir': basedir,
            'source': 'installed'
        }
    
    def _tags_to_list(self, tags) -> List[Any]:
        """Convert tags to serializable list."""
        if not tags:
            return []
        result = []
        for tag in tags:
            if isinstance(tag, str):
                result.append(tag)
            elif isinstance(tag, dict):
                result.append(tag)
            else:
                # Try to extract meaningful info
                result.append(str(tag))
        return result
    
    def _params_to_dict(self, params) -> Dict[str, Dict[str, Any]]:
        """Convert params to dict format."""
        if not params:
            return {}
        result = {}
        for name, param in params.items():
            if isinstance(param, str):
                result[name] = {'type': 'str', 'value': param}
            elif hasattr(param, 'type'):
                result[name] = {
                    'type': str(param.type) if param.type else 'any',
                    'value': param.value if hasattr(param, 'value') else '',
                    'doc': param.doc if hasattr(param, 'doc') else ''
                }
            else:
                result[name] = {'value': param}
        return result


class TaskCollector:
    """Collect task information from packages."""
    
    _log = logging.getLogger("TaskCollector")
    
    def __init__(self,
                 pkg: Optional[Any] = None,  # Can be Package or PackageDef
                 loader=None,
                 include_installed: bool = True,
                 verbose: bool = False):
        self._pkg = pkg
        self._loader = loader
        self._include_installed = include_installed
        self._verbose = verbose
    
    def collect(self) -> List[Dict[str, Any]]:
        """Return list of task info dicts."""
        tasks = []
        seen: Set[str] = set()
        
        # Project tasks first
        if self._pkg:
            pkg_name = self._pkg.name
            
            # Handle Package object (has task_m)
            if hasattr(self._pkg, 'task_m') and self._pkg.task_m:
                for task_fullname, task in self._pkg.task_m.items():
                    if task_fullname not in seen:
                        seen.add(task_fullname)
                        tasks.append(self._task_to_info(task, pkg_name))
            
            # Handle PackageDef object (has tasks list)
            elif hasattr(self._pkg, 'tasks'):
                for task_def in self._pkg.tasks:
                    fullname = f"{pkg_name}.{task_def.name}"
                    if fullname not in seen:
                        seen.add(fullname)
                        tasks.append(self._task_def_to_info(task_def, pkg_name))
                
                # Also collect from fragments
                for frag in getattr(self._pkg, 'fragment_l', []) or []:
                    for task_def in frag.tasks:
                        fullname = f"{pkg_name}.{task_def.name}"
                        if fullname not in seen:
                            seen.add(fullname)
                            tasks.append(self._task_def_to_info(task_def, pkg_name))
        
        # Installed package tasks
        if self._include_installed:
            rgy = ExtRgy.inst()
            # Create a loader if we don't have one
            loader = self._loader
            if loader is None:
                from ...package_loader import PackageLoader
                loader = PackageLoader(marker_listeners=[], param_overrides={})
            
            for pkg_name, provider in rgy._pkg_m.items():
                # Skip if we already have tasks from this package (project package)
                if self._pkg and pkg_name == self._pkg.name:
                    continue
                try:
                    pkg = provider.findPackage(pkg_name, loader)
                    if pkg and hasattr(pkg, 'task_m') and pkg.task_m:
                        for task_fullname, task in pkg.task_m.items():
                            if task_fullname not in seen:
                                seen.add(task_fullname)
                                tasks.append(self._task_to_info(task, pkg_name))
                except Exception as e:
                    self._log.debug(f"Could not load tasks from {pkg_name}: {e}")
        
        return tasks
    
    def _task_to_info(self, task, pkg_name: str) -> Dict[str, Any]:
        """Convert Task object to info dict."""
        # Extract short name from full name
        short_name = task.name.split('.')[-1] if '.' in task.name else task.name
        
        # Get scope info
        scope = []
        if getattr(task, 'is_root', False):
            scope.append('root')
        if getattr(task, 'is_export', False):
            scope.append('export')
        if getattr(task, 'is_local', False):
            scope.append('local')
        
        # Get description directly from task (desc/doc are set when task is created)
        desc = getattr(task, 'desc', '') or ''
        doc = getattr(task, 'doc', '') or ''
        
        info = {
            'name': task.name,
            'short_name': short_name,
            'package': pkg_name,
            'desc': desc,
            'doc': doc,
            'uses': getattr(task, 'uses', None),
            'scope': scope,
            'tags': self._tags_to_list(getattr(task, 'tags', [])),
        }
        
        if self._verbose:
            # Get params from param_defs if available
            params = {}
            if hasattr(task, 'param_defs') and task.param_defs:
                for name, pdef in task.param_defs.definitions.items():
                    params[name] = {
                        'type': str(task.param_defs.types.get(name, 'any')),
                        'value': pdef.value if hasattr(pdef, 'value') else '',
                        'doc': pdef.doc if hasattr(pdef, 'doc') else ''
                    }
            info['params'] = params
            info['needs'] = [n.name if hasattr(n, 'name') else str(n) for n in getattr(task, 'needs', [])]
        
        return info
    
    def _task_def_to_info(self, task_def: TaskDef, pkg_name: str) -> Dict[str, Any]:
        """Convert TaskDef to info dict."""
        # Determine scope
        scope = task_def.scope
        if isinstance(scope, str):
            scope = [scope]
        elif scope is None:
            scope = []
        
        info = {
            'name': f"{pkg_name}.{task_def.name}",
            'short_name': task_def.name,
            'package': pkg_name,
            'desc': task_def.desc or '',
            'doc': task_def.doc or '',
            'uses': task_def.uses,
            'scope': scope,
            'tags': self._tags_to_list(task_def.tags),
        }
        
        if self._verbose:
            info['params'] = self._params_to_dict(task_def.params)
            info['needs'] = list(task_def.needs) if task_def.needs else []
            info['rundir'] = str(task_def.rundir.value) if task_def.rundir else 'unique'
            info['passthrough'] = str(task_def.passthrough) if task_def.passthrough else None
            info['consumes'] = str(task_def.consumes) if task_def.consumes else None
        
        return info
    
    def _tags_to_list(self, tags) -> List[Any]:
        """Convert tags to serializable list."""
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
    
    def _params_to_dict(self, params) -> Dict[str, Dict[str, Any]]:
        """Convert params to dict format."""
        if not params:
            return {}
        result = {}
        for name, value in params.items():
            if isinstance(value, dict):
                result[name] = value
            else:
                result[name] = {'value': value}
        return result


class TypeCollector:
    """Collect type information from packages."""
    
    _log = logging.getLogger("TypeCollector")
    
    def __init__(self,
                 pkg: Optional[Any] = None,  # Can be Package or PackageDef
                 loader=None,
                 include_installed: bool = True,
                 verbose: bool = False,
                 tags_only: bool = False,
                 data_items_only: bool = False):
        self._pkg = pkg
        self._loader = loader
        self._include_installed = include_installed
        self._verbose = verbose
        self._tags_only = tags_only
        self._data_items_only = data_items_only
    
    def collect(self) -> List[Dict[str, Any]]:
        """Return list of type info dicts."""
        types = []
        seen: Set[str] = set()
        
        # Project types first
        if self._pkg:
            pkg_name = self._pkg.name
            
            # Handle Package object (has type_m)
            if hasattr(self._pkg, 'type_m') and self._pkg.type_m:
                for type_fullname, type_obj in self._pkg.type_m.items():
                    if type_fullname not in seen:
                        info = self._type_to_info(type_obj, pkg_name)
                        if self._should_include(info):
                            seen.add(type_fullname)
                            types.append(info)
            # Handle PackageDef object (has types list)
            elif hasattr(self._pkg, 'types'):
                for type_def in self._pkg.types:
                    fullname = f"{pkg_name}.{type_def.name}"
                    if fullname not in seen:
                        info = self._type_def_to_info(type_def, pkg_name)
                        if self._should_include(info):
                            seen.add(fullname)
                            types.append(info)
        
        # Installed package types
        if self._include_installed:
            rgy = ExtRgy.inst()
            # Create a loader if we don't have one
            loader = self._loader
            if loader is None:
                from ...package_loader import PackageLoader
                loader = PackageLoader(marker_listeners=[], param_overrides={})
            
            for pkg_name, provider in rgy._pkg_m.items():
                # Skip if we already have types from this package
                if self._pkg and pkg_name == self._pkg.name:
                    continue
                try:
                    pkg = provider.findPackage(pkg_name, loader)
                    if pkg and hasattr(pkg, 'type_m') and pkg.type_m:
                        for type_fullname, type_obj in pkg.type_m.items():
                            if type_fullname not in seen:
                                info = self._type_to_info(type_obj, pkg_name)
                                if self._should_include(info):
                                    seen.add(type_fullname)
                                    types.append(info)
                except Exception as e:
                    self._log.debug(f"Could not load types from {pkg_name}: {e}")
        
        return types
    
    def _should_include(self, info: Dict[str, Any]) -> bool:
        """Check if type should be included based on filters."""
        if self._tags_only:
            # Include if derives from std.Tag
            uses = info.get('uses', '')
            return uses and ('Tag' in uses or info.get('name', '').endswith('Tag'))
        if self._data_items_only:
            uses = info.get('uses', '')
            return uses and 'DataItem' in uses
        return True
    
    def _type_to_info(self, type_obj, pkg_name: str) -> Dict[str, Any]:
        """Convert Type object to info dict."""
        short_name = type_obj.name.split('.')[-1] if '.' in type_obj.name else type_obj.name
        
        info = {
            'name': type_obj.name,
            'short_name': short_name,
            'package': pkg_name,
            'uses': type_obj.uses.name if hasattr(type_obj, 'uses') and type_obj.uses else None,
            'doc': getattr(type_obj, 'doc', '') or '',
        }
        
        if self._verbose:
            # Get params from param_defs if available
            params = {}
            if hasattr(type_obj, 'param_defs') and type_obj.param_defs:
                for name, pdef in type_obj.param_defs.definitions.items():
                    ptype = type_obj.param_defs.types.get(name, 'any')
                    params[name] = {
                        'type': str(ptype) if ptype else 'any',
                        'value': pdef.value if hasattr(pdef, 'value') else '',
                        'doc': (pdef.doc or '') if hasattr(pdef, 'doc') else ''
                    }
            info['params'] = params
        
        return info
    
    def _type_def_to_info(self, type_def, pkg_name: str) -> Dict[str, Any]:
        """Convert TypeDef to info dict."""
        info = {
            'name': f"{pkg_name}.{type_def.name}",
            'short_name': type_def.name,
            'package': pkg_name,
            'uses': type_def.uses,
            'doc': type_def.doc or '',
        }
        
        if self._verbose:
            info['params'] = self._params_to_dict(type_def.params)
        
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


class SkillCollector:
    """Collect agent skills - DataSet types tagged with AgentSkillTag.
    
    Skills are capabilities that can be discovered and utilized by AI agents.
    A skill is defined as a type that:
    1. Derives from std.DataSet (or similar) 
    2. Is tagged with std.AgentSkillTag
    3. Has fields: name, desc, skill_doc
    """
    
    _log = logging.getLogger("SkillCollector")
    
    def __init__(self,
                 pkg: Optional[Any] = None,
                 loader=None,
                 include_installed: bool = True,
                 verbose: bool = False):
        self._pkg = pkg
        self._loader = loader
        self._include_installed = include_installed
        self._verbose = verbose
    
    def collect(self) -> List[Dict[str, Any]]:
        """Return list of skill info dicts."""
        skills = []
        seen: Set[str] = set()
        
        # Project skills first
        if self._pkg:
            pkg_name = self._pkg.name
            
            # Handle Package object (has type_m)
            if hasattr(self._pkg, 'type_m') and self._pkg.type_m:
                for type_fullname, type_obj in self._pkg.type_m.items():
                    if type_fullname not in seen and self._is_skill(type_obj):
                        seen.add(type_fullname)
                        skills.append(self._type_to_skill_info(type_obj, pkg_name))
            # Handle PackageDef object (has types list)
            elif hasattr(self._pkg, 'types'):
                for type_def in self._pkg.types:
                    fullname = f"{pkg_name}.{type_def.name}"
                    if fullname not in seen and self._is_skill_def(type_def):
                        seen.add(fullname)
                        skills.append(self._type_def_to_skill_info(type_def, pkg_name))
        
        # Installed package skills
        if self._include_installed:
            rgy = ExtRgy.inst()
            loader = self._loader
            if loader is None:
                from ...package_loader import PackageLoader
                loader = PackageLoader(marker_listeners=[], param_overrides={})
            
            for pkg_name, provider in rgy._pkg_m.items():
                # Skip if we already processed this package
                if self._pkg and pkg_name == self._pkg.name:
                    continue
                try:
                    pkg = provider.findPackage(pkg_name, loader)
                    if pkg and hasattr(pkg, 'type_m') and pkg.type_m:
                        for type_fullname, type_obj in pkg.type_m.items():
                            if type_fullname not in seen and self._is_skill(type_obj):
                                seen.add(type_fullname)
                                skills.append(self._type_to_skill_info(type_obj, pkg_name))
                except Exception as e:
                    self._log.debug(f"Could not load skills from {pkg_name}: {e}")
        
        return skills
    
    def _is_skill(self, type_obj) -> bool:
        """Check if a type object is an agent skill (tagged with AgentSkillTag)."""
        tags = getattr(type_obj, 'tags', [])
        if not tags:
            return False
        
        for tag in tags:
            tag_name = ''
            if isinstance(tag, str):
                tag_name = tag
            elif hasattr(tag, 'name'):
                tag_name = tag.name
            elif hasattr(tag, '__class__'):
                tag_name = tag.__class__.__name__
            
            if 'AgentSkillTag' in tag_name:
                return True
        
        return False
    
    def _is_skill_def(self, type_def: TypeDef) -> bool:
        """Check if a TypeDef is an agent skill."""
        tags = type_def.tags
        if not tags:
            return False
        
        for tag in tags:
            if isinstance(tag, str):
                if 'AgentSkillTag' in tag:
                    return True
            elif isinstance(tag, dict):
                # Check if any key contains AgentSkillTag
                for key in tag.keys():
                    if 'AgentSkillTag' in key:
                        return True
        
        return False
    
    def _type_to_skill_info(self, type_obj, pkg_name: str) -> Dict[str, Any]:
        """Convert Type object to skill info dict."""
        short_name = type_obj.name.split('.')[-1] if '.' in type_obj.name else type_obj.name
        
        # Extract skill fields from params
        desc = ''
        skill_doc = ''
        skill_name = ''
        
        if hasattr(type_obj, 'param_defs') and type_obj.param_defs:
            defs = type_obj.param_defs.definitions
            if 'desc' in defs:
                desc = defs['desc'].value if hasattr(defs['desc'], 'value') else ''
            if 'skill_doc' in defs:
                skill_doc = defs['skill_doc'].value if hasattr(defs['skill_doc'], 'value') else ''
            if 'name' in defs:
                skill_name = defs['name'].value if hasattr(defs['name'], 'value') else ''
        
        # Also check doc field on the type itself
        type_doc = getattr(type_obj, 'doc', '') or ''
        if not desc and type_doc:
            # Use first line of doc as desc
            desc = type_doc.split('\n')[0].strip()
        
        info = {
            'name': type_obj.name,
            'short_name': short_name,
            'package': pkg_name,
            'skill_name': skill_name,
            'desc': desc,
            'is_default': short_name == 'AgentSkill',
        }
        
        if self._verbose:
            info['skill_doc'] = skill_doc or type_doc
            info['uses'] = type_obj.uses.name if hasattr(type_obj, 'uses') and type_obj.uses else None
        
        return info
    
    def _type_def_to_skill_info(self, type_def: TypeDef, pkg_name: str) -> Dict[str, Any]:
        """Convert TypeDef to skill info dict."""
        # Extract skill fields from params
        desc = ''
        skill_doc = ''
        skill_name = ''
        
        params = type_def.params or {}
        for name, param in params.items():
            if name == 'desc':
                if isinstance(param, dict):
                    desc = param.get('value', '')
                elif hasattr(param, 'value'):
                    desc = param.value
            elif name == 'skill_doc':
                if isinstance(param, dict):
                    skill_doc = param.get('value', '')
                elif hasattr(param, 'value'):
                    skill_doc = param.value
            elif name == 'name':
                if isinstance(param, dict):
                    skill_name = param.get('value', '')
                elif hasattr(param, 'value'):
                    skill_name = param.value
        
        # Also use doc from the type def
        type_doc = type_def.doc or ''
        if not desc and type_doc:
            desc = type_doc.split('\n')[0].strip()
        
        info = {
            'name': f"{pkg_name}.{type_def.name}",
            'short_name': type_def.name,
            'package': pkg_name,
            'skill_name': skill_name,
            'desc': desc,
            'is_default': type_def.name == 'AgentSkill',
        }
        
        if self._verbose:
            info['skill_doc'] = skill_doc or type_doc
            info['uses'] = type_def.uses
        
        return info
