#****************************************************************************
#* cmd_validate.py
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
"""Validate command - checks flow.yaml/flow.dv for errors and warnings."""

import json
import logging
import os
from typing import ClassVar, List, Dict, Any, Set, Optional
from ..util import loadProjPkgDef, parse_parameter_overrides
from ..task_graph_builder import TaskGraphBuilder
from ..task_data import SeverityE, TaskMarker
from ..marker_listener import MarkerListener
from .util import get_rootdir


class ValidationMarkerListener:
    """Collect markers during validation."""
    
    def __init__(self):
        self.markers: List[Dict[str, Any]] = []
    
    def marker(self, m: TaskMarker):
        """Receive a TaskMarker and store it."""
        marker_info = {
            'severity': m.severity.value if hasattr(m.severity, 'value') else str(m.severity),
            'message': m.msg,
        }
        if m.loc:
            marker_info['location'] = {
                'file': m.loc.path,
                'line': m.loc.line if m.loc.line != -1 else None,
                'column': m.loc.pos if m.loc.pos != -1 else None,
            }
        self.markers.append(marker_info)


class CmdValidate:
    """Validate flow.yaml/flow.dv files for errors and warnings.
    
    Performs the following checks:
    - Syntax validation (YAML/DV parsing)
    - Undefined task references
    - Circular dependencies
    - Unused tasks (warnings)
    - Missing required parameters
    """
    
    _log: ClassVar = logging.getLogger("CmdValidate")
    
    def __call__(self, args):
        flow_file = getattr(args, 'flow_file', None)
        json_output = getattr(args, 'json', False)
        
        # Determine root directory
        root = get_rootdir(args)
        if flow_file and os.path.isfile(flow_file):
            root = os.path.dirname(os.path.abspath(flow_file))
        
        # Collect validation results
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        info: List[Dict[str, Any]] = []
        
        # Create marker listener for collecting errors during load
        marker_listener = ValidationMarkerListener()
        
        # Phase 1: Try to load the package
        pkg = None
        loader = None
        try:
            loader, pkg = loadProjPkgDef(
                root,
                listener=marker_listener.marker,
                parameter_overrides=parse_parameter_overrides(getattr(args, 'param_overrides', [])),
                config=getattr(args, 'config', None)
            )
        except Exception as e:
            errors.append({
                'type': 'LoadError',
                'message': str(e),
                'location': {'file': flow_file or root}
            })
        
        # Collect markers from loading
        for marker in marker_listener.markers:
            if marker['severity'] == 'error':
                errors.append({
                    'type': 'ParseError',
                    'message': marker['message'],
                    'location': marker.get('location', {})
                })
            elif marker['severity'] == 'warning':
                warnings.append({
                    'type': 'ParseWarning',
                    'message': marker['message'],
                    'location': marker.get('location', {})
                })
        
        if pkg is None:
            if not errors:
                errors.append({
                    'type': 'NoPackageFound',
                    'message': f"No flow.dv/flow.yaml/flow.toml found in {root} or parent directories"
                })
        else:
            # Phase 2: Check for undefined task references
            undefined_refs = self._check_undefined_refs(pkg, loader)
            errors.extend(undefined_refs)
            
            # Phase 3: Check for circular dependencies
            circular_deps = self._check_circular_deps(pkg, loader)
            errors.extend(circular_deps)
            
            # Phase 4: Check for unused tasks (warning)
            unused_tasks = self._check_unused_tasks(pkg)
            warnings.extend(unused_tasks)
            
            # Phase 5: Collect info about the package
            info.append({
                'type': 'PackageInfo',
                'name': pkg.name,
                'task_count': len(pkg.task_m) if hasattr(pkg, 'task_m') and pkg.task_m else 0,
                'type_count': len(pkg.type_m) if hasattr(pkg, 'type_m') and pkg.type_m else 0,
            })
        
        # Output results
        valid = len(errors) == 0
        
        if json_output:
            result = {
                'valid': valid,
                'errors': errors,
                'warnings': warnings,
                'info': info,
                'error_count': len(errors),
                'warning_count': len(warnings),
            }
            print(json.dumps(result, indent=2))
        else:
            self._print_text_output(valid, errors, warnings, info)
        
        return 0 if valid else 1
    
    def _check_undefined_refs(self, pkg, loader) -> List[Dict[str, Any]]:
        """Check for undefined task references in needs."""
        errors = []
        
        if not hasattr(pkg, 'task_m') or not pkg.task_m:
            return errors
        
        # Build set of known task names
        known_tasks: Set[str] = set(pkg.task_m.keys())
        
        # Also add tasks from imported packages
        if hasattr(pkg, 'pkg_m') and pkg.pkg_m:
            for subpkg in pkg.pkg_m.values():
                if hasattr(subpkg, 'task_m') and subpkg.task_m:
                    known_tasks.update(subpkg.task_m.keys())
        
        # Check each task's needs
        for task_name, task in pkg.task_m.items():
            needs = getattr(task, 'needs', []) or []
            for need in needs:
                # The needs list contains Task objects or None (if unresolved)
                if need is None:
                    # This was an unresolved reference - already reported by loader
                    continue
                
                # Handle Task object or tuple (Task, ...)
                if hasattr(need, 'name'):
                    need_name = need.name
                elif isinstance(need, tuple) and len(need) > 0 and hasattr(need[0], 'name'):
                    need_name = need[0].name
                else:
                    need_name = str(need)
                
                # Handle relative references
                if '.' not in need_name:
                    need_name = f"{pkg.name}.{need_name}"
                
                if need_name not in known_tasks:
                    # Try to find similar tasks
                    suggestions = self._find_similar(need_name, known_tasks)
                    error = {
                        'type': 'UndefinedTaskReference',
                        'task': task_name,
                        'reference': need_name,
                        'message': f"Task '{task_name}' references undefined task '{need_name}'"
                    }
                    if suggestions:
                        error['suggestions'] = suggestions
                    errors.append(error)
        
        return errors
    
    def _check_circular_deps(self, pkg, loader) -> List[Dict[str, Any]]:
        """Check for circular dependencies between tasks."""
        errors = []
        
        if not hasattr(pkg, 'task_m') or not pkg.task_m:
            return errors
        
        # Build dependency graph
        deps: Dict[str, Set[str]] = {}
        for task_name, task in pkg.task_m.items():
            needs = getattr(task, 'needs', []) or []
            deps[task_name] = set()
            for need in needs:
                if need is None:
                    continue
                if hasattr(need, 'name'):
                    need_name = need.name
                elif isinstance(need, tuple) and len(need) > 0 and hasattr(need[0], 'name'):
                    need_name = need[0].name
                else:
                    need_name = str(need)
                if '.' not in need_name:
                    need_name = f"{pkg.name}.{need_name}"
                deps[task_name].add(need_name)
        
        # Detect cycles using DFS
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []
        
        def dfs(node: str) -> Optional[List[str]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in deps.get(node, set()):
                if neighbor not in visited:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
            
            path.pop()
            rec_stack.remove(node)
            return None
        
        for task_name in deps:
            if task_name not in visited:
                cycle = dfs(task_name)
                if cycle:
                    errors.append({
                        'type': 'CircularDependency',
                        'tasks': cycle,
                        'message': f"Circular dependency detected: {' -> '.join(cycle)}"
                    })
                    break  # Report only first cycle
        
        return errors
    
    def _check_unused_tasks(self, pkg) -> List[Dict[str, Any]]:
        """Check for tasks that are defined but never referenced."""
        warnings = []
        
        if not hasattr(pkg, 'task_m') or not pkg.task_m:
            return warnings
        
        # Find all referenced tasks
        referenced: Set[str] = set()
        for task_name, task in pkg.task_m.items():
            needs = getattr(task, 'needs', []) or []
            for need in needs:
                if need is None:
                    continue
                if hasattr(need, 'name'):
                    need_name = need.name
                elif isinstance(need, tuple) and len(need) > 0 and hasattr(need[0], 'name'):
                    need_name = need[0].name
                else:
                    need_name = str(need)
                if '.' not in need_name:
                    need_name = f"{pkg.name}.{need_name}"
                referenced.add(need_name)
        
        # Find root tasks (entry points)
        root_tasks = set()
        for task_name, task in pkg.task_m.items():
            if getattr(task, 'is_root', False):
                root_tasks.add(task_name)
        
        # Tasks that are neither root nor referenced are "unused"
        for task_name in pkg.task_m:
            if task_name not in referenced and task_name not in root_tasks:
                # Only warn for tasks in the root package
                if task_name.startswith(pkg.name + '.'):
                    warnings.append({
                        'type': 'UnusedTask',
                        'task': task_name,
                        'message': f"Task '{task_name}' is defined but never referenced"
                    })
        
        return warnings
    
    def _find_similar(self, name: str, known: Set[str], max_results: int = 3) -> List[str]:
        """Find similar task names for suggestions."""
        # Simple substring matching
        base_name = name.split('.')[-1].lower()
        similar = []
        
        for known_name in known:
            known_base = known_name.split('.')[-1].lower()
            if base_name in known_base or known_base in base_name:
                similar.append(known_name)
        
        return similar[:max_results]
    
    def _print_text_output(self, valid: bool, errors: List[Dict], 
                          warnings: List[Dict], info: List[Dict]):
        """Print human-readable validation output."""
        # Print info
        for i in info:
            if i['type'] == 'PackageInfo':
                print(f"Package: {i['name']}")
                print(f"  Tasks: {i['task_count']}")
                print(f"  Types: {i['type_count']}")
                print()
        
        # Print errors
        if errors:
            print(f"Errors ({len(errors)}):")
            for error in errors:
                loc = error.get('location', {})
                loc_str = ''
                if loc:
                    file = loc.get('file', '')
                    line = loc.get('line')
                    if file:
                        loc_str = f" [{file}"
                        if line:
                            loc_str += f":{line}"
                        loc_str += "]"
                
                print(f"  ERROR: {error['message']}{loc_str}")
                
                if error.get('suggestions'):
                    print(f"         Did you mean: {', '.join(error['suggestions'])}?")
        
        # Print warnings
        if warnings:
            print(f"\nWarnings ({len(warnings)}):")
            for warning in warnings:
                print(f"  WARNING: {warning['message']}")
        
        # Summary
        print()
        if valid:
            print("✓ Validation passed")
            if warnings:
                print(f"  ({len(warnings)} warning(s))")
        else:
            print(f"✗ Validation failed with {len(errors)} error(s)")
