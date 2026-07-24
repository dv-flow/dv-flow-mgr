#****************************************************************************
#* name_resolution.py
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

import dataclasses as dc
import fnmatch
import logging
import re
from typing import Any, ClassVar, Dict, List, Optional, Tuple
from .package import Package
from .task_node import TaskNode


def _path_glob_to_regex(glob: str) -> str:
    """Translate a `path:` glob to a regex. Segments are separated by '/' (a
    node's dotted name is normalized to '/'); `**` matches any depth, `*`
    matches within a single segment."""
    out = []
    i = 0
    while i < len(glob):
        c = glob[i]
        if c == '*':
            if i + 1 < len(glob) and glob[i + 1] == '*':
                out.append('.*')          # ** -> any depth
                i += 2
                continue
            out.append('[^/]*')           # * -> within one segment
        else:
            out.append(re.escape(c))
        i += 1
    return '^' + ''.join(out) + '$'


def _path_match(glob: str, path: str) -> bool:
    """Match a hierarchical path against a `path:` glob. The path is normalized
    so '.' and '/' are interchangeable separators."""
    norm = path.replace('.', '/')
    g = glob.replace('.', '/')
    return re.match(_path_glob_to_regex(g), norm) is not None


def node_matches(matchers, uses_chain, path) -> bool:
    """True if a node with the given `uses`-chain task type-names and
    hierarchical `path` satisfies ALL matcher predicates (AND-combined).
    `matchers` is a list of ('uses'|'path', glob) tuples; an empty list matches
    everything (an unmatched, i.e. top-level, binding)."""
    for kind, glob in matchers:
        if kind == 'uses':
            if not any(fnmatch.fnmatch(t, glob) for t in (uses_chain or [])):
                return False
        elif kind == 'path':
            if path is None or not _path_match(glob, path):
                return False
        else:
            return False
    return True

@dc.dataclass
class VarResolver(object):

    def resolve_variable(self, name : str) -> Any:
        raise NotImplementedError("resolve_variable not implemented")
    
@dc.dataclass
class TaskNameResolutionScope:
    """Represents a single task scope in the name resolution stack"""
    task: TaskNode
    variables: Dict[str, Any] = dc.field(default_factory=dict)

@dc.dataclass
class SetScope:
    """One frame of the dynamic `set:` override stack (see
    docs/proposals/set_overrides_impl_plan.md Phase 2/4). Frames are pushed as
    the builder descends into a compound/matrix subtree that declares `set:`
    and popped when it leaves, so the stack mirrors the ancestor chain of the
    node whose params are being evaluated.

    - `rebinds`: qualified-name variable rebinds (e.g. "hdlsim.sim" -> "mti")
      that ordinary `${{ pkg.var }}` references resolve to. Each is
      (name, value, matchers); an empty matcher list is a global (top-level)
      rebind, a non-empty one narrows to nodes selected by uses:/path: globs.
    - `rules`: forceful param-set rules applied at node creation — each is
      (param_name, value, matchers, depth). `depth` (nesting depth) drives
      outer-wins for the same param on the same node (Phase 4).

    Outer frames win over inner (the stack is scanned outermost-first)."""
    task_name: str = None
    rebinds: List[Tuple[str, Any, list]] = dc.field(default_factory=list)
    rules: List[Tuple[str, Any, list, int]] = dc.field(default_factory=list)

@dc.dataclass
class NameResolutionContext(VarResolver):
    """Represents a complete name resolution context"""
    builder: 'TaskGraphBuilder'  # Forward reference to avoid circular import
    package: Package
    task_scopes: List[TaskNameResolutionScope] = dc.field(default_factory=list)
    _log : ClassVar = logging.getLogger(__name__)

    def push_task_scope(self, task: TaskNode) -> None:
        """Push a new task scope onto the stack"""
        self.task_scopes.append(TaskNameResolutionScope(task=task))

    def pkg_var(self, pkg_name: str, name: str):
        """Look up a package-level variable, reading the package's *instance*
        params first so a `-D <pkg>.<name>` override is honored, then falling
        back to the class default. Returns (found: bool, value).

        Used by ExprEval._lookup_pkg_chain for the resolve() `uses`-chain walk
        (see docs/proposals/task_elaboration_impl_plan.md §B.2). Distinct from
        resolve_variable's dotted branch (:69-75), which reads only the class
        default and thus misses -D overrides."""
        # 1. Instance params (honors -D <pkg>.<name>)
        params = self.builder._pkg_params_m.get(pkg_name)
        if params is not None and hasattr(params, name):
            return True, getattr(params, name)
        # 2. Class default (package with a paramT but no materialized instance)
        pkg = self.builder._pkg_m.get(pkg_name)
        if pkg is not None and getattr(pkg, 'paramT', None) is not None \
                and hasattr(pkg.paramT, name):
            return True, getattr(pkg.paramT, name)
        return False, None


    def _lookup_set_scope(self, name: str):
        """Look up a `set:` qualified-name rebind. The override stack lives on
        the builder (`_set_scopes`) so it survives package-context switches; it
        is scanned OUTERMOST-first so an ancestor `set:` beats a nested one
        (design §R2.4). Returns (found: bool, value).

        A var overridden from the CLI/-D is NOT reboundable here: the CLI is the
        precedence ceiling, so such names fall through to the (CLI-baked) default."""
        scopes = getattr(self.builder, "_set_scopes", None)
        if not scopes:
            return False, None
        if self._is_cli_overridden(name):
            return False, None
        # Current build target (uses-chain, path) for narrowing matcher-gated
        # rebinds; None => match only un-narrowed (top-level) rebinds.
        ctx = getattr(self.builder, "_cur_build_ctx", None)
        uses_chain, path = ctx if ctx is not None else (None, None)
        for scope in scopes:                  # index 0 = outermost -> outer wins
            best = None                       # (num_matchers, value) most-specific
            for rname, rval, matchers in scope.rebinds:
                if rname != name:
                    continue
                if matchers and not node_matches(matchers, uses_chain, path):
                    continue
                # Within one frame, a matcher-bearing (narrowed) rebind is more
                # specific than a global one and wins; across frames, outer wins.
                if best is None or len(matchers) > best[0]:
                    best = (len(matchers), rval)
            if best is not None:
                return True, best[1]
        return False, None

    def _is_cli_overridden(self, name: str) -> bool:
        """True if `name` (a dotted pkg.var) names a package variable that was
        overridden from the CLI/-D at load (recorded on the Package)."""
        last_dot = name.rfind('.')
        if last_dot == -1:
            return False
        pkg_name, var_name = name[:last_dot], name[last_dot+1:]
        pkg = self.builder._pkg_m.get(pkg_name)
        return pkg is not None and var_name in getattr(pkg, "cli_var_overrides", ())

    def resolve_variable(self, name: str) -> Any:
        """Resolve a `${{ name }}` reference at GRAPH-BUILD time. This is the
        authoritative precedence ladder for the build phase; keep the order here
        and the body in sync.

        Precedence (first match wins):
          1. CLI / -D package var        (`_pkg_params_m[name]`) -- the ceiling
          2. `set:` scoped rebind        (outermost frame wins; CLI-pinned names
                                          are excluded -- see _lookup_set_scope)
          3. dotted `pkg.var`            (instance-first via `pkg_var`, honoring
                                          -D; loads the package on demand)
          4. task scopes                 (innermost first: scope vars, then the
                                          scope task's params)
          5. current package default     (`self.package.paramT`)

        Related but SEPARATE ladders (do not conflate):
          * `resolve()` (ExprEval._builtin_resolve) adds a `let:`-scoped rung and
            a `uses`-chain-package rung ahead of the literal default -- it is a
            superset used only for scoped-variable fallback.
          * The LOAD phase resolves through PackageScope.resolve_variable, which
            reads class-level `model_fields[...].default` (there are no
            materialized param *instances* yet; a -D override is baked into that
            default at load, so -D is still honored). The build phase reads the
            *instance* (via `pkg_var`) because expanded/templated values live
            only on instances. This phase split is intentional -- the two readers
            exist because different data is available, not by oversight.
        """
        self._log.debug("--> resolve_variable(%s)", name)
        # Check if this is a package-qualified reference
        ret = None

        # Package-qualified parameter lookup (e.g. foo.DEBUG).
        # Precedence ladder (design §R2.4): CLI/-D (`_pkg_params_m`) is the
        # ceiling and stays first; a `set:` rebind (outer overrides inner) beats
        # the declared package default; the default is the last resort.
        if name in self.builder._pkg_params_m.keys():
            ret = self.builder._pkg_params_m[name]        # 1. CLI / -D (ceiling)
        else:
            # 2. `set:` scoped rebind, outermost frame wins.
            found, val = self._lookup_set_scope(name)
            if found:
                ret = val
            else:
                # 3. Dotted `pkg.var` lookup. Trigger on-demand load/registration
                # (variable substitution pulls in a package that was never
                # statically imported -- e.g. an elaborator-selected backend),
                # then read the package's param INSTANCE via pkg_var: it honors
                # -D and, unlike `getattr(pkg.paramT, ...)` on the class, actually
                # exposes pydantic-v2 fields (which live on instances only).
                last_dot = name.rfind('.')
                if last_dot != -1:
                    pkg_name = name[:last_dot]
                    param_name = name[last_dot+1:]
                    self.builder._ensure_pkg_vars(pkg_name)
                    found, val = self.pkg_var(pkg_name, param_name)
                    if found:
                        ret = val

        # Check task scopes from innermost to outermost
        if ret is None:
            for scope in reversed(self.task_scopes):
                if name in scope.variables.keys():
                    ret = scope.variables[name]
                    break
                elif hasattr(scope.task.params, name):
                    # Check task parameters
                    ret = getattr(scope.task.params, name)
                    break

        # Check package variables
        if ret is None and hasattr(self.package.paramT, name):
            ret = getattr(self.package.paramT, name)

#        if ret is None and name in self.builder._pkg_m.keys():
#            pkg = self.builder._pkg_m[name]
#            ret = pkg.paramT

        self._log.debug("<-- resolve_variable(%s) -> %s" % (name, ret))
        return ret
