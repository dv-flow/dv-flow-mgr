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
from ..util import get_rootdir, get_naming_scheme
from ...util import loadProjPkgDef, parse_parameter_overrides
from ...cli_task_resolver import CLITaskResolver, TaskResolutionError
from ...ext_rgy import ExtRgy
from ...task import collect_task_params


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
        
        # `--usage` renders the CLI-shaped view (what you can pass the task)
        # instead of the data-shaped detail view (what the task is). Same
        # resolution path; different renderer.
        if getattr(args, 'usage', False):
            resolved = self._resolve_task(task_name, pkg, loader)
            if resolved is None:
                print(f"Error: Task '{task_name}' not found")
                return 1
            task, _ = resolved
            from .usage import build_usage_info, render_usage
            values = self._resolved_values(task, pkg, loader)
            if getattr(args, 'json', False):
                # `--json` is a format switch here, exactly as it is for every
                # other show subcommand -- not an alternative to --usage.
                print(json.dumps(build_usage_info(task, values=values),
                                 indent=2, default=str))
            else:
                render_usage(task, values=values)
            return 0

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
    
    def _builder(self, pkg, loader):
        """A throwaway builder used only to RESOLVE values for display.

        It constructs no nodes (see `TaskGraphBuilder.resolveTaskParams`), so
        describing a task never builds, or fails on, that task's dependencies.
        """
        if pkg is None or loader is None:
            return None
        try:
            from ...task_graph_builder import TaskGraphBuilder
            return TaskGraphBuilder(
                root_pkg=pkg,
                rundir=os.path.join(os.getcwd(), "rundir"),
                loader=loader)
        except Exception as e:
            self._log.debug(f"No builder for value resolution: {e}")
            return None

    def _resolved_values(self, task, pkg, loader):
        """`{param: value}` with `${{ }}` defaults evaluated, or None.

        Display-only: any failure degrades to showing the declared text rather
        than breaking the command.
        """
        b = self._builder(pkg, loader)
        if b is None:
            return None
        try:
            return b.resolveTaskParams(task)
        except Exception as e:
            self._log.debug(f"Could not resolve params for {task.name}: {e}")
            return None

    def _find_task(self, task_name: str, pkg, loader) -> Optional[Dict[str, Any]]:
        """Find a task by name and describe it."""
        self._resolve_builder = self._builder(pkg, loader)
        resolved = self._resolve_task(task_name, pkg, loader)
        if resolved is None:
            return None
        task, pkg_name = resolved
        return self._task_to_info(task, pkg_name)

    def _resolve_task(self, task_name: str, pkg, loader):
        """Resolve a name to (Task, package name), or None.

        Split out of _find_task so `--usage` reaches the same resolution --
        including the installed-package fallback -- without going through the
        detail-view dict.
        """
        # Use CLITaskResolver for flexible suffix matching when project pkg available
        if pkg:
            resolver = CLITaskResolver.from_package(pkg)
            try:
                task = resolver.resolve(task_name)
                pkg_name = task.package.name if hasattr(task, 'package') and task.package else pkg.name
                return task, pkg_name
            except TaskResolutionError:
                pass

        # Fallback: exact lookup in installed packages by parsing the name
        if '.' in task_name:
            pkg_name, short_name = task_name.rsplit('.', 1)
        else:
            return None

        rgy = ExtRgy.inst()
        if pkg_name in rgy._pkg_m:
            try:
                provider = rgy._pkg_m[pkg_name]
                if loader is None:
                    from ...package_loader import PackageLoader
                    loader = PackageLoader(marker_listeners=[], param_overrides={})
                loaded_pkg = provider.findPackage(pkg_name, loader)
                if loaded_pkg and hasattr(loaded_pkg, 'task_m') and loaded_pkg.task_m:
                    full_task_name = f"{pkg_name}.{short_name}"
                    if full_task_name in loaded_pkg.task_m:
                        return loaded_pkg.task_m[full_task_name], pkg_name
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
        
        # Prefer the resolved Task, which is where inheritance along `uses:`
        # has already been applied; the taskdef is only the authored YAML, and
        # is absent entirely for tasks that aren't declared directly.
        desc = getattr(task, 'desc', '') or ''
        doc = getattr(task, 'doc', '') or ''
        if not (desc and doc) and getattr(task, 'taskdef', None):
            desc = desc or (getattr(task.taskdef, 'desc', '') or '')
            doc = doc or (getattr(task.taskdef, 'doc', '') or '')
        
        info = {
            'name': task.name,
            'short_name': short_name,
            'package': pkg_name,
            'desc': desc,
            'doc': doc,
            'examples': self._examples_to_list(getattr(task, 'examples', [])),
            'uses': task.uses.name if hasattr(task, 'uses') and task.uses else None,
            'scope': scope,
            'tags': self._tags_to_list(getattr(task, 'tags', [])),
            'params': self._get_params(task),
            # A lazily-evaluated default is stored as its source text, so the
            # detail view showed `${{ build }}` where the user wants `opt`.
            'param_values': self._param_values(task),
            'needs': [n.name if hasattr(n, 'name') else str(n) for n in getattr(task, 'needs', [])],
            'rundir': str(task.rundir.value) if hasattr(task, 'rundir') and task.rundir else 'unique',
            'passthrough': str(task.passthrough) if hasattr(task, 'passthrough') and task.passthrough else None,
            'consumes': str(task.consumes) if hasattr(task, 'consumes') and task.consumes else None,
            'produces': task.produces if hasattr(task, 'produces') and task.produces else None,
        }

        select = getattr(getattr(task, 'strategy', None), 'select', None)
        if select is not None:
            # A family's cells are the thing a user actually addresses, so they
            # belong in its detail view -- otherwise the only way to learn a
            # cell's name is to derive it from the axes by hand.
            # The default is an expression over the family's parameters, so
            # report what it RESOLVES to -- `view=tlm`, not `view=${{ view }}`.
            default = None
            b = getattr(self, '_resolve_builder', None)
            if b is not None:
                try:
                    default = b.resolveSelectDefault(task)
                except Exception as e:
                    self._log.debug(f"Could not resolve select default: {e}")
            if default is None:
                default = select.default
            info['select'] = {
                'axes': {a: [str(v) for v in vals]
                         for a, vals in select.axes.items()},
                'mode': select.mode,
                'default': {a: str(v) for a, v in default.items()},
                'cells': ["%s.%s" % (task.name, k) for k in select.cells],
            }
        bindings = getattr(task, 'select_bindings', None)
        if bindings is not None:
            family = getattr(task, 'select_family', None)
            info['select_cell'] = {
                'family': family.name if family is not None else None,
                'bindings': {a: str(v) for a, v in bindings.items()},
            }

        return info
    
    def _param_values(self, task):
        b = getattr(self, '_resolve_builder', None)
        if b is None:
            return None
        try:
            return {k: str(v) for k, v in b.resolveTaskParams(task).items()}
        except Exception as e:
            self._log.debug(f"Could not resolve params for {task.name}: {e}")
            return None

    def _get_params(self, task) -> Dict[str, Dict[str, Any]]:
        """Extract parameters from a task, including those inherited via `uses:`.

        A derived task really has its base's params (they are merged into the
        node's paramT and are settable with `-D`), so listing only its own
        declarations under-reported it.
        """
        params = {}
        definitions, types = collect_task_params(task)
        for name in definitions:
            pdef = definitions[name]
            ptype = types.get(name, 'any')
            params[name] = {
                'type': str(ptype) if ptype else 'any',
                'value': pdef.value if hasattr(pdef, 'value') else '',
                'doc': (pdef.doc or pdef.desc or '') if hasattr(pdef, 'doc') else ''
            }
        return params
    
    def _examples_to_list(self, examples):
        """Convert declared examples to JSON-serializable dicts."""
        if not examples:
            return []
        result = []
        for ex in examples:
            result.append({
                'title': getattr(ex, 'title', None),
                'code': getattr(ex, 'code', '') or '',
                'caption': getattr(ex, 'caption', None),
                'lang': getattr(ex, 'lang', 'yaml') or 'yaml',
            })
        return result

    def _tags_to_list(self, tags):
        """Convert tags to JSON-serializable entries.

        A resolved tag is a Type, and str() on one is a Python repr of the
        whole type object -- unusable to any consumer. What a caller wants is
        the tag's name and the parameters it was applied with, which is what a
        lifecycle tag (std.Deprecated and friends) exists to carry.
        """
        if not tags:
            return []
        result = []
        for tag in tags:
            if isinstance(tag, (str, dict)):
                result.append(tag)
                continue
            name = getattr(tag, 'name', None)
            if name is None:
                result.append(str(tag))
                continue
            entry = {'name': name}
            paramT = getattr(tag, 'paramT', None)
            if paramT is not None and hasattr(type(paramT), 'model_fields'):
                params = {}
                for k in type(paramT).model_fields.keys():
                    v = getattr(paramT, k, None)
                    if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                        params[k] = v
                    else:
                        params[k] = str(v)
                entry['params'] = params
            result.append(entry)
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
            builder = TaskGraphBuilder(root_pkg=pkg, rundir=rundir, loader=loader,
                                       naming_scheme=get_naming_scheme())
            
            # Build the task node (CLI usage: allow root package prefix)
            # Resolve the task name using CLITaskResolver for flexible matching
            resolver = CLITaskResolver.from_package(pkg)
            try:
                resolved = resolver.resolve(task_name)
                resolved_name = resolved.name
            except TaskResolutionError:
                resolved_name = task_name
            task_node = builder.mkTaskNode(resolved_name)
            
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
        
        # Show resolved values where they are available: `${{ build }}` is the
        # expression that computes the default, not the default.
        _params = dict(info.get('params', {}))
        _values = info.get('param_values') or {}
        for _name, _entry in _params.items():
            if _name in _values and isinstance(_entry, dict):
                _entry = dict(_entry)
                _entry['value'] = _values[_name]
                _params[_name] = _entry
        formatter.add_params("Parameters", _params)

        select = info.get('select')
        if select is not None:
            axes = ["%s: %s" % (a, ", ".join(v)) for a, v in select['axes'].items()]
            formatter.add_list("Variant axes", axes)
            if select['mode'] == 'all':
                note = "(a gate over every cell)"
            elif select['mode'] == 'none':
                note = "(only cells are addressable)"
            else:
                note = "(default: %s)" % ", ".join(
                    "%s=%s" % (a, v) for a, v in select['default'].items())
            formatter.add_list("Cells %s" % note, select['cells'])

        cell = info.get('select_cell')
        if cell is not None:
            formatter.add_list(
                "Variant of %s" % cell['family'],
                ["%s = %s" % (a, v) for a, v in cell['bindings'].items()])
        
        if info.get('examples'):
            for i, ex in enumerate(info['examples']):
                heading = ex.get('title') or "Example %d" % (i + 1)
                # A section, not a list: example code is meant to be copied,
                # and bullets are not part of what the reader should type.
                body = ""
                if ex.get('caption'):
                    body += "%s\n\n" % ex['caption']
                body += ex.get('code', '').rstrip()
                formatter.add_section(heading, body)

        if info.get('tags'):
            tag_strs = []
            for tag in info['tags']:
                if isinstance(tag, str):
                    tag_strs.append(tag)
                elif isinstance(tag, dict) and 'name' in tag:
                    # Show only the parameters that were actually set: a tag's
                    # empty defaults say nothing and crowd out the ones that do.
                    set_params = ["%s=%s" % (k, v)
                                  for k, v in (tag.get('params') or {}).items()
                                  if v not in (None, "", [], {})]
                    if set_params:
                        tag_strs.append("%s (%s)" % (tag['name'],
                                                     ", ".join(set_params)))
                    else:
                        tag_strs.append(tag['name'])
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
            # Show consumes and produces
            if info.get('consumes'):
                formatter.add_field("Consumes", info['consumes'])
            
            if info.get('produces'):
                produces_strs = []
                for pattern in info['produces']:
                    pattern_str = ', '.join(f"{k}={v}" for k, v in pattern.items())
                    produces_strs.append(pattern_str)
                formatter.add_list("Produces", produces_strs)
            
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
