#****************************************************************************
#* task_graph_builder.py
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
#* Created on:
#*     Author: 
#*
#****************************************************************************
import os
import re
import difflib
import dataclasses as dc
import logging
import pydantic
from typing import Callable, Any, Dict, List, Union
from .package import Package
from .package_def import PackageDef, PackageSpec
from .package_loader_p import PackageLoaderP
from .param_ref_eval import ParamRefEval
from .param_builder import ParamBuilder
from .name_resolution import NameResolutionContext, TaskNameResolutionScope, SetScope, node_matches
from .exec_gen_callable import ExecGenCallable
from .ext_rgy import ExtRgy
from .task import (Task, Need, iter_uses_chain, collect_task_params,
                   collect_param_value_sets)
from .task_def import RundirE
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE, TaskDataItem
from .task_gen_ctxt import TaskGenCtxt, TaskGenInputData
from .task_node import TaskNode
from .task_node_compound import TaskNodeCompound
from .task_node_ctxt import TaskNodeCtxt
from .task_node_leaf import TaskNodeLeaf
from .type import Type
from .std.task_null import TaskNull
from .data_callable import DataCallable
from .exec_callable import ExecCallable
from .null_callable import NullCallable
from .shell_callable import ShellCallable
from .deferred_expr import DeferredExpr, references_runtime_data
from .param_types import (TypeKind, ParamTypeError, normalize_type,
                          coerce_to_kind, coerce_cli_value, check_value_set)
from .expr_parser import parse_expr
from .filter_registry import FilterRegistry
from .naming_scheme import NamingScheme, NamingSchemeRegistry, TaskNamingContext, MatrixNamingContext
from .task_elaborator import (
    TaskElaborator, DefaultLeafElaborator, DefaultCompoundElaborator,
    DefaultStrategyElaborator, DefaultControlElaborator)

@dc.dataclass
class TaskNamespaceScope(object):
    task_m : Dict[str,TaskNode] = dc.field(default_factory=dict)

@dc.dataclass
class CompoundTaskCtxt(object):
    parent : 'TaskGraphBuilder'
    task : 'TaskNode'
    rundir : RundirE
    task_m : Dict[str,TaskNode] = dc.field(default_factory=dict)
    uses_s : List[Dict[str, TaskNode]] = dc.field(default_factory=list)


@dc.dataclass
class CheckCtxt(object):
    """What a `std.Check` implementation is handed.

    Deliberately narrower than `ElabCtxt`: a check may inspect and report, and
    must not construct nodes. A check that built something would change the
    graph it is validating, and its diagnostics would stop being trustworthy.
    """
    task : Any                  # the (override-resolved) task being checked
    node : Any                  # the constructed node
    needs : List[Any]           # its needs, after elaborator selection
    params : Any                # the check instance's own parameters
    check_name : str = ""
    severity : str = "error"
    hint : str = ""
    builder : Any = None

    def error(self, msg, detail=None, fix=None):
        self._report(msg, detail, fix, self.severity)

    def warning(self, msg, detail=None, fix=None):
        self._report(msg, detail, fix, "warning")

    def _report(self, msg, detail, fix, severity):
        """One shape for every check diagnostic: what is wrong, where the
        requirement came from, and what to type. The third part is what makes
        the difference between a report and a fix."""
        lines = ["%s -- %s" % (self.task.name, msg)]
        if detail:
            lines.append("   " + str(detail).replace("\n", "\n   "))
        lines.append("   required by  %s" % self.check_name)
        for extra in (fix, self.hint):
            if extra:
                lines.append("")
                for line in str(extra).rstrip().split("\n"):
                    lines.append("   " + line)
        text = "\n".join(lines)
        if self.builder is None:
            raise Exception(text)
        if severity == "warning":
            self.builder.marker(TaskMarker(msg=text, severity=SeverityE.Warning))
        else:
            self.builder.error(text)


@dc.dataclass
class _ParamsHolder(object):
    """Adapts a bare params instance to the `.params` shape that
    `_apply_task_param_overrides` expects, so the override pass can run against
    params that do not (yet) belong to a node -- the pre-elaboration case."""
    params : Any


@dc.dataclass
class BuilderElabCtxt(object):
    """Concrete ElabCtxt (see task_elaborator.ElabCtxt) that adapts the builder's
    internals for a TaskElaborator. Constructed per elaborate() call with the
    build parameters (srcdir/params/hierarchical/eval) captured from
    `_mkTaskNode` so `buildDefault` reproduces the standard interior exactly."""
    builder : 'TaskGraphBuilder'
    srcdir : Any = None
    params : Any = None
    hierarchical : bool = False
    eval : Any = None
    is_root : bool = False
    # Programmatic mkTaskNode(**kwargs) for the node being elaborated, so
    # mkParams can apply the full ladder. None when this is not the node the
    # caller asked for (same meaning as `node_params` in the builder).
    node_params : Any = None
    # The task being elaborated -- kwargs apply only to it, not to some other
    # task an elaborator happens to call mkParams() on.
    task : Any = None

    # --- default interior -------------------------------------------------
    def buildDefault(self, task, name, select_needs=None):
        """Run the standard kind-based interior (control/strategy/compound/leaf)
        and needs wiring for `task`. `select_needs` filters declared needs."""
        return self.builder._build_default_interior(
            task, name, self.srcdir, self.params, self.hierarchical, self.eval,
            select_needs=select_needs)

    # --- params -----------------------------------------------------------
    def mkParams(self, task):
        """Build and return `task`'s params instance, with `${{ }}`/resolve()
        evaluated **and** the override ladder applied -- so what an elaborator
        reads is what the node will settle on. kwargs are applied only for the
        node actually being elaborated."""
        return self.builder._build_task_params(
            task, self.eval,
            node_params=(self.node_params if task is self.task else None))

    def resolveParam(self, task, name, default=None):
        """Convenience: build params and read one field, with a default."""
        params = self.mkParams(task)
        if params is None:
            return default
        return getattr(params, name, default)

    # --- node construction ------------------------------------------------
    def mkTaskNode(self, name_or_task, name=None, srcdir=None, needs=None, **kwargs):
        """Build another task's node, honoring overrides/memoization.

        Accepts a task *name* or a `Task` object. The Task form is what lets an
        elaborator build a locally-derived variant (e.g. `dc.replace(need,
        strategy=<filtered matrix>)`) and register it under the original name,
        so the standard needs-gathering picks the variant up from the node memo
        instead of rebuilding the original.
        """
        if isinstance(name_or_task, Task):
            # `eval` must be threaded: without it a variant of a task that
            # carries an `iff:` (or any expression evaluated during node build)
            # hits a None evaluation context.
            return self.builder._mkTaskNode(
                name_or_task,
                name=name if name is not None else name_or_task.name,
                srcdir=srcdir, eval=self.eval, **kwargs)
        return self.builder.mkTaskNode(
            name_or_task, name=name, srcdir=srcdir, needs=needs, **kwargs)

    def resolveNeed(self, name):
        """Memoized lazy need resolution (== builder._getTaskNode)."""
        return self.builder._getTaskNode(name)

    def expand(self, expr):
        """Evaluate a `${{ }}` expression in this elaboration's context.

        Lets an elaborator inspect a declaration that is still an expression --
        e.g. a matrix axis written `"${{ images }}"`, whose members it would
        otherwise have to treat as unknowable. Returns the expression unchanged
        if it cannot be evaluated, so a caller can fall back rather than fail.
        """
        try:
            return self.builder._expandParam(expr, self.eval)
        except Exception:
            return expr

    def getTask(self, name):
        """Resolve a task *type* by name without building it (for rebinding)."""
        return self.builder.lookupTask(name)

    def declaredNeeds(self, task):
        """The task's declared needs, as a list of **Task** objects (not `Need`
        -- `Task.needs` holds resolved Tasks, which `_gatherNeeds` reads
        `.name` off directly). A filter therefore sees the whole task and can
        match on `.name`, `.tags`, or the `uses` chain."""
        return list(task.needs)

    # --- needs wiring primitives -----------------------------------------
    def wireNeed(self, node, need, block=False):
        need_n = need if isinstance(need, TaskNode) else self.resolveNeed(
            need.name if isinstance(need, Need) else need)
        node.needs.append((need_n, block))
        return need_n

    def wireNeeds(self, node, needs):
        for n in needs:
            self.wireNeed(node, n)

    def wireBody(self, node, task):
        """Reserved. The standard body construction is complex and stateful;
        obtain it via buildDefault(task, name) (optionally with a selectNeeds
        subclass) rather than re-implementing it here."""
        raise NotImplementedError(
            "wireBody: build the standard body via buildDefault(task, name); "
            "use a DefaultCompoundElaborator.selectNeeds subclass to filter needs")

    # --- diagnostics ------------------------------------------------------
    def error(self, msg, loc=None):
        self.builder.error(msg, loc)

    def marker(self, marker):
        self.builder.marker(marker)

    # --- cross-elaborator communication (A2.3) ---------------------------
    def publish(self, key, value):
        if self.builder._elab_ctxt_s:
            self.builder._elab_ctxt_s[-1][key] = value

    def lookup(self, key, default=None):
        for scope in reversed(self.builder._elab_ctxt_s):
            if key in scope:
                return scope[key]
        return default

    @property
    def args(self):
        """Build-global args (root package params). Root-only: a non-root
        elaborator reading args is a build error (invariant #4), because its
        output would then vary by context and break name-keyed memoization."""
        if not self.is_root:
            raise Exception(
                "elaborator context error: only the root task's elaborator may "
                "read `args` (invariant #4: root-only parameterization keeps the "
                "elaboration context build-global-constant). Use publish()/lookup() "
                "to pass values down, or bind the varying decision at the root.")
        rp = self.builder.root_pkg
        return self.builder._pkg_params_m.get(rp.name) if rp is not None else None


@dc.dataclass
class _ParamsHolder(object):
    """Minimal stand-in for a TaskNode where only `.params` is needed.

    `_apply_task_param_overrides` writes through `task_node.params`; a select
    family has to apply overrides before it has a node (the node it builds
    depends on the parameter values), so it passes this instead."""
    params : Any


def _resolve_uses_attr(task, attr : str):
    """Resolve an inheritable Task attribute along the `uses` chain.

    The package loader normally materializes inherited attributes onto each Task
    when the package is read (see
    `PackageProviderYaml._getPTConsumesProducesRundirUptodate`). That is correct
    right up until an ELABORATOR rewrites `uses` -- which happens after loading,
    so the inherited values were computed against the OLD chain and are stale.

    The concrete case this exists for: `hdlsim`'s abstract simulator tasks carry
    `elaborate: backend_select`, which rebinds `uses` from the abstract family
    task to the selected backend (`hdlsim.SimImage` -> `hdlsim.vlt.SimImage`).
    The backend is where `uptodate:` is declared, so before this the specialized
    node was built with `uptodate=None` and silently fell back to comparing
    parameters and the input signature -- neither of which changes when a source
    file's CONTENTS change. Simulation images built through the abstract task
    were therefore never rebuilt, which is the worst possible failure mode: a
    regression that passes against a stale binary.

    Only attributes that can legitimately still be None after loading are
    resolved this way (`uptodate`, `rundir`). `passthrough` and `consumes` are
    defaulted by the loader, so an unset value is indistinguishable from a
    declared one and walking the chain would override real declarations.
    """
    v = getattr(task, attr, None)
    seen = set()
    t = task
    while v is None and t is not None and getattr(t, "uses", None) is not None:
        t = t.uses
        if id(t) in seen:      # defensive: a malformed cyclic `uses` chain
            break
        seen.add(id(t))
        v = getattr(t, attr, None)
    return v


@dc.dataclass
class TaskGraphBuilder(object):
    """The Task-Graph Builder knows how to discover packages and construct task graphs"""
    root_pkg : Package
    rundir : str
    loader : PackageLoaderP = None
    marker_l : Callable = lambda *args, **kwargs: None
    env : Dict[str, str] = dc.field(default=None)
    task_param_overrides : Dict[str, Dict[str, Any]] = dc.field(default_factory=dict)  # task name → {param: value}
    leaf_param_overrides : Dict[str, Any] = dc.field(default_factory=dict)  # NEW: leaf param names to try on tasks
    naming_scheme : Union[str, NamingScheme] = "legacy"
    # Optional OverrideBindingTracker (param_override_tracker.py). When present,
    # each task-param override that actually binds is recorded, so the CLI can
    # report `-D` keys that bound nowhere. None for programmatic callers.
    override_tracker : Any = dc.field(default=None)
    # Per-run output-data identity (see run_id.py). None -> allocate the next
    # counter by scanning <rundir>/out. Threaded into TaskNodeCtxt so
    # std.Publish tasks share one output directory across the run.
    run_id : str = None
    _pkg_m : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    _pkg_params_m : Dict[str,Any] = dc.field(default_factory=dict)
    _pkg_spec_s : List[PackageDef] = dc.field(default_factory=list)
    _shell_m : Dict[str,Callable] = dc.field(default_factory=dict)
    _task_m : Dict[str,Task] = dc.field(default_factory=dict)
    _type_m : Dict[str,Type] = dc.field(default_factory=dict)
    # Node names whose `requires:` checks are held until `flushDeferredChecks`
    # (the invoked root, whose needs `--needs` can still extend).
    # >0 while a node is being built only to source a `uses:` implementation.
    _uses_impl_depth : int = 0
    _deferred_check_names : set = dc.field(default_factory=set)
    _deferred_checks : List[Any] = dc.field(default_factory=list)
    _task_node_m : Dict['TaskSpec',TaskNode] = dc.field(default_factory=dict)
    _type_node_m : Dict[str,Any] = dc.field(default_factory=dict)
    _override_m : Dict[str,str] = dc.field(default_factory=dict)
    _ns_scope_s : List[TaskNamespaceScope] = dc.field(default_factory=list)
    _compound_task_ctxt_s : List[CompoundTaskCtxt] = dc.field(default_factory=list)
    _task_rundir_s : List[List[str]] = dc.field(default_factory=list)
    _name_resolution_stack : List[NameResolutionContext] = dc.field(default_factory=list)
    # Dynamic `set:` override stack (design §R2 / set_overrides_impl_plan Phase
    # 2/4). Pushed on entry to a compound/matrix subtree that declares `set:`,
    # popped on exit; scanned outermost-first by resolve_variable so an ancestor
    # `set:` beats a nested one. Lives on the builder (not a name-resolution
    # context) so it survives package-context switches.
    _set_scopes : List['SetScope'] = dc.field(default_factory=list)
    # Current (uses_chain, path) of the node whose params are being evaluated,
    # so resolve_variable can narrow a matcher-gated `set:` rebind. None outside
    # a node build. Saved/restored around each _mkTaskNode (recursion-safe).
    _cur_build_ctx : Any = dc.field(default=None)
    _task_node_s : List[TaskNode] = dc.field(default_factory=list)
    _eval : ParamRefEval = dc.field(default_factory=ParamRefEval)
    # Per-type TaskElaborator registry (Feature A). Keyed by task type full
    # name; resolution walks the `uses` chain. Empty by default -> every task
    # uses the standard kind-based interior.
    _elaborator_m : Dict[str,Any] = dc.field(default_factory=dict)
    # Cache of resolved `elaborate:` clause callables, keyed by 'module:function'.
    _elaborate_fn_cache : Dict[str,Any] = dc.field(default_factory=dict)
    # Elaboration context stack for publish()/lookup() (A2.3). Each entry is a
    # dict scoped to a subtree; lookup walks outward, publish writes the top.
    _elab_ctxt_s : List[Dict[str,Any]] = dc.field(default_factory=list)
    # Type names whose elaborator is currently running -- a re-entrancy guard so
    # an elaborator that builds a task of its own bound type (e.g. a backend
    # selector building the concrete backend, which `uses:` the abstract type)
    # falls through to the default interior instead of re-firing forever.
    _elab_active : set = dc.field(default_factory=set)
    # Companion to _elab_active keyed on the NODE name currently being
    # elaborated. _elab_active keys on the elaborator TYPE name, but a
    # `uses:`-based package inheritance chain can expose the same abstract type
    # under several qualified names; a rebuilt variant can then reach the
    # `elaborate:` clause under a name not yet in _elab_active and re-fire
    # forever. The node name is stable across those aliases, so gating on it too
    # makes the re-entrancy guard alias-proof (critical for package-uses-package).
    _elab_active_names : set = dc.field(default_factory=set)
    _ctxt : TaskNodeCtxt = None
    _uses_count : int = 0
    _inherit_rundir_depth : int = 0
    _filter_registry : FilterRegistry = dc.field(default_factory=FilterRegistry)

    _log : logging.Logger = None

    def __post_init__(self):
        # Initialize the overrides from the global registry
        self._log = logging.getLogger(type(self).__name__)
        self._shell_m.update(ExtRgy.inst()._shell_m)
        # Per-type elaborators are bound declaratively via a task's `elaborate:`
        # clause (resolved in _resolve_elaborator) or programmatically via
        # register_elaborator; there is no global entry-point registry.
        self._task_rundir_s.append([self.rundir])

        # Resolve naming scheme from string or instance
        if isinstance(self.naming_scheme, str):
            self._naming_scheme = NamingSchemeRegistry.get(self.naming_scheme)
        else:
            self._naming_scheme = self.naming_scheme

        if self.env is None:
            self.env = os.environ.copy()

        if self.run_id is None:
            from .run_id import alloc_run_id
            self.run_id = alloc_run_id(self.rundir)

        self._eval.set("env", self.env)
        
        # Preserve runtime-only variables (expanded at task execution time)
        self._eval.set("inputs", "${{ inputs }}")
        self._eval.set("name", "${{ name }}")
        self._eval.set("result_file", "${{ result_file }}")



        if self.root_pkg is not None:
            # Collect all the tasks
            pkg_s = set()

            self._ctxt = TaskNodeCtxt(
                root_pkgdir=self.root_pkg.basedir,
                root_rundir=self.rundir,
                env=self.env,
                naming_scheme=self._naming_scheme,
                root_package_name=self.root_pkg.name,
                run_id=self.run_id)

            # Set built-in directory variables for task graph building
            # root: full path to the package file
            # rootdir: directory containing the package file
            # srcdir: directory containing the package file (same as rootdir for root package)
            pkg_file = self.root_pkg.srcinfo.file if self.root_pkg.srcinfo else None
            self._eval.set("root", pkg_file)
            self._eval.set("rootdir", self.root_pkg.basedir)
            self._eval.set("srcdir", self.root_pkg.basedir)

            # Build package paramT if needed
            if self.root_pkg.paramT:
                params = self.root_pkg.paramT()
                self._expandParams(params, self._eval)
                # Re-apply CLI/-D package-var overrides AFTER _expandParams (which
                # would otherwise re-apply the declared `value:` and mask them).
                self._apply_cli_var_overrides(self.root_pkg, params)
                for key in self.root_pkg.paramT.model_fields.keys():
                    self._eval.set(key, getattr(params, key))
                self._pkg_params_m[self.root_pkg.name] = params
            else:
                # No parameters
                params = None
                self._pkg_params_m[self.root_pkg.name] = None

            self._addPackageTasks(self.root_pkg, pkg_s)

            # Seed override map from package-level and config-level substitutions
            if hasattr(self.root_pkg, 'substitution_m'):
                self._override_m.update(self.root_pkg.substitution_m)
        else:
            self._ctxt = TaskNodeCtxt(
                root_pkgdir=None,
                root_rundir=self.rundir,
                env=self.env,
                naming_scheme=self._naming_scheme,
                root_package_name="",
                run_id=self.run_id)


    def setEnv(self, env):
        self.env.update(env)

    def _apply_cli_var_overrides(self, pkg, params):
        """Re-apply CLI/-D package-variable overrides onto a freshly built
        package-params instance. The load step records the overridden names on
        `pkg.cli_var_overrides` and stashes the parsed value on the paramT field
        default; but pydantic v2 does not honor a post-hoc default change at
        instantiation, so the instance must be corrected here. This makes
        `-D pkg.var` reach ordinary `${{ pkg.var }}` reads (and keeps the CLI the
        precedence ceiling over `set:`)."""
        for vn in getattr(pkg, 'cli_var_overrides', ()) or ():
            field = pkg.paramT.model_fields.get(vn) if pkg.paramT else None
            if field is not None and hasattr(params, vn):
                setattr(params, vn, field.default)

    def _ensure_pkg_vars(self, pkg_name):
        """Make package `pkg_name`'s variables resolvable for a `${{ pkg.var }}`
        reference, loading the package on demand if it was never statically
        imported. This covers a concrete backend (e.g. hdlsim.vlt) pulled in
        dynamically by an elaborator rather than via `imports:` -- there is no
        import edge to walk, but the loader can still find it by name. Variable
        substitution thus triggers the load; the package's param *instance*
        (honoring -D, and the only place pydantic-v2 fields are readable) is
        built into `_pkg_params_m`. Idempotent -- a no-op once registered.
        Returns the Package or None."""
        if pkg_name in self._pkg_m:
            return self._pkg_m[pkg_name]
        if self.loader is None:
            return None
        pkg = self.loader.findPackage(pkg_name)
        if pkg is None:
            return None
        # Register before expanding params so a self-referential var can't
        # re-enter this load for the same package.
        self._pkg_m[pkg_name] = pkg
        if getattr(pkg, 'paramT', None) is not None and pkg_name not in self._pkg_params_m:
            params = pkg.paramT()
            self._expandParams(params, self._eval)
            self._apply_cli_var_overrides(pkg, params)
            self._pkg_params_m[pkg_name] = params
            self._eval.set(pkg_name, params)
        return pkg

    def setParam(self, name, value):
        if self.root_pkg is None:
            raise Exception("No root package")
        params = self._pkg_params_m[self.root_pkg.name]
        
        if params is None:
            raise Exception("Package %s has no parameters" % self.root_pkg.name)

        if not hasattr(params, name):
            raise Exception("Package %s does not have parameter %s" % (self.root_pkg.name, name))
        setattr(params, name, value)

    def _addPackageTasks(self, pkg, pkg_s):
        # Register filters from this package
        if hasattr(pkg, 'filters') and pkg.filters:
            # Get list of imported package names
            imports = [imp if isinstance(imp, str) else imp.package for imp in (pkg.imports or [])]
            self._filter_registry.register_package_filters(pkg.name, pkg.filters, imports)
            self._log.debug(f"Registered {len(pkg.filters)} filters from package '{pkg.name}'")
        
        # Set root package for visibility checks
        if self.root_pkg and pkg.name == self.root_pkg.name:
            self._filter_registry.set_root_package(pkg.name)
        
        self._log.debug("--> _addPackageTasks: %s" % pkg.name)

        self._pkg_m[pkg.name] = pkg

        # Build out the package parameters
        if pkg.paramT:
            params = pkg.paramT()
            self._expandParams(params, self._eval)
            self._apply_cli_var_overrides(pkg, params)
            self._pkg_params_m[pkg.name] = params
            self._eval.set(pkg.name, params)
        else:
            params = None
            self._pkg_params_m[pkg.name] = None

        if pkg not in pkg_s:
            pkg_s.add(pkg)
            for task in pkg.task_m.values():
                self._addTask(task)
            for tt in pkg.type_m.values():
                self._addType(tt)
            for subpkg in pkg.pkg_m.values():
                self._addPackageTasks(subpkg, pkg_s)
            # Register import aliases (`as:`) so qualified references like
            # `alias.Task` / `alias.Type` / `alias.PARAM` resolve to the
            # aliased package's symbols.
            for alias, real_name in getattr(pkg, 'pkg_alias_m', {}).items():
                sub = pkg.pkg_m.get(real_name)
                if sub is not None:
                    self._registerPackageAlias(sub, alias)

    def _registerPackageAlias(self, sub, alias):
        """Make *sub*'s tasks/types/params reachable under an alias prefix."""
        self._pkg_m.setdefault(alias, sub)
        prefix = sub.name + "."
        for task in sub.task_m.values():
            short = task.name[len(prefix):] if task.name.startswith(prefix) else task.name
            self._task_m.setdefault("%s.%s" % (alias, short), task)
        for tt in sub.type_m.values():
            short = tt.name[len(prefix):] if tt.name.startswith(prefix) else tt.name
            self._type_m.setdefault("%s.%s" % (alias, short), tt)
        params = self._pkg_params_m.get(sub.name)
        if params is not None and alias not in self._pkg_params_m:
            self._pkg_params_m[alias] = params
            self._eval.set(alias, params)

    def _addTask(self, task):
        if task.name not in self._task_m.keys():
            self._task_m[task.name] = task
            for st in task.subtasks:
                self._addTask(st)

    def _addType(self, tt):
        if tt.name not in self._type_m.keys():
            self._type_m[tt.name] = tt

    def addOverride(self, key : str, val : str):
        self._override_m[key] = val

    def enter_package(self, pkg : PackageDef):
        pass

    def enter_rundir(self, rundir : str):
        self._log.debug("enter_rundir: %s (%d)" % (rundir, len(self._task_rundir_s[-1])))
        self._task_rundir_s[-1].append(rundir)

    def get_rundir(self, rundir=None):
        ret = self._task_rundir_s[-1].copy()
        if rundir is not None:
            ret.append(rundir)
        self._log.debug("get_rundir: %s" % str(ret))
        return ret
    
    def leave_rundir(self):
        self._log.debug("leave_rundir")
        self._task_rundir_s[-1].pop()

    def enter_uses(self):
        self._uses_count += 1

    def in_uses(self):
        return (self._uses_count > 0)
    
    def leave_uses(self):
        self._uses_count -= 1

#    def enter_compound(self, task : TaskNode, rundir=None):
#        self._compound_task_ctxt_s.append(CompoundTaskCtxt(
#            parent=self, task=task, rundir=rundir))
#
#        if rundir is None or rundir == RundirE.Unique:
#            self._rundir_s.append(task.name)

    def enter_compound_uses(self):
        self._compound_task_ctxt_s[-1].uses_s.append({})

    def leave_compound_uses(self):
        if len(self._compound_task_ctxt_s[-1].uses_s) > 1:
            # Propagate the items up the stack, appending 'super' to 
            # the names
            for k,v in self._compound_task_ctxt_s[-1].uses_s[-1].items():
                self._compound_task_ctxt_s[-1].uses_s[-2]["super.%s" % k] = v
        else:
            # Propagate the items to the compound namespace, appending
            # 'super' to the names
            for k,v in self._compound_task_ctxt_s[-1].uses_s[-1].items():
                self._compound_task_ctxt_s[-1].task_m["super.%s" % k] = v
        self._compound_task_ctxt_s[-1].uses_s.pop()

    def is_compound_uses(self):
        return len(self._compound_task_ctxt_s) > 0 and len(self._compound_task_ctxt_s[-1].uses_s) != 0

    def addTask(self, name, task : TaskNode):
        self._log.debug("--> addTask: %s" % name)

        if len(self._compound_task_ctxt_s) == 0:
            self._task_node_m[name] = task
        else:
            if len(self._compound_task_ctxt_s[-1].uses_s) > 0:
                self._compound_task_ctxt_s[-1].uses_s[-1][name] = task
            else:
                self._compound_task_ctxt_s[-1].task_m[name] = task
        self._log.debug("<-- addTask: %s" % name)

    def findTask(self, name, create=True, allow_root_prefix=False):
        """Find a task node by name.
        
        Args:
            name: Task name to find
            create: If True, create the task node if the task exists but node doesn't
            allow_root_prefix: If True (for CLI usage), try prepending root package name if exact match fails
        """
        task = None

        if len(self._compound_task_ctxt_s) > 0:
            if len(self._compound_task_ctxt_s[-1].uses_s) > 0:
                if name in self._compound_task_ctxt_s[-1].uses_s[-1].keys():
                    task = self._compound_task_ctxt_s[-1].uses_s[-1][name]
            if task is None and name in self._compound_task_ctxt_s[-1].task_m.keys():
                task = self._compound_task_ctxt_s[-1].task_m[name]
        if task is None and name in self._task_node_m.keys():
            task = self._task_node_m[name]

        if task is None and create:
            if name in self.root_pkg.task_m.keys():
                task = self.mkTaskGraph(name)
                self._log.debug("Found task %s in root package" % name)
            elif allow_root_prefix:
                # Try prepending the root package name for fragment-qualified names (CLI usage only)
                qualified_name = f"{self.root_pkg.name}.{name}"
                if qualified_name in self.root_pkg.task_m.keys():
                    task = self.mkTaskGraph(qualified_name)
                    self._log.debug("Found task %s as %s in root package" % (name, qualified_name))

            # Check the current package
#            if len(self._pkg_s) > 0 and name in self._pkg_s[-1].task_m.keys():
#                task = self._pkg_s[-1].task_m[name]
        
        return task

#    def leave_compound(self, task : TaskNode):
#        ctxt = self._compound_task_ctxt_s.pop()
#        if ctxt.rundir is None or ctxt.rundir == RundirE.Unique:
#            self._rundir_s.pop()

    def mkTaskGraph(self, task : str) -> TaskNode:
        return self.mkTaskNode(task)
        
    def push_name_resolution_context(self, pkg: Package):
        """Create and push a new name resolution context"""
        ctx = NameResolutionContext(
            builder=self,
            package=pkg)
        self._name_resolution_stack.append(ctx)
        # Keep the shared eval's resolver synced to the stack top so resolve()'s
        # package fall-through (Feature B) can walk `uses`-chain package vars via
        # NameResolutionContext.pkg_var. Body/matrix/needs evals already do this.
        self._eval.set_name_resolution(ctx)

    def pop_name_resolution_context(self):
        """Pop the current name resolution context"""
        if self._name_resolution_stack:
            self._name_resolution_stack.pop()
        self._eval.set_name_resolution(
            self._name_resolution_stack[-1] if self._name_resolution_stack else None)

    def push_task_scope(self, task: TaskNode):
        """Push a new task scope onto the current context"""
        scope = TaskNameResolutionScope(task=task)
        # Add task parameters as 'this' in the scope's variables
        if isinstance(task, TaskNodeCompound):
            scope.variables['this'] = task.params
        self._name_resolution_stack[-1].task_scopes.append(scope)

    def task_scope(self):
        """Get the current task scope"""
        if self._name_resolution_stack and self._name_resolution_stack[-1].task_scopes:
            return self._name_resolution_stack[-1].task_scopes[-1]
        return None

    def pop_task_scope(self):
        """Pop the current task scope"""
        if self._name_resolution_stack and self._name_resolution_stack[-1].task_scopes:
            self._name_resolution_stack[-1].task_scopes.pop()

    def resolve_variable(self, name: str) -> Any:
        """Resolve a variable using the current name resolution context"""
        ret = None
        if self._name_resolution_stack:
            ret = self._name_resolution_stack[-1].resolve_variable(name)
        return ret

    def mkTaskNode(self, task_t, name=None, srcdir=None, needs=None, allow_root_prefix=False, **kwargs):
        """Create a task node from a task type/name.
        
        Args:
            task_t: Task type or name to create node from
            name: Optional name override for the node
            srcdir: Optional source directory
            needs: Optional list of task dependencies
            allow_root_prefix: If True (CLI usage), try prepending root package name if exact match fails
            **kwargs: Additional parameters to set on the task
        """
        self._log.debug("--> mkTaskNode: %s" % task_t)
        ret = None

        task = None
        if task_t in self._task_m.keys():
            task = self._task_m[task_t]
        elif self.loader is not None:
            task = self.loader.findTask(task_t)
            
            # If not found and CLI usage is allowed, try with root package prefix
            if task is None and allow_root_prefix and self.root_pkg is not None:
                qualified_name = f"{self.root_pkg.name}.{task_t}"
                task = self.loader.findTask(qualified_name)
                if task is not None:
                    self._log.debug("Found task %s as %s with root prefix" % (task_t, qualified_name))

            if task is None:
                type = None
                if task_t in self._type_m.keys():
                    type = self._type_m[task_t]
                
                if type is None:
                    type = self.loader.findType(task_t)
                
                if type is not None:
                    if srcdir is None:
                        srcdir = os.path.dirname(type.srcinfo.file)
                    ret = TaskNodeLeaf(
                        name=name,
                        srcdir=srcdir,
                        params=type.paramT(),
                        ctxt=self._ctxt,
                        task=DataCallable(type.paramT))
                    self._task_node_m[name] = ret
                else:
                    raise Exception(self._task_not_found_message(task_t))

        elif task_t in self._type_m.keys():
            # Create a task around the type
            type = self._type_m[task_t]
            if srcdir is None:
                srcdir = os.path.dirname(type.srcinfo.file)
            ret = TaskNodeLeaf(
                name=name,
                srcdir=srcdir,
                params=type.paramT(),
                ctxt=self._ctxt,
                task=DataCallable(type.paramT)
            )
            self._task_node_m[name] = ret
        else:
            self._log.debug("Fallthrough")

        if ret is None:
            if task is None:
                raise Exception(self._task_not_found_message(task_t))

            self.push_name_resolution_context(task.package)

            try:
                # Reject direct invocation of abstract tasks
                if getattr(task, "abstract", False) and not self.in_uses():
                    raise Exception("Cannot invoke abstract task '%s' directly; use it via 'uses:' or as an override replacement" % task.name)
                # `node_params` carries the programmatic kwargs down to where
                # the node's params are built, and marks this as the node that
                # -D/-P overrides apply to. Both used to be applied *here*,
                # after the node came back fully built -- which was too late
                # for a `run:` body that references an overridden parameter.
                # Passing a dict (empty is fine) is the "top node" signal;
                # recursive _mkTaskNode calls pass None and are untouched, so
                # the set of nodes that receive overrides is unchanged.
                ret = self._mkTaskNode(
                    task,
                    name=name,
                    srcdir=srcdir,
                    eval=self._eval,
                    node_params=kwargs)

                if needs is not None:
                    for need in needs:
                        ret.needs.append((need, False))
            finally:
                # Clean up package context if we created one
                self.pop_name_resolution_context()

        self._log.debug("<-- mkTaskNode: %s" % task_t)
        return ret
    
    def mkDataItem(self, type, name=None, **kwargs):
        self._log.debug("--> mkDataItem: %s" % type)

        tt = None
        if type in self._type_m.keys():
            tt = self._type_m[type]
        elif self.loader is not None:
            tt = self.loader.findType(type)

        if tt is None:
            raise Exception(f"Type {type} does not exist")
        
        if tt in self._type_node_m.keys():
            tn = self._type_node_m[tt]
        else:
#            tn = self._mkDataItem(tt)
            tn = tt.paramT
            self._type_node_m[tt] = tn

        ret = tn()

        for k, v in kwargs.items():
            if hasattr(ret, k):
                setattr(ret, k, v)
            else:
                raise Exception("Data item %s parameters do not include %s" % (name, k))

        self._log.debug("<-- mkDataItem: %s" % name)
        return ret
    
    def _findType(self, pkg, name):
        tt = None
        if name in pkg.type_m.keys():
            tt = pkg.type_m[name]
        else:
            for subpkg in pkg.pkg_m.values():
                tt = self._findType(subpkg, name)
                if tt is not None:
                    break
        return tt
    
    def _mkDataItem(self, tt : Type):
        field_m = {}

        # Save the type name in each instance 
        field_m["type"] = (str, tt.name)
        exclude_s = set()
        exclude_s.add("type")

        self._mkDataItemI(tt, field_m, exclude_s)

        ret = pydantic.create_model(tt.name, __base__=TaskDataItem, **field_m)

        return ret
    
    def _mkDataItemI(self, tt : Type, field_m, exclude_s):
        # First, identify cases where the value is set
        for pt in tt.params.values():
            if pt.name not in exclude_s:
                if pt.type is not None:
                    # Defining a new attribute
                    field_m[pt.name] = (str, pt.value)
                else:
                    # TODO: determine whether 
                    field_m[pt.name] = (str, None)
        if tt.uses is not None:
            self._mkDataItemI(tt.uses, field_m, exclude_s)

    def _findTask(self, pkg, name):
        task = None
        if name in pkg.task_m.keys():
            task = pkg.task_m[name]
        else:
            for subpkg in pkg.pkg_m.values():
                task = self._findTask(subpkg, name)
                if task is not None:
                    break
        return task
    
    def _resolve_on_error(self, task, srcdir=None):
        """Resolve the task.on_error string (module:function) to a Python callable.
        
        Returns None if task.on_error is None or empty.
        """
        on_error = getattr(task, 'on_error', None)
        if not on_error:
            return None
        if ':' in on_error:
            module_name, func_name = on_error.rsplit(':', 1)
        else:
            raise ValueError(
                "on_error '%s' must be in 'module:function' form" % on_error)
        import importlib
        mod = importlib.import_module(module_name)
        return getattr(mod, func_name)

    def _mkTaskNode(self,
                    task : Task,
                    name=None,
                    srcdir=None,
                    params=None,
                    hierarchical=False,
                    eval=None,
                    node_params=None):

        # Apply override substitution before anything else
        task = self._findOverride(task)

        # A cell of a `select:` family is built from the family's single body
        # task with this cell's axis values bound -- the same construction a
        # matrix cell gets, differing only in that the node carries the cell's
        # registered name. Doing it here (rather than inside the family) is what
        # makes a cell an ordinary node: it lands in the node memo under that
        # name, so two consumers of `sim-img.prof` share one build, and a cell
        # nobody asks for is never constructed at all.
        if getattr(task, 'select_bindings', None) is not None:
            return self._mkSelectCellNode(task, name)

        # Compute the `uses`-chain task type-names once (reused for the build
        # context below and the node stamp at exit).
        _chain = self._uses_chain_task_names(task)

        # Publish this node's (uses-chain, path) as the current build context so
        # a matcher-gated `set:` rebind can narrow to it while its params are
        # evaluated. Saved/restored (recursion-safe) below.
        _saved_build_ctx = self._cur_build_ctx
        self._cur_build_ctx = (
            _chain, name if name is not None else getattr(task, 'name', None))

        if not hierarchical:
            self._task_rundir_s.append([self.rundir])

        # If the task has an enable condition, evaluate
        # that now
        iff = True
        if task.iff is not None:
            self._log.debug("Evaluate iff condition \"%s\"" % task.iff)
            iff = self._expandParam(task.iff, eval)

            if iff:
                self._log.debug("Condition \"%s\" is true" % task.iff)
            else:
                self._log.debug("Condition \"%s\" is false" % task.iff)

        # Determine how to build this node. Cross-cutting concerns (override,
        # iff, memoization) have already been handled above; now select an
        # elaborator. A type may bind a custom TaskElaborator (resolved along the
        # `uses` chain); otherwise the standard kind-based interior is used. The
        # default path is byte-identical to the pre-elaborator behavior, so any
        # flow that binds no elaborator is unaffected (Feature A invariant #1).
        if iff:
            elab_name, elaborator = self._resolve_elaborator(task)
            # Alias-proof re-entrancy guard: an elaborator (e.g. hdlsim's
            # backend_select) rebuilds the SAME node name via ctxt.buildDefault
            # after rebinding `uses`. If that node name is already being
            # elaborated higher in the stack, this is a self-typed rebuild --
            # fall through to the default interior rather than re-fire (which,
            # under package-uses-package type aliasing, would loop forever and
            # exhaust memory). Complements the type-name _elab_active guard.
            _eff_name = name if name is not None else getattr(task, 'name', None)
            if elaborator is not None and _eff_name is not None \
                    and _eff_name in self._elab_active_names:
                elaborator = None
            if elaborator is not None:
                # Push an elaboration scope for publish()/lookup(); the first
                # elaborator in the chain sees build-global-constant context and
                # is the only one permitted to read `args` (invariant #4). Mark
                # the bound type active so a self-typed rebuild doesn't re-fire.
                self._elab_ctxt_s.append({})
                self._elab_active.add(elab_name)
                if _eff_name is not None:
                    self._elab_active_names.add(_eff_name)
                is_root_elab = (len(self._elab_ctxt_s) == 1)
                try:
                    ctxt = BuilderElabCtxt(
                        builder=self, srcdir=srcdir, params=params,
                        hierarchical=hierarchical, eval=eval,
                        is_root=is_root_elab,
                        node_params=node_params, task=task)
                    ret = elaborator(
                        ctxt, task, _eff_name if _eff_name is not None else task.name)
                finally:
                    self._elab_active.discard(elab_name)
                    if _eff_name is not None:
                        self._elab_active_names.discard(_eff_name)
                    self._elab_ctxt_s.pop()
                # A custom elaborator builds its own interior, which this
                # method cannot reach into, so its node settles params after
                # the fact -- unchanged from before Phase C.
                self._apply_node_params(ret, task, node_params)

                # ...and because the interior evaluated `produces:` against the
                # params as they stood BEFORE the line above, a `with:`/kwarg or
                # -D value never reached it: `mode: test` would advertise
                # `mode: run`, and downstream matching on a produces attribute
                # would miss the artifact. Re-evaluate from the raw patterns now
                # that params are settled. `ret.taskdef` is the (possibly
                # rebound) task the elaborator actually built, so a backend's
                # own `produces:` override is preserved.
                # The node's task scope is what makes a bare `${{ sim }}`
                # resolve to *this* node's parameter, so re-push it for the
                # re-evaluation; without it the reference does not resolve and
                # ProducesEvaluator quietly keeps the raw source text.
                if node_params:
                    _td = getattr(ret, "taskdef", None)
                    _pat = getattr(_td, "produces", None) if _td is not None else None
                    if _pat is not None and getattr(ret, "params", None) is not None:
                        from .produces_eval import ProducesEvaluator
                        self.push_task_scope(ret)
                        try:
                            ret.produces = ProducesEvaluator(
                                eval if eval is not None else self._eval
                            ).evaluate(_pat, ret.params)
                        finally:
                            self.pop_task_scope()
            else:
                ret = self._build_default_interior(
                    task, name, srcdir, params, hierarchical, eval,
                    node_params=node_params)
        else:
            if name is None:
                name = task.name
            
            if params is None:
                # Build paramT lazily
                if task.paramT is None:
                    if task.param_defs is not None or (task.uses and (task.uses.paramT or task.uses.param_defs)):
                        param_builder = ParamBuilder(eval or self._eval)
                        task.paramT = param_builder.build_param_type(task)
                params = task.paramT() if task.paramT else None

            if params:
                self._expandParams(params, eval)

            if srcdir is None:
                srcdir = os.path.dirname(task.srcinfo.file)

            # Create a null task
            ret = TaskNodeLeaf(
                name=name,
                srcdir=srcdir,
                params=params,
                passthrough=task.passthrough,
                consumes=task.consumes,
                consumes_declared=getattr(task, 'consumes_declared', False),
                task=NullCallable(task.run),
                ctxt=None,
                iff=False)
            self._task_node_m[name] = ret
            self._apply_node_params(ret, task, node_params)


        if not hierarchical:
            self._task_rundir_s.pop()

        # Restore the enclosing build context.
        self._cur_build_ctx = _saved_build_ctx

        # Stamp the node's `uses`-chain task type-names (most-derived first) so
        # the `set:` `uses:` matcher can test is-a against it (Phase 3/4). Only
        # set when empty so a custom elaborator that already populated it wins.
        if ret is not None and hasattr(ret, "uses_chain") and not ret.uses_chain:
            ret.uses_chain = _chain

        # Apply forceful `set:` param rules (bare names under a scope item) that
        # select this node (overrides `with:`, yields to CLI; Phase 4).
        if ret is not None and hasattr(ret, "params") and self._set_scopes:
            self._apply_set_force_rules(ret, task, name)

        # Evaluate this task's contract against the node just built. Last,
        # deliberately: everything a check should see -- the override-resolved
        # task, the elaborated interior, the filtered needs -- is in place.
        if ret is not None and iff:
            self._run_checks(task, ret)

        return ret

    def _uses_chain_task_names(self, task) -> List[str]:
        """Ordered, de-duplicated task TYPE names along `task`'s `uses` chain
        (most-derived first — e.g. [foo.Run, hdlsim.SimRun]). Mirrors
        ParamBuilder._uses_chain_pkg_names but collects task names, giving the
        `set:` `uses:` matcher its is-a set (Phase 3)."""
        names = []
        seen = set()
        for current in iter_uses_chain(task):
            nm = getattr(current, 'name', None)
            if nm is not None and nm not in seen:
                seen.add(nm)
                names.append(nm)
        return names

    def _build_default_interior(self, task, name, srcdir, params, hierarchical,
                                eval, select_needs=None, node_params=None):
        """The standard kind-based node construction (control / strategy /
        compound / leaf) plus needs wiring. This is the default elaborator's
        implementation; it is also what `ElabCtxt.buildDefault` invokes, so a
        custom elaborator can delegate to it. `select_needs`, when provided,
        filters a compound/leaf/strategy task's declared needs before wiring
        (the DefaultCompoundElaborator.selectNeeds hook)."""
        if hasattr(task, 'control') and task.control is not None:
            # Runtime control flow construct (needs-filtering N/A)
            node = self._buildControlNode(
                task, name, srcdir, params, hierarchical, eval)
            # These two kinds build no `run:` body of their own, so there is
            # nothing here that has to see the final values first; they keep
            # the post-hoc application.
            self._apply_node_params(node, task, node_params)
            return node
        elif task.strategy is not None and getattr(task.strategy, 'select', None) is not None:
            node = self._applySelect(
                task, name, srcdir, params, hierarchical, eval,
                select_needs=select_needs, node_params=node_params)
            return node
        elif task.strategy is not None:
            node = self._applyStrategy(
                task, name, srcdir, params, hierarchical, eval,
                select_needs=select_needs)
            self._apply_node_params(node, task, node_params)
            return node
        elif self._isCompound(task):
            return self._mkTaskCompoundNode(
                task, name=name, srcdir=srcdir, params=params,
                hierarchical=hierarchical, eval=eval, select_needs=select_needs,
                node_params=node_params)
        else:
            return self._mkTaskLeafNode(
                task, name=name, srcdir=srcdir, params=params,
                hierarchical=hierarchical, eval=eval, select_needs=select_needs,
                node_params=node_params)

    def _apply_node_params(self, node, task, node_params):
        """Settle a node's parameters: programmatic kwargs first, then -D/-P.

        Precedence is `default -> with:/kwargs -> -P -> -D -> --flag`: a
        `mkTaskNode(**kwargs)` value is how the *description* constructs the
        node, and `-D` is the user overriding the description from outside,
        so `-D` wins. `node_params is None` means this is not the node the
        caller asked for (a recursive build), and nothing is applied.
        """
        if node_params is None:
            return
        params = getattr(node, "params", None)
        for k, v in node_params.items():
            if params is not None and hasattr(params, k):
                setattr(params, k, v)
            else:
                raise Exception(
                    "Task %s parameters do not include %s" % (task.name, k))
        self._apply_task_param_overrides(node, task)

    def _build_task_params(self, task, eval=None, node_params=None):
        """Build and return a task's params instance (evaluating ${{ }} incl.
        resolve()), without constructing a node. Used by ElabCtxt so a custom
        elaborator can read a resolved param (e.g. hdlsim's `sim`) to decide how
        to build the node.

        The full precedence ladder is applied here -- `default -> with:/kwargs
        -> -P -> -D -> --flag` -- so an elaborator reads the *same* value the
        node will settle on. Without this an elaborator that decides from a
        parameter would silently decide from the declared default, which is
        exactly what a `-D` is meant to change (see
        docs/proposals/expansion_phase_ladder.md: load is the one moment when
        values are guaranteed not to be final; elaboration must not repeat that
        mistake).
        """
        ev = eval if eval is not None else self._eval
        if task.paramT is None:
            if task.param_defs is not None or (task.uses and (task.uses.paramT or task.uses.param_defs)):
                paramT = ParamBuilder(ev).build_param_type(task)
                if ev is self._eval:
                    task.paramT = paramT
            else:
                paramT = None
        else:
            paramT = task.paramT
        params = paramT() if paramT else None
        if params is not None:
            self._expandParams(params, ev)
            # kwargs first, then -P/-D/--flag, mirroring _apply_node_params.
            if node_params:
                for k, v in node_params.items():
                    if hasattr(params, k):
                        setattr(params, k, v)
            self._apply_task_param_overrides(_ParamsHolder(params), task)
        return params

    def lookupTask(self, name):
        """Resolve a task *type* by full name without building a node. Used by
        elaborators (e.g. backend selection) that need the concrete task to
        rebind `uses`."""
        t = self._task_m.get(name)
        if t is None and self.loader is not None:
            t = self.loader.findTask(name)
        return t

    def register_elaborator(self, type_name: str, elaborator):
        """Bind a TaskElaborator to a task *type* (by full name). Resolution
        walks the `uses` chain, so binding an abstract type covers every task
        that `uses:` it. Packages that ship elaborators call this at
        package-add time (see Feature C / hdlsim)."""
        self._elaborator_m[type_name] = elaborator

    def _resolve_elaborator(self, task):
        """Resolve the elaborator bound to `task`'s type, walking the `uses`
        chain (nearest declaration wins). Returns (type_name, callable) where
        `callable(ctxt, task, name) -> TaskNode`, or (None, None) when nothing is
        bound -- the common case, which uses the default interior.

        Two binding sources, checked per chain node (nearest wins):
          * a declarative ``elaborate: <module>:<function>`` clause on the task
            type (the function *is* the elaborator); and
          * a programmatic binding registered via ``register_elaborator`` (a
            ``TaskElaborator`` object -- its ``.elaborate`` bound method is
            returned).
        A binding whose type is currently being elaborated (`_elab_active`) is
        skipped, so a self-typed rebuild falls through (re-entrancy guard)."""
        for current in iter_uses_chain(task):
            name = getattr(current, 'name', None)
            if name is not None and name not in self._elab_active:
                ref = getattr(current, 'elaborate', None)
                if ref:
                    return name, self._load_elaborate_fn(ref)
                obj = self._elaborator_m.get(name)
                if obj is not None:
                    return name, obj.elaborate
        return None, None

    def _resolve_requires(self, task):
        """The check instances in effect for `task`, accumulated along `uses:`.

        Unlike `_resolve_elaborator`, this **accumulates**: a leaf that uses a
        capability that uses an archetype is subject to all three levels. That
        union is what makes a base project's contract enforceable at all.

        Nearest-wins per `(check type, id)`, so a nearer level restating the
        same check replaces the farther one -- the override channel, and the
        reason `id:` exists (a task may legitimately carry two `std.check.Needs`
        requirements with different parameters).
        """
        out, seen = [], set()
        for current in iter_uses_chain(task):
            for req in getattr(current, 'requires', ()) or ():
                ident = ""
                values = getattr(req, 'paramT', None)
                if values is not None:
                    ident = getattr(values, 'id', "") or ""
                key = (getattr(req, 'name', ''), ident)
                if key in seen:
                    continue
                seen.add(key)
                out.append(req)
        return out

    def _run_checks(self, task, node):
        """Evaluate `task`'s contract against the node just built.

        Called after override resolution, after `iff:`, and after elaboration,
        which is what makes it useful rather than pedantic:

          * after OVERRIDE -- the check sees the effective task, so a leaf's
            `override: src-rtl` is what satisfies a requirement the base
            declared on `src-rtl`. This is the whole mechanism;
          * after `iff:` -- a node that does not exist is not checked;
          * after ELABORATION -- needs are wired and filtered, so a check sees
            the graph rather than the declaration.

        Memoization gives "once per node" for free, so a shared upstream task
        is checked once and diagnostics are not duplicated.
        """
        # A `uses:` chain link is built as its own node under the SAME name, so
        # without this a base's requirements would fire against the base task --
        # outside the context of the task that derives from it, and before its
        # override had a chance to satisfy them. The derived task's
        # `_resolve_requires` already accumulates the whole chain, so checking
        # only the outermost build loses nothing and is what "once per node,
        # on the effective task" means.
        if self.in_uses() or self._uses_impl_depth:
            return

        reqs = self._resolve_requires(task)
        if not reqs:
            return

        # The invoked root's needs are not final until `--needs` has been wired,
        # which necessarily happens after the node exists. Checking it here would
        # report against an empty need-set and reject a correct command line, so
        # the root's checks are deferred and flushed once the CLI has had its
        # say (see flushDeferredChecks).
        if getattr(node, 'name', None) in self._deferred_check_names:
            self._deferred_checks.append((task, node))
            return

        needs = []
        for entry in getattr(node, 'needs', ()) or ():
            n = entry[0] if isinstance(entry, tuple) else entry
            if n is not None:
                needs.append(n)

        for req in reqs:
            values = getattr(req, 'paramT', None)
            severity = (getattr(values, 'severity', 'error') or 'error')
            if severity == 'off':
                continue
            fn = self._resolve_check_fn(req)
            if fn is None:
                self.error(
                    "check type '%s' has no `check:` implementation" % (
                        getattr(req, 'name', '?'),))
                continue
            ctxt = CheckCtxt(
                task=task, node=node, needs=needs, params=values,
                check_name=getattr(req, 'name', '?'),
                severity=severity,
                hint=(getattr(values, 'hint', '') or ''),
                builder=self)
            try:
                fn(ctxt)
            except Exception as e:
                self.error("check '%s' on task '%s' raised: %s" % (
                    getattr(req, 'name', '?'), task.name, e))

    def deferCheckFor(self, name):
        """Hold back checks for the node called `name` until flushed."""
        self._deferred_check_names.add(name)

    def flushDeferredChecks(self):
        """Run the checks held back by `deferCheckFor`, now that the node is
        final. Idempotent: the pending list is drained."""
        pending, self._deferred_checks = self._deferred_checks, []
        self._deferred_check_names = set()
        for task, node in pending:
            self._run_checks(task, node)

    def _resolve_check_fn(self, req):
        """The callable bound to a check instance, walking its type chain."""
        current = req
        seen = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            ref = getattr(current, 'check', None)
            if ref:
                return self._load_elaborate_fn(ref)
            current = getattr(current, 'uses', None)
        # A check instance is a fresh Type without a `uses` link back to its
        # declared type (_instantiateTag builds it that way), so fall back to
        # looking the type up by name.
        name = getattr(req, 'name', None)
        if name and self.loader is not None:
            typ = self.loader.findType(name)
            while typ is not None:
                ref = getattr(typ, 'check', None)
                if ref:
                    return self._load_elaborate_fn(ref)
                typ = getattr(typ, 'uses', None)
        return None

    def _load_elaborate_fn(self, ref):
        """Import and cache the ``module:function`` (or ``module.function``)
        callable named by an ``elaborate:`` clause."""
        fn = self._elaborate_fn_cache.get(ref)
        if fn is None:
            import importlib
            sep = ':' if ':' in ref else '.'
            module_name, func_name = ref.rsplit(sep, 1)
            mod = importlib.import_module(module_name)
            fn = getattr(mod, func_name)
            self._elaborate_fn_cache[ref] = fn
        return fn

    def _buildControlNode(self, task, name, srcdir, params, hierarchical, eval):
        """
        Build a runtime control flow node (if, while, do-while, repeat, match).
        
        Args:
            task: TaskDef with control field
            name: Task name
            srcdir: Source directory
            params: Parameters
            hierarchical: Whether to use hierarchical rundir
            eval: ExprEval instance
            
        Returns:
            TaskNodeControl subclass instance
        """
        from .task_node_if import TaskNodeIf
        from .task_node_do_while import TaskNodeDoWhile
        from .task_node_while import TaskNodeWhile
        from .task_node_repeat import TaskNodeRepeat
        from .task_node_match import TaskNodeMatch
        
        self._log.debug(f"--> _buildControlNode {task.name}, type={task.control.type}")
        
        if name is None:
            name = task.name or task.root or task.export
        
        if srcdir is None and task.srcinfo:
            srcdir = os.path.dirname(task.srcinfo.file)
        
        # Build parameters if needed
        if params is None:
            if task.paramT is None:
                if task.param_defs is not None or (task.uses and (task.uses.paramT or task.uses.param_defs)):
                    param_builder = ParamBuilder(eval or self._eval)
                    task.paramT = param_builder.build_param_type(task)
            params = task.paramT() if task.paramT else None
        
        # Create the appropriate control node type
        if task.control.type == 'if':
            node = TaskNodeIf(
                name=name,
                srcdir=srcdir,
                params=params,
                ctxt=self._ctxt,
                control_def=task.control,
                body_tasks=task.body,
                else_tasks=task.control.else_body
            )
        elif task.control.type == 'match':
            node = TaskNodeMatch(
                name=name,
                srcdir=srcdir,
                params=params,
                ctxt=self._ctxt,
                control_def=task.control,
                body_tasks=[]  # Match uses cases, not body
            )
        elif task.control.type == 'while':
            node = TaskNodeWhile(
                name=name,
                srcdir=srcdir,
                params=params,
                ctxt=self._ctxt,
                control_def=task.control,
                body_tasks=task.body
            )
        elif task.control.type == 'do-while':
            node = TaskNodeDoWhile(
                name=name,
                srcdir=srcdir,
                params=params,
                ctxt=self._ctxt,
                control_def=task.control,
                body_tasks=task.body
            )
        elif task.control.type == 'repeat':
            node = TaskNodeRepeat(
                name=name,
                srcdir=srcdir,
                params=params,
                ctxt=self._ctxt,
                control_def=task.control,
                body_tasks=task.body
            )
        else:
            raise NotImplementedError(f"Control type '{task.control.type}' not yet implemented")
        
        self._log.debug(f"<-- _buildControlNode {task.name}")
        return node
    
    def _applyStrategy(self, task, name, srcdir, params, hierarchical, eval, select_needs=None):
        self._log.debug("--> _applyStrategy %s" % task.name)

        if name is None:
            name = task.name

        if srcdir is None:
            srcdir = os.path.dirname(task.srcinfo.file)

        if params is None:
            # Build paramT lazily
            if task.paramT is None:
                if task.param_defs is not None or (task.uses and (task.uses.paramT or task.uses.param_defs)):
                    param_builder = ParamBuilder(self._eval)
                    task.paramT = param_builder.build_param_type(task)
            params = task.paramT() if task.paramT else None

        ret = TaskNodeCompound(
            name=name,
            srcdir=srcdir,
            params=params,
            ctxt=self._ctxt,
            max_failures=getattr(task, 'max_failures', -1),
            run=self._resolve_on_error(task, srcdir))

        if ret.input is None:
            raise Exception("Task %s does not have an input" % task.name)

        self._gatherNeeds(task, ret, select_needs)

        ret.input.needs.extend(ret.needs)

        ctxt = TaskGenCtxt(
            rundir=self.get_rundir(),
            srcdir=srcdir,
            input=ret.input,
            basename=ret.name,
            builder=self
        )

        # In both cases, the result 'lives' inside a compound task

        res = None
        if task.strategy.generate is not None:
            callable = ExecGenCallable(body=task.strategy.generate.run, srcdir=srcdir)
            input = TaskGenInputData(params=params)

            res = callable(ctxt, input)
        elif len(task.strategy.matrix):
            matrix = {}
            matrix_items = []
            _axis_eval = eval if eval is not None else self._eval
            for k in task.strategy.matrix.keys():
                matrix[k] = None
                axis = task.strategy.matrix[k]
                # An axis value may be a `${{ }}` expression resolving to a list
                # (e.g. `image: "${{ images }}"`) -- evaluate it here so a single
                # package var can drive the fan-out (and be `-D`-overridden).
                if isinstance(axis, str):
                    resolved = _axis_eval.eval(axis) if "${{" in axis else axis
                    if not isinstance(resolved, list):
                        raise Exception(
                            "matrix axis '%s' expression '%s' resolved to %r, "
                            "which is not a list" % (k, axis, resolved))
                    axis = resolved
                matrix_items.append((k, axis))

            res = self._applyStrategyMatrix(task.subtasks, matrix_items, 0, ret.name,
                                            parent_let=self._get_let(task),
                                            parent_set=self._get_set(task))

        tasks = []
        tasks.extend(ret.tasks[1:])

        tasks.extend(ctxt.tasks.copy())
        if res is not None:
            if isinstance(res, list):
                tasks.extend(res)
            else:
                tasks.append(res)

        # Add generated tasks to ret.tasks so they appear in the compound node's subgraph
        for tn in tasks:
            if tn not in ret.tasks:
                ret.tasks.append(tn)

        # Finish hooking this up...
        for tn in tasks:
            if tn is None:
                raise Exception("Generator yielded a null class")
            referenced = None
            for tt in tasks:
                for tnn,_ in tt.needs:
                    if tn == tnn:
                        referenced = tnn
                        break

            refs_internal = None
            for nn,_ in tn.first.needs:
                for tnn in tasks:
                    if nn == tnn:
                        refs_internal = tnn
                        break
                if refs_internal is not None:
                    break
            
            if not refs_internal:
                if ret.input is None:
                    raise Exception("Adding None input")
                if tn == ret.input:
                    raise Exception("Adding input to itself")
                
                # Graph generators completely handle their inputs
                if task.strategy.generate is None:
                    tn.needs.append((ret.input, False))
            
            if referenced is None:
                if tn is None:
                    raise Exception("Adding None input")
                ret.needs.append((tn, False))

        self._log.debug("<-- _applyStrategy %s" % task.name)
        return ret
    
    def _get_let(self, task):
        """Return the `let` (scoped-variable) block declared on a task, or None.
        The runtime Task carries it directly (populated from its TaskDef)."""
        return getattr(task, 'let', None)

    def _get_set(self, task):
        """Return the `set:` scoped-override list declared on a task, or None.
        The runtime Task carries it directly (populated from its TaskDef)."""
        return getattr(task, 'set_defs', None)

    def _apply_set(self, eval, set_defs, task_name):
        """Evaluate a task's `set:` list and push a SetScope frame onto the
        builder's dynamic override stack (`_set_scopes`), returning the frame so
        the caller can pop it once the subtree is built (see _pop_set_scope).
        Returns None (pushes nothing) when there is nothing to apply.

        Each list item is either an *assignment map* or a *scope item*
        (`{uses?, path?, set: [...]}`). Semantics (design §R2.3):
          * qualified name (has '.') -> variable REBIND read via ${{ pkg.var }};
            narrowed to matched readers when it appears under a scope item.
          * bare name UNDER a scope item -> forceful param SET on matched nodes.
          * bare name at TOP level (no matcher) -> no-op + Info marker.
        A fresh frame is always created so a child subtree never mutates an
        ancestor's bindings."""
        if not set_defs:
            return None

        scope = SetScope(task_name=task_name)
        self._collect_set_items(eval, set_defs, task_name, matchers=[], depth=0,
                                scope=scope)
        if not scope.rebinds and not scope.rules:
            return None
        self._set_scopes.append(scope)
        return scope

    def _collect_set_items(self, eval, items, task_name, matchers, depth, scope):
        """Walk a `set:` list (recursively through scope items), accumulating
        `uses:`/`path:` matchers, and record rebinds/rules onto `scope`."""
        for item in items:
            if not isinstance(item, dict):
                continue
            if 'set' in item:
                sub = list(matchers)
                if item.get('uses'):
                    sub.append(('uses', item['uses']))
                if item.get('path'):
                    sub.append(('path', item['path']))
                self._collect_set_items(eval, item['set'], task_name, sub,
                                        depth + 1, scope)
                continue
            for name, expr in item.items():
                val = expr
                if isinstance(expr, str) and "${{" in expr:
                    val = eval.eval(expr)
                if '.' in name:
                    # Qualified -> variable rebind (narrowed by any matchers).
                    scope.rebinds.append((name, val, list(matchers)))
                elif matchers:
                    # Bare name under a scope item -> forceful param rule.
                    scope.rules.append((name, val, list(matchers), depth))
                else:
                    # Bare name at top level, no matcher -> no-op.
                    self.marker(TaskMarker(
                        msg=("`set:` on task '%s' assigns bare name '%s' with no "
                             "matcher; use a package-qualified name (pkg.%s) to "
                             "rebind a scoped variable, or wrap it in a scope item "
                             "(uses:/path:) to force a parameter" %
                             (task_name, name, name)),
                        severity=SeverityE.Info))

    def _pop_set_scope(self, scope):
        """Pop a SetScope frame pushed by _apply_set (no-op if scope is None)."""
        if scope is not None and self._set_scopes and self._set_scopes[-1] is scope:
            self._set_scopes.pop()

    def _apply_set_force_rules(self, node, task, name):
        """Apply forceful `set:` param rules (bare names under a scope item) to a
        newly created node whose matchers select it. Overrides the instance's
        `with:` but NOT a CLI/-D value; for the same param, the OUTER frame /
        shallower nesting wins (design §R2.4)."""
        if not self._set_scopes:
            return
        params = getattr(node, 'params', None)
        if params is None:
            return
        uses_chain = getattr(node, 'uses_chain', None) or \
            self._uses_chain_task_names(task)
        node_name = getattr(node, 'name', None) or name
        # Gather matching candidates, then pick the outermost per param.
        cands = {}   # param_name -> (frame_idx, depth, value)
        for fi, scope in enumerate(self._set_scopes):          # outer-first
            for pname, pval, matchers, depth in scope.rules:
                if not node_matches(matchers, uses_chain, node_name):
                    continue
                key = (fi, depth)
                if pname not in cands or key < cands[pname][:2]:
                    cands[pname] = (fi, depth, pval)
        for pname, (_fi, _d, pval) in cands.items():
            if not hasattr(params, pname):
                continue           # rule may target other matched nodes; skip
            if self._param_cli_pinned(node_name, pname):
                continue           # CLI is the ceiling
            self._force_node_param(node, pname, pval)

    def _param_cli_pinned(self, node_name, param_name) -> bool:
        """True if `param_name` on the node named `node_name` was pinned from the
        CLI (-D/-P), so a `set:` force rule must yield to it. Matched by full
        instance name, leaf name, and bare leaf-param name."""
        leaf = node_name.split('.')[-1] if node_name else None
        for key in (node_name, leaf):
            if key in self.task_param_overrides and \
                    param_name in self.task_param_overrides[key]:
                return True
        if self.leaf_param_overrides and param_name in self.leaf_param_overrides:
            return True
        return False

    def _force_node_param(self, node, param_name, value):
        """Coerce and set a forced param value on a node, using the built
        params model's field type (which includes inherited params)."""
        params = node.params
        field = type(params).model_fields.get(param_name)
        param_type = field.annotation if field is not None else None
        coerced = self._coerce_param_value(value, param_type, param_name,
                                           getattr(node, 'name', '?'))
        setattr(params, param_name, coerced)

    def _apply_let(self, eval, let_defs, task_name):
        """Evaluate `let` bindings in declaration order and layer them into the
        eval context's reserved __let__ dict. Later entries may reference earlier
        ones by bare name (within the block only). Returns nothing; mutates `eval`.

        A fresh merged dict is always created ({**parent, **new}) so a child
        subtree never mutates an ancestor's bindings (invariant §0.3).

        The bindings live ONLY in __let__ — read via resolve(). They are exposed
        as plain variables *while the block is being evaluated* (so a later entry
        can reference an earlier one by bare name), then removed, so a bare
        ${{ name }} in the subtree does NOT see a let binding (invariant §0.1)."""
        if not let_defs:
            return
        parent = eval.expr_eval.variables.get('__let__') or {}
        merged = dict(parent)                      # fresh dict — never mutate parent
        variables = eval.expr_eval.variables
        saved = {}                                 # keys we shadowed: restore after
        added = []                                 # keys we introduced: pop after
        for name, expr in let_defs.items():
            val = expr
            if isinstance(expr, str) and "${{" in expr:
                # Allow resolve() inside a let value (implicit-name form binds to
                # this let entry's name).
                eval.expr_eval.current_param_name = name
                val = eval.eval(expr)
                eval.expr_eval.current_param_name = None
            merged[name] = val
            # Temporarily expose so a later let entry can reference this one by
            # bare name during THIS block's evaluation only.
            if name in variables:
                if name not in saved:
                    saved[name] = variables[name]
            elif name not in added:
                added.append(name)
            variables[name] = val
        # Withdraw the temporary plain vars so the bindings live only in __let__.
        for name in added:
            variables.pop(name, None)
        for name, v in saved.items():
            variables[name] = v
        variables['__let__'] = merged

    def _applyStrategyMatrix(self, subtasks, matrix_items, idx, parent_name=None, parent_let=None, parent_set=None):
        """
        Expand matrix combinations and create task nodes.
        
        Args:
            subtasks: List of Task objects from the body
            matrix_items: List of (key, values) tuples for matrix variables
            idx: Unused, kept for compatibility
            parent_name: Name of parent task to prefix generated task names
            
        Returns:
            List of TaskNode objects, one for each matrix combination
        """
        import itertools
        from .param_builder import ParamBuilder
        from .param_ref_eval import ParamRefEval
        
        if not matrix_items:
            return []
        
        # Extract keys and value lists
        keys = [item[0] for item in matrix_items]
        value_lists = [item[1] for item in matrix_items]
        
        # Generate all combinations using cartesian product
        result = []
        for combo_values in itertools.product(*value_lists):
            # Build matrix dict for this combination
            matrix_dict = dict(zip(keys, combo_values))

            # Calculate indices for this combination
            indices = []
            for value, value_list in zip(combo_values, value_lists):
                indices.append(value_list.index(value))

            for subtask in subtasks:
                result.append(self._mkCellNode(
                    subtask, matrix_dict, dict(zip(keys, indices)),
                    parent_name=parent_name,
                    parent_let=parent_let, parent_set=parent_set))

        return result

    def resolveTaskParams(self, task):
        """`{param: value}` for `task` with its `${{ }}` defaults evaluated.

        For the CLI-facing views (`dfm run <task> --help`, `dfm show task`),
        which otherwise print the raw expression -- `[default: ${{ build }}]`
        rather than `[default: opt]` -- because a lazily-evaluated default is
        stored as its source text.

        Deliberately stops short of `mkTaskNode`: only the parameter type is
        built, so nothing upstream is constructed and a display command cannot
        fail (or do work) because of a task's dependencies. `-D`/`-P` are
        applied, so what is shown is what this invocation would use.
        """
        if task is None:
            return {}
        srcdir = os.path.dirname(task.srcinfo.file) if task.srcinfo else None
        prev_srcdir = self._eval.expr_eval.variables.get("srcdir")
        if srcdir is not None:
            self._eval.set("srcdir", srcdir)

        # A select cell's parameters are written against its axis bindings
        # (`${{ this.view }}`), so without them the cell reports the template
        # rather than what it will actually run with.
        bindings = getattr(task, 'select_bindings', None)
        prev_this = self._eval.expr_eval.variables.get('this')
        prev_matrix = self._eval.expr_eval.variables.get('matrix')
        if bindings:
            self._eval.expr_eval.variables['this'] = dict(bindings)
            self._eval.expr_eval.variables['matrix'] = dict(bindings)

        self.push_name_resolution_context(task.package)
        try:
            paramT = ParamBuilder(self._eval).build_param_type(task)
            if paramT is None:
                return {}
            params = paramT()
            self._expandParams(params, self._eval)
            self._apply_task_param_overrides(_ParamsHolder(params), task)
            return {f: getattr(params, f, None)
                    for f in getattr(type(params), 'model_fields', {})}
        finally:
            self.pop_name_resolution_context()
            self._eval.set("srcdir", prev_srcdir)
            for _k, _v in (('this', prev_this), ('matrix', prev_matrix)):
                if _v is None:
                    self._eval.expr_eval.variables.pop(_k, None)
                else:
                    self._eval.expr_eval.variables[_k] = _v

    def resolveSelectDefault(self, task):
        """`{axis: value}` a select family's `default:` currently resolves to,
        or None if `task` is not a family with a binding default.

        Same purpose as `resolveTaskParams`: `show task` would otherwise report
        the family's default as the expression that computes it.
        """
        select = getattr(getattr(task, 'strategy', None), 'select', None)
        if select is None or select.mode != "alias":
            return None
        values = self.resolveTaskParams(task)
        eval_ctx = self._selectDefaultEval_values(values)
        ret = {}
        for axis, value in select.default.items():
            if isinstance(value, str) and "${{" in value:
                value = eval_ctx.eval(value)
            ret[axis] = value
        return ret

    def mkSelectPartialNode(self, task):
        """Build a family from a command-line partial cell key.

        The resolver hands back a copy of the family task carrying
        `select_partial`; that binding cannot survive a round-trip through a
        name, so this is the entry point the CLI uses instead of
        `mkTaskNode(name)`. Everything else -- the package name-resolution
        context, the `node_params` "this is the top node" signal that makes
        -D/--flag apply -- has to match `mkTaskNode`, or the family would
        resolve its default from declared values only.
        """
        self.push_name_resolution_context(task.package)
        try:
            return self._mkTaskNode(
                task, name=task.name, eval=self._eval, node_params={})
        finally:
            self.pop_name_resolution_context()

    def _applySelect(self, task, name, srcdir, params, hierarchical, eval,
                     select_needs=None, node_params=None):
        """Build the node the bare family name denotes.

        A select family is never a unit of work -- the cells are. What the
        family name means is declared, not guessed:

          * `default: {axis: value}` (or omitted) -- the family is an **alias**
            for one cell, and the node returned *is* that cell's node. It is
            registered under the family name too, so `needs: [sim-img]` and
            `needs: [sim-img.tlm.opt]` reach the same build.
          * `default: all`, or a binding naming several values -- the family is
            a **gate** over that sub-family.
          * `default: none` -- only cells are addressable; naming the family is
            an error rather than a build of nothing.
        """
        select = task.strategy.select
        if name is None:
            name = task.name

        if params is None:
            # Built here, not left to the compound path below: the `default:`
            # binding is an expression over these very parameters, so they have
            # to exist before the family knows which cell it denotes.
            if task.paramT is None:
                if task.param_defs is not None or (
                        task.uses and (task.uses.paramT or task.uses.param_defs)):
                    task.paramT = ParamBuilder(
                        eval or self._eval).build_param_type(task)
            params = task.paramT() if task.paramT else None
            if params is not None:
                self._expandParams(params, eval)
                # `-D` / `--flag` must reach the family's parameters *before*
                # the default binding is evaluated, or a select would resolve
                # from its declared default no matter what the user asked for --
                # the same mistake elaborators used to make (ChangeLog 1.19.0).
                self._apply_task_param_overrides(_ParamsHolder(params), task)

        if select.mode == "none":
            raise Exception(
                "task '%s' is a select family declared `default: none`, so it "
                "cannot be built or depended on directly. Name one of its "
                "cells: %s" % (
                    task.name,
                    ", ".join("%s.%s" % (task.name, k) for k in select.cells)))

        cells = self._selectedCells(task, select, params, eval,
                                    partial=getattr(task, 'select_partial', None))

        if select.mode == "alias" and len(cells) == 1:
            cell = self._selectCellTask(task, cells[0])
            node = self._mkSelectCellNode(cell)
            # The family name is an alias for the cell, so both names must find
            # the same node -- otherwise a second consumer using the other
            # spelling would build the artifact twice.
            self._task_node_m[name] = node
            return node

        # A gate over several cells. The compound owns no work of its own; the
        # cells are its needs, and each is still shared by name.
        ret = TaskNodeCompound(
            name=name,
            srcdir=srcdir if srcdir is not None else os.path.dirname(task.srcinfo.file),
            params=params,
            ctxt=self._ctxt,
            max_failures=getattr(task, 'max_failures', -1),
            run=self._resolve_on_error(task, srcdir))
        self._gatherNeeds(task, ret, select_needs)
        ret.input.needs.extend(ret.needs)

        for key in cells:
            cell_node = self._mkSelectCellNode(self._selectCellTask(task, key))
            cell_node.needs.append((ret.input, False))
            ret.tasks.append(cell_node)
        self._task_node_m[name] = ret
        self._apply_node_params(ret, task, node_params)
        return ret

    def _selectDefaultEval_values(self, values):
        """`_selectDefaultEval` over an already-extracted {name: value} map."""
        from .param_ref_eval import ParamRefEval
        import copy
        ctx = ParamRefEval()
        base = self._eval
        if base is not None:
            ctx.expr_eval.variables = copy.deepcopy(base.expr_eval.variables)
            if base.expr_eval.name_resolution:
                ctx.set_name_resolution(base.expr_eval.name_resolution)
        ctx.expr_eval.variables.update(values)
        ctx.expr_eval.variables['this'] = dict(values)
        return ctx

    def _selectDefaultEval(self, params, eval):
        """An eval context in which a `default:` expression sees the family's
        own parameters by bare name (and under `this`).

        The family's parameter is the knob the user turns -- through its
        declared default, the package variable that default came from, `-D`, or
        its `--flag`. Binding it as a plain name is what makes
        `default: {build: "${{ build }}"}` mean the obvious thing, and it
        deliberately shadows a same-named package variable: the parameter
        already defaults from it, so the parameter is the more specific answer.
        """
        from .param_ref_eval import ParamRefEval
        import copy

        base = eval if eval is not None else self._eval
        ctx = ParamRefEval()
        if base is not None:
            ctx.expr_eval.variables = copy.deepcopy(base.expr_eval.variables)
            if base.expr_eval.name_resolution:
                ctx.set_name_resolution(base.expr_eval.name_resolution)
        if params is not None:
            values = {f: getattr(params, f, None)
                      for f in getattr(type(params), 'model_fields', {})}
            ctx.expr_eval.variables.update(values)
            ctx.expr_eval.variables['this'] = values
        return ctx

    def _selectCellTask(self, family, key):
        """The registered Task for cell `key` of `family`."""
        cell = family.package.task_m.get("%s.%s" % (family.name, key))
        if cell is None:
            raise Exception(
                "select family '%s' has no cell '%s'" % (family.name, key))
        return cell

    def _selectedCells(self, task, select, params, eval, partial=None):
        """The cell keys the family currently denotes.

        `default:` values may be `${{ }}` expressions over the family's own
        parameters -- that is the wire from a task-level variable (and its
        `--flag`, and the package variable it defaults from) to which cell gets
        built. They are resolved here, at graph build, because that is the first
        moment the parameter's final value is known.

        `partial` is a command-line partial cell key (`sim-img.prof`): it pins
        the axes it names and leaves the rest to the default, which is why it
        can only come from the CLI.
        """
        if select.mode == "all" and not partial:
            return list(select.cells.keys())

        cell_eval = self._selectDefaultEval(params, eval)
        binding = {}
        base = select.default if select.mode != "all" else {}
        for axis, value in base.items():
            if isinstance(value, str) and "${{" in value:
                value = cell_eval.eval(value)
            binding[axis] = value
        if partial:
            # A partial key names some axes outright; every other axis keeps
            # whatever the default (and therefore -D/--flag) says.
            binding.update(partial)

        wanted = {}
        for axis, value in binding.items():
            values = value if isinstance(value, list) else [value]
            values = [v for v in values if v is not None and v != ""]
            unknown = [v for v in values if v not in select.axes[axis]]
            if unknown:
                raise Exception(
                    "task '%s': %s is not a value of select axis '%s'. "
                    "Accepted: %s" % (
                        task.name, ", ".join("'%s'" % u for u in unknown), axis,
                        ", ".join(str(v) for v in select.axes[axis])))
            wanted[axis] = values

        keys = [k for k, cell in select.cells.items()
                if all(cell[a] in vs for a, vs in wanted.items())]
        if not keys:
            raise Exception(
                "task '%s': the select default %s matches no cell" % (
                    task.name, binding))
        return keys

    def _mkSelectCellNode(self, cell, name=None):
        """Build one cell of a `select:` family.

        `cell` is the task registered at load under `<family>.<key>`; its
        interior is the family's body task, evaluated with this cell's axis
        values bound to `this`/`matrix`.
        """
        family = cell.select_family
        if not family.subtasks:
            raise Exception(
                "select family '%s' has no body task to build cell '%s' from"
                % (family.name, cell.name))
        if name is None:
            name = cell.name

        existing = self._task_node_m.get(name)
        if existing is not None:
            return existing

        # `${{ srcdir }}` must be the FAMILY's directory, not whatever the
        # builder was last looking at. A matrix cell gets this for free -- its
        # parent compound node sets srcdir before the cell's eval context is
        # copied -- but a select cell has no parent node in the graph, so
        # without this a `basedir: "${{ srcdir }}"` default resolves to the root
        # package and the body looks for its sources in the wrong tree.
        family_srcdir = os.path.dirname(family.srcinfo.file)
        prev_srcdir = self._eval.expr_eval.variables.get("srcdir")
        self._eval.set("srcdir", family_srcdir)

        # Build at the TOP of the rundir stack, not nested under whoever asked
        # for the cell. A matrix cell belongs to its parent compound and is
        # rightly nested; a select cell is a shared, independently-addressable
        # artifact, so its rundir must not depend on which consumer happened to
        # trigger construction -- that would move the artifact (and its cache
        # identity) depending on the order consumers appear in the graph.
        self._task_rundir_s.append([self.rundir])
        try:
            return self._mkCellNode(
                family.subtasks[0],
                dict(cell.select_bindings),
                {},
                name=name,
                parent_name=family.name,
                parent_let=self._get_let(family),
                parent_set=self._get_set(family),
                hierarchical=False,
                srcdir=family_srcdir)
        finally:
            self._task_rundir_s.pop()
            self._eval.set("srcdir", prev_srcdir)

    def _mkCellNode(self, subtask, matrix_dict, indices_m, name=None,
                    parent_name=None, parent_let=None, parent_set=None,
                    hierarchical=True, srcdir=None):
        """Build the node for ONE cell of a matrix or select body.

        Shared by both so they cannot drift on what a cell's scope contains:
        the `this`/`matrix` bindings, the parent's `let:`/`set:` layers, and the
        per-cell resolution of a deferred `uses`/`needs`/`name`. A `select` cell
        passes `name` (its registered cell name); a matrix cell leaves it None
        and gets the naming scheme's generated name.
        """
        from .param_builder import ParamBuilder
        from .param_ref_eval import ParamRefEval

        keys = list(matrix_dict.keys())
        combo_values = [matrix_dict[k] for k in keys]
        indices = [indices_m.get(k, 0) for k in keys]

        # Create fresh eval context for each task node
        eval_ctx = ParamRefEval()
        
        # Copy variables from current context
        if hasattr(self, '_eval') and self._eval:
            # Deep copy to avoid mutation
            import copy
            eval_ctx.expr_eval.variables = copy.deepcopy(self._eval.expr_eval.variables)
            if self._eval.expr_eval.name_resolution:
                eval_ctx.set_name_resolution(self._eval.expr_eval.name_resolution)
        
        # Add matrix variables to 'this' scope
        this_vars = eval_ctx.expr_eval.variables.get('this', {})
        if not isinstance(this_vars, dict):
            this_vars = {}
        # Create a fresh copy and update
        this_vars = dict(this_vars)
        this_vars.update(matrix_dict)
        eval_ctx.expr_eval.variables['this'] = this_vars
        
        # Also expose under 'matrix' so ${{ matrix.key }} works
        eval_ctx.expr_eval.variables['matrix'] = dict(matrix_dict)

        # Layer the parent's `let` bindings into this cell's scope so
        # resolve() in the subtree picks up per-cell values
        # (e.g. let: sim: "${{ matrix.sim }}").
        self._apply_let(eval_ctx, parent_let, parent_name)

        # Push the parent's `set:` overrides for this cell so ordinary
        # ${{ pkg.var }} references (in this subtask's params and its
        # whole subtree) resolve to per-cell rebinds
        # (e.g. set: [{ hdlsim.sim: "${{ matrix.sim }}" }]). Popped after
        # the cell's node is fully built.
        _set_scope = self._apply_set(eval_ctx, parent_set, parent_name)
        try:
            # Resolve a deferred (matrix-driven) `uses` for this cell: the
            # body task's `uses` expression (e.g. uvm-${{ this.test }}) is
            # evaluated against this cell's matrix bindings, the referenced
            # task type is looked up, and the node is built from a per-cell
            # copy so the shared subtask template is not mutated.
            eff_subtask = subtask
            if getattr(subtask, 'uses_expr', None) and subtask.uses is None:
                # Evaluate the `uses` expression against this cell's
                # matrix bindings (see _eval_in_cell for the dropped
                # name-resolution rationale).
                uses_name = self._eval_in_cell(eval_ctx, subtask.uses_expr)
                uses_task = self._resolveDeferredUses(uses_name, subtask)
                if uses_task is None:
                    raise Exception(
                        "matrix 'uses' expression '%s' resolved to '%s', "
                        "which is not a known task" % (
                            subtask.uses_expr, uses_name))
                import copy as _copy
                eff_subtask = _copy.copy(subtask)
                eff_subtask.uses = uses_task

            # Build params with matrix-specific eval context
            param_builder = ParamBuilder(eval_ctx)
            paramT = param_builder.build_param_type(eff_subtask)
            params = paramT()

            # Generate unique name using indices
            matrix_bindings = tuple(zip(keys, combo_values))
            matrix_indices = tuple(zip(keys, indices))
            pkg_name = subtask.package.name if hasattr(subtask, 'package') and subtask.package else ""
            root_pkg_name = self.root_pkg.name if self.root_pkg else ""
            parent_leaf = None
            parent_fq = parent_name
            if parent_name:
                parent_leaf = parent_name.rsplit(".", 1)[-1] if "." in parent_name else parent_name
            # A body task's name may itself be an expression over the
            # matrix variables (e.g. `name: "${{ this.test }}"`). Evaluate
            # it against this cell's bindings so the node name and its
            # rundir segment read `...uvm-test.wb-smoke` rather than the
            # raw `...uvm-test.${{ this.test }}` template (see
            # _eval_in_cell for the dropped name-resolution rationale).
            fq_name = subtask.name
            leaf_name = subtask.leafname
            if isinstance(fq_name, str) and "${{" in fq_name:
                try:
                    fq_name = self._eval_in_cell(eval_ctx, fq_name)
                    leaf_name = fq_name.rsplit(".", 1)[-1] if "." in fq_name else fq_name
                except Exception:
                    fq_name = subtask.name
                    leaf_name = subtask.leafname
            if name is None:
                # A matrix cell has no identity of its own, so the naming scheme
                # derives one from the parent and the cell's bindings. A select
                # cell arrives with its registered name -- which is the point:
                # that name is what `needs:` and the CLI address, and what the
                # node memo keys on so two consumers share one build.
                matrix_ctx = MatrixNamingContext(
                    fq_name=fq_name,
                    leaf_name=leaf_name,
                    package_name=pkg_name,
                    root_package_name=root_pkg_name,
                    parent_leaf=parent_leaf,
                    parent_fq=parent_fq,
                    matrix_bindings=matrix_bindings,
                    matrix_indices=matrix_indices,
                )
                name = self._naming_scheme.matrix_task_node_name(matrix_ctx)

            # Build the task node with matrix-specific params
            node = self._mkTaskNode(
                eff_subtask,
                name=name,
                srcdir=srcdir,
                params=params,
                hierarchical=hierarchical,
                eval=eval_ctx
            )

            # Resolve any matrix-driven `needs` for this cell: evaluate
            # each deferred need expression against this cell's bindings
            # (see _eval_in_cell), look up the referenced task, and wire
            # its node in.
            for need_expr in getattr(eff_subtask, 'needs_expr', None) or []:
                need_name = self._eval_in_cell(eval_ctx, need_expr)
                need_task = self._resolveDeferredUses(
                    need_name, eff_subtask,
                    fragment=getattr(eff_subtask, 'needs_expr_fragment', None))
                if need_task is None:
                    raise Exception(
                        "matrix 'needs' expression '%s' resolved to '%s', "
                        "which is not a known task" % (need_expr, need_name))
                need_node = self._getTaskNode(need_task.name)
                node.needs.append((need_node, False))
                # A COMPOUND consumes its dependencies through `input`, not
                # through `needs` -- `_gatherNeeds` gathers into `needs` and
                # then extends `input.needs` from it. A deferred need is wired
                # after that has already happened, so without this it reaches
                # the node and never the interior, and the body compiles
                # without the very thing the cell asked for. Only ever bit
                # matrix bodies that were leaves (SimUVMCase); a select body is
                # naturally a compound, which is what exposed it.
                if getattr(node, 'input', None) is not None:
                    node.input.needs.append((need_node, False))

            return node
        finally:
            self._pop_set_scope(_set_scope)

    def _eval_in_cell(self, eval_ctx, expr):
        """Evaluate `expr` against a matrix cell's bindings with the
        name-resolution context dropped, so `this`/`matrix` resolve to the cell
        variables (which carry the matrix values) rather than an enclosing
        compound's own `this` scope, which would otherwise shadow them. The
        context is always restored. Used for a cell's deferred `uses`, its
        computed node `name`, and its deferred `needs`."""
        saved_nr = eval_ctx.expr_eval.name_resolution
        eval_ctx.expr_eval.name_resolution = None
        try:
            return eval_ctx.eval(expr)
        finally:
            eval_ctx.expr_eval.name_resolution = saved_nr

    def _resolveDeferredUses(self, name, subtask, fragment=None):
        """Resolve a matrix-driven `uses`/`needs` name (evaluated per cell) to a
        Task type.

        Mirrors the load-time resolution: try the name as given, then qualified
        by the root package and the subtask's fragment. Returns the Task, or
        None if no candidate matches. `fragment` overrides the subtask's
        `uses_expr_fragment` (used for deferred needs, which carry their own).
        """
        frag = fragment if fragment is not None \
            else getattr(subtask, 'uses_expr_fragment', None)
        root = self.root_pkg.name if self.root_pkg else None
        candidates = [name]
        if root:
            candidates.append("%s.%s" % (root, name))
            if frag:
                candidates.append("%s.%s.%s" % (root, frag, name))
        if frag:
            candidates.append("%s.%s" % (frag, name))
        for cand in candidates:
            if self.root_pkg is not None and cand in self.root_pkg.task_m:
                return self.root_pkg.task_m[cand]
            if cand in self._task_m:
                return self._task_m[cand]
        # Fall back to a leaf-name match: fragment-qualified tasks are keyed as
        # `<pkg>.<fragment>.<leaf>`, and the fragment segment is not always known
        # at the point the expression is stashed. Match the trailing leaf name.
        suffix = ".%s" % name
        for task_m in (getattr(self.root_pkg, 'task_m', None), self._task_m):
            if not task_m:
                continue
            matches = [t for k, t in task_m.items() if k == name or k.endswith(suffix)]
            if len(matches) == 1:
                return matches[0]
        return None

    def _isCompound(self, task):
        if isinstance(task, Task):
            if task.subtasks is not None and len(task.subtasks):
                return True
            elif task.uses is not None:
                return self._isCompound(task.uses)
        else:
            return False
    
    def _getTaskNode(self, name):
        if name in self._task_node_m.keys():
            return self._task_node_m[name]
        else:
            return self.mkTaskNode(name)
    
    def _mkTaskLeafNode(self,
                        task : Task,
                        name=None,
                        srcdir=None,
                        params=None,
                        hierarchical=False,
                        eval=None,
                        select_needs=None,
                        node_params=None) -> TaskNode:
        self._log.debug("--> _mkTaskLeafNode %s" % task.name)

        # A `let` block only affects a task's subtree; a leaf has none.
        _let = self._get_let(task)
        if _let:
            self.marker(TaskMarker(
                msg="`let` on task '%s' has no subtree; it will have no effect" % task.name,
                severity=SeverityE.Warning))

        if name is None:
            name = task.name

        if srcdir is None:
            srcdir = os.path.dirname(task.srcinfo.file)
        
        # Set srcdir to the task's source directory for parameter evaluation
        prev_srcdir = self._eval.expr_eval.variables.get("srcdir")
        self._eval.set("srcdir", srcdir)
        
        if params is None:
            # Build paramT lazily if not already built.
            # When a non-default eval context is provided (e.g. from a
            # matrix strategy), always rebuild so that ${{ }} references
            # are expanded with the current iteration's variables instead
            # of reusing stale defaults cached on the shared Task object.
            needs_rebuild = task.paramT is None or (eval is not None and eval is not self._eval)
            if needs_rebuild:
                if task.param_defs is not None:
                    self._log.debug(f"Building paramT for {task.name} from param_defs")
                    param_builder = ParamBuilder(eval or self._eval)
                    paramT = param_builder.build_param_type(task)
                elif task.uses and (task.uses.paramT or task.uses.param_defs):
                    # Task has no param_defs but uses another task with params
                    # Build paramT from the uses chain
                    self._log.debug(f"Building paramT for {task.name} from uses chain")
                    param_builder = ParamBuilder(eval or self._eval)
                    paramT = param_builder.build_param_type(task)
                else:
                    self._log.warning(f"Task {task.name} has no paramT or param_defs")
                    # Create empty paramT
                    paramT = pydantic.create_model(f"Task{task.name}Params")
                # Only cache on the Task object when using the default
                # eval context; matrix iterations must not pollute the
                # shared definition.
                if eval is None or eval is self._eval:
                    task.paramT = paramT
            else:
                paramT = task.paramT
            
            params = paramT()

        # Create and push task scope for parameter resolution
        node = TaskNodeLeaf(
            name=name,
            srcdir=srcdir,
            params=params,
            ctxt=self._ctxt,
            passthrough=task.passthrough,
            consumes=task.consumes,
            consumes_declared=getattr(task, 'consumes_declared', False),
            produces=task.produces,
            uptodate=_resolve_uses_attr(task, "uptodate"),
            taskdef=task,
            task=None,
            inherits_rundir=(_resolve_uses_attr(task, "rundir") == RundirE.Inherit))
            
        self.push_task_scope(node)

        self.task_scope().variables["rundir"] = "/".join([str(e) for e in self.get_rundir()])
        
        # Now expand parameters in the scope context
        # Note: Most evaluation now happens in ParamBuilder, but we still
        # need to handle runtime-only variables like 'rundir'
        self._expandParams(params, eval)

        # Settle the parameters -- kwargs, then -D/-P -- BEFORE the body is
        # expanded. This is the ordering fix: overrides used to land after
        # the whole node was built, so `run: echo ${{ seed }}` rendered the
        # declared default while `node.params.seed` carried the override.
        self._apply_node_params(node, task, node_params)

        # Evaluate produces patterns after params are set, in THIS node's eval
        # context. The shared builder context has no `this`, so a produce
        # pattern written against a strategy cell's axis values -- which is how
        # an artifact advertises which variant it is,
        # `{type: SimImg, build: "${{ this.build }}"}` -- would otherwise be
        # stored as its own source text and match nothing.
        if task.produces is not None:
            from .produces_eval import ProducesEvaluator
            evaluator = ProducesEvaluator(eval if eval is not None else self._eval)
            node.produces = evaluator.evaluate(task.produces, params)

        # Expand the body, once per node, from this node's evaluated params.
        # Position matters twice over: the task scope pushed above is what
        # makes `${{ <param> }}` resolve to *this* node's value, and `srcdir`
        # is still the task's own directory (it is restored just below).
        task_run = task.run
        if task_run is not None and "${{" in task_run:
            # `${{ srcdir }}` in a body means the directory of the file that
            # *wrote* the body -- which differs from this node's srcdir when
            # the body is inherited through `uses:`.
            run_srcdir = getattr(task, "run_srcdir", None)
            if run_srcdir is not None and run_srcdir != srcdir:
                self._eval.set("srcdir", run_srcdir)

            # `rundir` is a phase-3 (run) name: the node's final rundir is not
            # settled here -- the Unique segment is pushed below -- and the
            # callable resolves it at execution. Bind it to its own literal
            # for the duration, exactly as PackageLoader.__post_init__ does,
            # so the reference survives expansion instead of picking up the
            # parent's rundir from the task scope.
            _scope_vars = self.task_scope().variables
            _prev_rundir = _scope_vars.get("rundir")
            _scope_vars["rundir"] = "${{ rundir }}"
            try:
                task_run = self._expandParam(
                    task_run, eval if eval is not None else self._eval)
            finally:
                _scope_vars["rundir"] = _prev_rundir
                self._eval.set("srcdir", srcdir)

        # Restore previous srcdir after all parameter evaluation is complete
        self._eval.set("srcdir", prev_srcdir)


        if task.rundir == RundirE.Unique and self._inherit_rundir_depth == 0:
            _leaf_ctx = self._build_task_naming_context(task, name)
            _leaf_segment = self._naming_scheme.rundir_segment(_leaf_ctx)
            if _leaf_segment is not None:
                self.enter_rundir(_leaf_segment)

        callable = None

        if task_run is not None:
            shell = task.shell if task.shell is not None else "shell"
            if shell in self._shell_m.keys():
                self._log.debug("Use shell implementation")
                self._log.debug("task_run: %s" % task_run)
                callable = self._shell_m[shell](
                    task_run, 
                    os.path.dirname(task.srcinfo.file), 
                    task.shell)
            else:
                raise Exception("Shell %s not found" % shell)
            
        # Setup the callable
        if callable is None and task.uses is not None:
            if isinstance(task.uses, Type):
                callable = DataCallable(task.uses.paramT)
            else:
                # The base's node is built purely to borrow its callable. It is
                # an implementation detail, not something anyone asked for, so
                # its `requires:` contract must not fire here -- that contract
                # is for whoever DERIVES from it, and is evaluated on the
                # derived node (which accumulates it along the `uses` chain).
                self._uses_impl_depth += 1
                try:
                    uses = self._getTaskNode(task.uses.name)
                finally:
                    self._uses_impl_depth -= 1
                callable = uses.task
        
        if callable is None:
            callable = NullCallable(task_run)

        node.task = callable

        self._task_node_m[name] = node
        node.rundir = self.get_rundir()

        if len(self._task_node_s):
            node.parent = self._task_node_s[-1]

        # Now, link up the needs
        self._log.debug("--> processing needs")
        self._gatherNeeds(task, node, select_needs)
        self._log.debug("<-- processing needs")

        if task.rundir == RundirE.Unique and self._inherit_rundir_depth == 0:
            self.leave_rundir()

        # Clean up
        self.pop_task_scope()

        self._log.debug("<-- _mkTaskLeafNode %s" % task.name)
        return node
    
    def _mkTaskCompoundNode(self,
                            task : Task,
                            name=None,
                            srcdir=None,
                            params=None,
                            hierarchical=False,
                            eval=None,
                            select_needs=None,
                            node_params=None) -> TaskNode:
        self._log.debug("--> _mkTaskCompoundNode %s" % task.name)

        if name is None:
            name = task.name

        if srcdir is None:
            srcdir = os.path.dirname(task.srcinfo.file)

        # Set srcdir to the task's source directory for parameter evaluation
        prev_srcdir = self._eval.expr_eval.variables.get("srcdir")
        self._eval.set("srcdir", srcdir)

        if params is None:
            # Build paramT lazily.  Same rebuild-vs-cache logic as
            # _mkTaskLeafNode: avoid reusing stale cached paramT when
            # a matrix-specific eval context is active.
            needs_rebuild = task.paramT is None or (eval is not None and eval is not self._eval)
            if needs_rebuild:
                if task.param_defs is not None or (task.uses and (task.uses.paramT or task.uses.param_defs)):
                    param_builder = ParamBuilder(eval or self._eval)
                    paramT = param_builder.build_param_type(task)
                else:
                    paramT = None
                if eval is None or eval is self._eval:
                    task.paramT = paramT
            else:
                paramT = task.paramT
            params = paramT() if paramT else None

        # expand any variable references (runtime-only variables like rundir)
        if params:
            self._expandParams(params, eval)

        # Create a new task scope for this compound task
        node = TaskNodeCompound(
            name=name,
            srcdir=srcdir,
            params=params,
            ctxt=self._ctxt,
            max_failures=getattr(task, 'max_failures', -1),
            run=self._resolve_on_error(task, srcdir))

        # Settle kwargs and -D/-P before the body is built: a compound's
        # subtasks read the parent's params (via `this` and as bare names),
        # so they must be final before descending.
        self._apply_node_params(node, task, node_params)

        # Restore previous srcdir after all parameter evaluation
        self._eval.set("srcdir", prev_srcdir)

        # Push this compound's rundir segment. All compounds in a single `uses`
        # chain are the same logical task and are built with the same `name`, so
        # each Unique link would otherwise re-push an identical segment -- nesting
        # the rundir one extra level per chain link (e.g.
        # `.../wb-smoke_0/wb-smoke_0/wb-smoke_0/...`). Skip the push when the
        # segment already sits at the top of the stack, collapsing those
        # consecutive duplicates to a single directory while still nesting
        # genuinely distinct parents. (A guard on in_uses() would over-suppress:
        # the most-derived task in the chain may not itself be Unique, so the one
        # legitimate push can come from a base link.)
        _pushed_compound_rundir = False
        if task.rundir == RundirE.Unique and self._inherit_rundir_depth == 0:
            _compound_ctx = self._build_task_naming_context(task, name)
            _compound_segment = self._naming_scheme.rundir_segment(_compound_ctx)
            _cur_rundir = self._task_rundir_s[-1]
            _dup_top = (len(_cur_rundir) > 0 and _cur_rundir[-1] == _compound_segment)
            if _compound_segment is not None and not _dup_top:
                self.enter_rundir(_compound_segment)
                _pushed_compound_rundir = True

        if task.uses is not None:
            # This is a compound task that is based on
            # another. Create the base implementation
            task_uses = task.uses

            if not self.in_uses():
                # Determine whether this task is overridden
                task_uses = self._findOverride(task_uses)

            self.push_task_scope(node)  # Push scope before enter_uses
            self.enter_uses()
            # Propagate rundir:inherit through the uses chain: increment
            # depth so all tasks built inside the expansion (compound
            # and leaf) skip their own rundir segments.
            if task.rundir == RundirE.Inherit:
                self._inherit_rundir_depth += 1
            try:
                uses_node = self._mkTaskNode(
                    task_uses,
                    name=name, 
                    srcdir=srcdir,
                    params=params,
                    hierarchical=True,
                    eval=eval)
            finally:
                if task.rundir == RundirE.Inherit:
                    self._inherit_rundir_depth -= 1
            self.leave_uses()
            
            if not isinstance(uses_node, TaskNodeCompound):
                # Non-compound base with no implementation is parameter-only;
                # allow the compound task to provide its own body.
                _has_impl = (isinstance(task_uses, Task) and
                             (task_uses.run is not None or
                              (task_uses.subtasks is not None and len(task_uses.subtasks) > 0)))
                if _has_impl:
                    raise Exception("Task %s is not compound" % task_uses)
                self.pop_task_scope()
                self.push_task_scope(node)
            else:
                # Copy properties from uses_node to our node
                node.tasks = uses_node.tasks
                node.input = uses_node.input
                node.needs = uses_node.needs
                self.pop_task_scope()  # Pop the scope
        else:
            # Node represents the terminal node of the sub-DAG
            self.push_task_scope(node)  # Push scope for non-uses compound task

        if len(self._task_node_s):
            node.parent = self._task_node_s[-1]

        self._task_node_m[name] = node
        self._task_node_s.append(node)

        node.rundir = self.get_rundir()

        # Put the input node inside the compound task's rundir
        _sentinel_ctx = self._build_task_naming_context(task, name, is_sentinel=True)
        _sentinel_segment = self._naming_scheme.sentinel_rundir_segment(_sentinel_ctx)
        if _sentinel_segment is not None:
            self.enter_rundir(_sentinel_segment)
            node.input.rundir = self.get_rundir()
            self.leave_rundir()
        else:
            node.input.rundir = self.get_rundir()
            node.input.save_exec_data = False

        self._log.debug("--> processing needs (%s) (%d)" % (task.name, len(task.needs)))
        # Resolve needs with THIS node off the task-node stack. A need is a
        # dependency, not a hierarchical child: if the needed task has to be
        # built here (not yet cached), it must not be mis-parented as a subtask
        # of the needer. Leaving `node` on the stack would set the needed
        # (possibly top-level) task's `.parent` to `node`, corrupting the
        # hierarchy -- which breaks rundir nesting and sends the dot writer's
        # parent-walk into the needer (an effectively unbounded render).
        self._task_node_s.pop()
        try:
            _needs = select_needs(task.needs) if select_needs is not None else task.needs
            for need in _needs:
                need_n = self._getTaskNode(need.name)
                if need_n is None:
                    raise Exception("Failed to find need %s" % need.name)
                elif need_n.iff:
                    self._log.debug("Add need %s with %d dependencies" % (need_n.name, len(need_n.needs)))
                    node.input.needs.append((need_n, False))
                else:
                    self._log.debug("Needed node %s is not enabled" % need_n.name)
        finally:
            self._task_node_s.append(node)
        self._log.debug("<-- processing needs")

        # TODO: handle strategy

        # Need a local map of name -> task 
        # For now, build out local tasks and link up the needs
        tasks = []

        # Inject compound task params into a CHILD eval context so body tasks
        # can reference them via ${{ param_name }}. Using a fresh context (rather
        # than mutating the shared eval in place) makes `eval is not self._eval`
        # true when the subtasks are built, which forces their paramT to be
        # re-evaluated against THESE param values instead of reusing a paramT
        # cached from an earlier build with different values (e.g. the compound's
        # own defaults, or a prior standalone build). This mirrors how the matrix
        # strategy scopes its per-iteration variables.
        base_eval = eval if eval is not None else self._eval
        body_eval = ParamRefEval()
        body_eval.expr_eval.variables = dict(base_eval.expr_eval.variables)
        _name_res = getattr(base_eval.expr_eval, "name_resolution", None)
        if _name_res is not None:
            body_eval.set_name_resolution(_name_res)
        if params is not None:
            for field_name in type(params).model_fields.keys():
                body_eval.set(field_name, getattr(params, field_name))

        # Layer this compound's `let` bindings into the body eval context so
        # resolve() in the subtree reads them.
        self._apply_let(body_eval, self._get_let(task), task.name)

        # Push this compound's `set:` overrides so ordinary ${{ pkg.var }}
        # references in the subtree resolve to them (design §R2). Popped after
        # the body is built.
        _set_scope = self._apply_set(body_eval, self._get_set(task), task.name)

        try:
            for t in task.subtasks:
                nn = self._mkTaskNode(t, hierarchical=True, eval=body_eval)
                # A compound that `uses` another compound adopts the base's
                # subtask nodes (node.tasks = uses_node.tasks, above). If this
                # compound declares a subtask with the SAME name, it OVERRIDES
                # the adopted one rather than adding a duplicate. This is the
                # normal same-name override semantic, and it is what keeps the
                # package-uses-package re-export from double-instantiating:
                # `<pkg>.uvm-sim-run` uses `<base>.uvm-sim-run` and re-exports a
                # copy of the base's `sim-run` subtask, so without this the
                # single `sim-run` would appear twice (adopted + re-exported).
                _replaced = False
                for _i, _existing in enumerate(node.tasks):
                    if _existing.name == nn.name:
                        node.tasks[_i] = nn
                        _replaced = True
                        break
                if not _replaced:
                    node.tasks.append(nn)
                tasks.append((t, nn))
        finally:
            self._pop_set_scope(_set_scope)

        # Pop the node stack, since we're done constructing the body
        self._task_node_s.pop()

        # Fill in 'needs'
        for t, tn in tasks:
            self._log.debug("Process node %s" % t.name)

            referenced = None
            for tt in node.tasks:
                self._log.debug("  Checking task %s" % tt.name)
                for tnn,_ in tt.needs:
                    self._log.debug("    Check against need %s" % tnn.name)
                    if tn == tnn:
                        referenced = tnn
                        break

            refs_internal = None
            # Assess how this task is connected to others in the compound node
            for nn,_ in tn.first.needs:
                self._log.debug("Need: %s" % nn.name)
                for _,tnn in tasks:
                    if nn == tnn:
                        refs_internal = tnn
                        break
                if refs_internal is not None:
                    break
            
            if not refs_internal:
                # Any node that doesn't depend on an internal
                # task is a top-level task
                self._log.debug("Node %s doesn't reference any internal node" % t.name)
                tn.needs.append((node.input, False))
            else:
                self._log.debug("Node %s references internal node %s" % (t.name, refs_internal.name))

            if referenced is not None:
                self._log.debug("Node %s has internal needs: %s" % (tn.name, referenced.name))
            else:
                # Add this task as a dependency of the output
                # node (the root one)
                self._log.debug("Add node %s as a top-level dependency" % tn.name)
                node.needs.append((tn, False))

        if _pushed_compound_rundir:
            self.leave_rundir()

        # Clean up task scope if we created one for a non-uses compound task
        if not task.uses:
            self.pop_task_scope()

        return node

    def _convertValueToType(self, value, target_type):
        """Convert an expanded value to the destination type.

        eval() returns strings for spliced values, so scalar destinations
        (bool/int/float) still need string->scalar conversion here. Container
        destinations (list/map) and stringification are delegated to the shared
        coerce_to_kind() so both expansion sites behave identically. See
        docs/proposals/typed_param_expansion.md §5.2.
        """
        # DeferredExpr values are resolved at runtime; the dst kind travels with
        # them (see _expandParam) so we must not coerce the placeholder now.
        if isinstance(value, DeferredExpr):
            return value

        kind = normalize_type(target_type)

        # Scalar string coercions kept here — coerce_to_kind defers these to us.
        if kind is TypeKind.BOOL and isinstance(value, str):
            low = value.lower()
            if low in ('true', '1', 'yes', 'on'):
                return True
            elif low in ('false', '0', 'no', 'off', ''):
                return False
            else:
                return value  # let pydantic report it
        if kind in (TypeKind.INT, TypeKind.FLOAT) and isinstance(value, str):
            try:
                return (int if kind is TypeKind.INT else float)(value)
            except (ValueError, TypeError):
                return value  # let pydantic report it

        # LIST / MAP / STR / ANY -> deterministic, dst-driven coercion.
        try:
            return coerce_to_kind(value, kind)
        except ParamTypeError:
            # Preserve leniency at this site: let downstream pydantic surface it
            # rather than hard-failing graph construction.
            return value

    def _expandParams(self, params, eval):
        for name in type(params).model_fields.keys():
            value = getattr(params, name)
            new_val = self._expandParam(value, eval)
            # Get the expected type from the model field
            field_info = type(params).model_fields[name]
            expected_type = field_info.annotation
            # Convert the value to the expected type if needed
            new_val = self._convertValueToType(new_val, expected_type)
            setattr(params, name, new_val)


    _TMPL_EXPR_RE = re.compile(r'\$\{\{\s*(.*?)\s*\}\}')

    def _check_runtime_ref(self, text):
        """Extract expressions from ${{ }} delimiters, parse each, and
        check whether any references runtime data (inputs, memento).
        Returns (True, ast) for the first match, or (False, None)."""
        for m in self._TMPL_EXPR_RE.finditer(text):
            try:
                ast = parse_expr(m.group(1))
                if ast and references_runtime_data(ast):
                    return True, ast
            except:
                pass
        return False, None

    def _expandParam(self, value, eval):
        new_val = value
        if type(value) == str:
            if value.find("${{") != -1:
                # Parse the expression to check for runtime references
                try:
                    is_runtime, ast = self._check_runtime_ref(value)
                    
                    # Check if expression references runtime data (inputs, memento)
                    if is_runtime:
                        # Capture static context for deferred evaluation
                        static_context = {}
                        if len(self._name_resolution_stack) > 0:
                            # Capture current variable context
                            # Note: This is a shallow copy; variables should be immutable
                            # ParamRefEval has expr_eval.variables, not variables directly
                            if hasattr(eval, 'variables'):
                                static_context = dict(eval.variables)
                            elif hasattr(eval, 'expr_eval'):
                                static_context = dict(eval.expr_eval.variables)
                        
                        # Create deferred expression for runtime evaluation
                        self._log.debug("Param: Deferring expression \"%s\" (references runtime data)" % value)
                        return DeferredExpr(value, ast, static_context)
                    
                except Exception as e:
                    # If parsing fails, fall through to normal evaluation
                    self._log.debug("Failed to parse expression for deferred check: %s" % e)
                
                # Normal static evaluation
                if len(self._name_resolution_stack) > 0:
                    eval.set_name_resolution(self._name_resolution_stack[-1])
                new_val = eval.eval(value)
                self._log.debug("Param: Evaluate expression \"%s\" => \"%s\"" % (value, new_val))
        elif isinstance(value, list):
            new_val = []
            for i,elem in enumerate(value):
                if isinstance(elem, str):
                    if elem.find("${{") != -1:
                        # Check for runtime references
                        try:
                            is_runtime, ast = self._check_runtime_ref(elem)
                            if is_runtime:
                                # Handle both ExprEval and ParamRefEval
                                if hasattr(eval, 'variables'):
                                    static_context = dict(eval.variables) if len(self._name_resolution_stack) > 0 else {}
                                elif hasattr(eval, 'expr_eval'):
                                    static_context = dict(eval.expr_eval.variables) if len(self._name_resolution_stack) > 0 else {}
                                else:
                                    static_context = {}
                                new_val.append(DeferredExpr(elem, ast, static_context))
                                continue
                        except:
                            pass  # Fall through to normal evaluation
                        
                        if len(self._name_resolution_stack) > 0:
                            eval.set_name_resolution(self._name_resolution_stack[-1])
                        resolved = eval.eval(elem)
                        new_val.append(resolved)
                    else:
                        new_val.append(elem)
                elif isinstance(elem, dict):
                    for k, v in elem.items():
                        if isinstance(v, str):
                            if v.find("${{") != -1:
                                # Check for runtime references
                                try:
                                    is_runtime, ast = self._check_runtime_ref(v)
                                    if is_runtime:
                                        # Handle both ExprEval and ParamRefEval
                                        if hasattr(eval, 'variables'):
                                            static_context = dict(eval.variables) if len(self._name_resolution_stack) > 0 else {}
                                        elif hasattr(eval, 'expr_eval'):
                                            static_context = dict(eval.expr_eval.variables) if len(self._name_resolution_stack) > 0 else {}
                                        else:
                                            static_context = {}
                                        new_val.append({k: DeferredExpr(v, ast, static_context)})
                                        continue
                                except:
                                    pass
                                
                                if len(self._name_resolution_stack) > 0:
                                    eval.set_name_resolution(self._name_resolution_stack[-1])
                                resolved = eval.eval(v)
                                new_val.append({k: resolved})
                            else:
                                new_val.append({k: v})
                        else:
                            new_val.append(elem)
                else:
                    new_val.append(elem)
        elif isinstance(value, dict):
            new_val = {}
            for k, v in value.items():
                if isinstance(v, str):
                    if v.find("${{") != -1:
                        # Check for runtime references
                        try:
                            is_runtime, ast = self._check_runtime_ref(v)
                            if is_runtime:
                                # Handle both ExprEval and ParamRefEval
                                if hasattr(eval, 'variables'):
                                    static_context = dict(eval.variables) if len(self._name_resolution_stack) > 0 else {}
                                elif hasattr(eval, 'expr_eval'):
                                    static_context = dict(eval.expr_eval.variables) if len(self._name_resolution_stack) > 0 else {}
                                else:
                                    static_context = {}
                                new_val[k] = DeferredExpr(v, ast, static_context)
                                continue
                        except:
                            pass
                        
                        if len(self._name_resolution_stack) > 0:
                            eval.set_name_resolution(self._name_resolution_stack[-1])
                            resolved = eval.eval(v)
                            new_val[k] = resolved
                        else:
                            new_val[k] = v
                    else:
                        new_val[k] = v
                else:
                    new_val[k] = v
        return new_val

    def _gatherNeeds(self, task_t, node, select_needs=None):
        self._log.debug("--> _gatherNeeds %s (%s %d)" % (task_t.name, node.name, len(task_t.needs)))
        if task_t.uses is not None and isinstance(task_t.uses, Task) and not getattr(task_t, 'inherited', False):
            self._gatherNeeds(task_t.uses, node, select_needs)

        _needs = select_needs(task_t.needs) if select_needs is not None else task_t.needs
        for need in _needs:
            need_n = self._getTaskNode(need.name)
            if need_n is None:
                raise Exception("Failed to find need %s" % need.name)
            node.needs.append((need_n, False))
        self._log.debug("<-- _gatherNeeds %s (%d)" % (task_t.name, len(node.needs)))
        

    def _task_not_found_message(self, task_t):
        """Build a user-friendly error message when a task/type cannot be found."""
        all_names = sorted(self._task_m.keys())
        type_names = sorted(self._type_m.keys())

        suggestions = difflib.get_close_matches(task_t, all_names + type_names, n=5, cutoff=0.5)

        if not suggestions and self.loader is not None and hasattr(self.loader, "getSimilarNamesError"):
            loader_hint = self.loader.getSimilarNamesError(task_t, only_tasks=True)
            if loader_hint:
                return "Task '%s' not found.%s" % (task_t, loader_hint)

        msg = "Task '%s' not found." % task_t

        if suggestions:
            msg += " Did you mean: %s?" % ", ".join("'%s'" % s for s in suggestions)
        elif all_names:
            shown = all_names[:10]
            msg += " Available tasks: %s" % ", ".join("'%s'" % n for n in shown)
            if len(all_names) > 10:
                msg += " (and %d more \u2014 run 'dfm run' with no arguments to list all)" % (len(all_names) - 10)
        else:
            msg += " No tasks are registered in the current package."

        return msg

    def error(self, msg, loc=None):
        if loc is not None:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error, loc=loc)
        else:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error)
        self.marker(marker)

    def marker(self, marker):
        self.marker_l(marker)

    def _findOverride(self, task):
        """Check if this task has a substitution registered.
        
        Returns the replacement Task if a substitution exists, otherwise
        the original task.
        """
        if task.name in self._override_m:
            replacement_name = self._override_m[task.name]
            replacement = self._task_m.get(replacement_name)
            if replacement is None and self.loader is not None:
                replacement = self.loader.findTask(replacement_name)
            if replacement is None:
                # Search imported packages by prefix (handles implicit std, etc.)
                parts = replacement_name.split(".", 1)
                if len(parts) == 2:
                    pkg_name, task_short = parts
                    pkg = self._pkg_m.get(pkg_name)
                    if pkg is None and self.root_pkg is not None:
                        # Walk root_pkg's pkg_m for the package
                        pkg = self.root_pkg.pkg_m.get(pkg_name)
                    if pkg is not None:
                        replacement = pkg.task_m.get(replacement_name)
                        if replacement is not None:
                            # Register so subsequent lookups are fast
                            self._task_m[replacement_name] = replacement
            if replacement is None:
                # Search packages reachable through existing tasks' uses chains
                parts = replacement_name.split(".", 1)
                if len(parts) == 2:
                    pkg_name = parts[0]
                    for t in self._task_m.values():
                        if (hasattr(t, 'package') and t.package is not None
                                and t.package.name == pkg_name):
                            replacement = t.package.task_m.get(replacement_name)
                            if replacement is not None:
                                self._task_m[replacement_name] = replacement
                                break
                        if (hasattr(t, 'uses') and t.uses is not None
                                and hasattr(t.uses, 'package')
                                and t.uses.package is not None
                                and t.uses.package.name == pkg_name):
                            replacement = t.uses.package.task_m.get(replacement_name)
                            if replacement is not None:
                                self._task_m[replacement_name] = replacement
                                break
            if replacement is None:
                raise Exception(
                    "Override '%s' -> '%s': replacement task not found"
                    % (task.name, replacement_name))
            self._log.info("Overriding task '%s' with '%s'"
                           % (task.name, replacement_name))
            return replacement
        return task

    def _build_task_naming_context(self, task, name, is_sentinel=False):
        """Build a TaskNamingContext for the given task."""
        fq_name = name if name else task.name
        leaf_name = fq_name.rsplit(".", 1)[-1] if "." in fq_name else fq_name
        pkg_name = task.package.name if hasattr(task, 'package') and task.package else ""
        root_pkg_name = self.root_pkg.name if self.root_pkg else ""
        parent_leaf = None
        parent_fq = None
        if len(self._task_node_s) > 0:
            parent = self._task_node_s[-1]
            parent_fq = parent.name
            parent_leaf = parent.name.rsplit(".", 1)[-1] if "." in parent.name else parent.name
        inherits_rundir = (task.rundir == RundirE.Inherit) if hasattr(task, 'rundir') else False
        sibling_leaves = ()
        if len(self._compound_task_ctxt_s) > 0:
            existing = self._compound_task_ctxt_s[-1].task_m
            sibling_leaves = tuple(
                k.rsplit(".", 1)[-1] if "." in k else k for k in existing.keys()
            )
        return TaskNamingContext(
            fq_name=fq_name,
            leaf_name=leaf_name,
            package_name=pkg_name,
            root_package_name=root_pkg_name,
            parent_leaf=parent_leaf,
            parent_fq=parent_fq,
            inherits_rundir=inherits_rundir,
            is_sentinel=is_sentinel,
            sibling_leaves=sibling_leaves,
        )

    def _apply_task_param_overrides(self, task_node, task):
        """Apply parameter overrides from -D/-P to a task node.
        
        Looks up overrides by:
        1. Full task name (pkg.task)
        2. Leaf task name (task)
        3. Leaf parameter names (for -D param=value)
        """
        overrides = {}
        # param name -> the raw `-D` key that supplied it, for diagnostics. The
        # key is reconstructible because parse_parameter_overrides splits a
        # dotted key into (task_key, param) and leaves a bare key as-is.
        origin = {}

        # Try full task name first
        if task.name in self.task_param_overrides:
            for pname, pvalue in self.task_param_overrides[task.name].items():
                overrides[pname] = pvalue
                origin[pname] = "%s.%s" % (task.name, pname)

        # Also try leaf name
        leaf_name = task.leafname if hasattr(task, 'leafname') else task.name.split('.')[-1]
        if leaf_name in self.task_param_overrides:
            for pname, pvalue in self.task_param_overrides[leaf_name].items():
                overrides[pname] = pvalue
                origin[pname] = "%s.%s" % (leaf_name, pname)

        # Also try leaf parameter names (from -D param=value without task name).
        # "Has this parameter" spans the `uses:` chain, so the bare form and the
        # qualified form agree about which params a derived task has.
        # Keys that named a real param but lost to a higher-precedence entry.
        # They still "found a target", so the diagnostics must not call them
        # unmatched -- that would report a typo where there is none.
        shadowed = []
        if self.leaf_param_overrides and hasattr(task, 'param_defs'):
            task_param_names, _ = collect_task_params(task)
            for param_name, param_value in self.leaf_param_overrides.items():
                # Only apply if this task has this parameter
                if param_name in task_param_names:
                    if param_name not in overrides:  # Don't override explicit task overrides
                        overrides[param_name] = param_value
                        origin[param_name] = param_name
                    else:
                        shadowed.append(param_name)

        # Apply each override
        for param_name, param_value in overrides.items():
            try:
                self._apply_task_param_override(task_node, task, param_name, param_value)
            except Exception as e:
                self.error(f"Failed to apply override for parameter '{param_name}' on task '{task.name}': {e}")
                raise
            if self.override_tracker is not None and param_name in origin:
                self.override_tracker.note_task_bind(origin[param_name], task.name)

        if self.override_tracker is not None:
            for param_name in shadowed:
                self.override_tracker.note_task_bind(param_name, task.name)
    
    def _apply_task_param_override(self, task_node, task, param_name, value):
        """Apply a single parameter override with type coercion.
        
        Args:
            task_node: TaskNode to modify
            task: Task definition
            param_name: Parameter name (must exist in task.param_defs)
            value: Value from -D (string) or -P (any JSON type)
        """
        # Check param exists in task definition. Params inherited via `uses:`
        # count: the node really has them (they are merged into paramT), so
        # refusing to override one would make `-D` unusable on any derived task.
        definitions, types = collect_task_params(task)
        if param_name not in definitions:
            raise ValueError(
                f"Parameter '{param_name}' not found in task '{task.name}'. "
                f"Available parameters: {sorted(definitions.keys())}"
            )

        param_type = types.get(param_name)

        # Coerce value to correct type
        coerced_value = self._coerce_param_value(value, param_type, param_name, task.name)

        # ... then check it against the parameter's declared value set, if any.
        # This is what makes `-D task.detail=ful` fail the way `--detail ful`
        # already does, instead of running the whole flow and degrading later.
        value_set = collect_param_value_sets(task).get(param_name)
        if value_set is not None:
            try:
                warning = check_value_set(
                    coerced_value, value_set, param_type,
                    name="parameter '%s' on task '%s'" % (param_name, task.name))
            except ParamTypeError as e:
                raise ValueError(str(e))
            if warning is not None:
                self._log.warning(warning)

        # Apply to task_node.params
        if hasattr(task_node, 'params') and hasattr(task_node.params, param_name):
            setattr(task_node.params, param_name, coerced_value)

        # Also update param_def.value for consistency -- but only for a param
        # this task declares itself. An inherited ParamDef is the *base's*
        # object, shared by every task deriving from it, so writing to it would
        # leak this task's override into all of its siblings.
        own_defs = getattr(task, 'param_defs', None)
        if own_defs is not None and param_name in own_defs.definitions:
            own_defs.definitions[param_name].value = coerced_value
    
    def _coerce_param_value(self, value, param_type, param_name, task_name):
        """Coerce a CLI/-D (or set:-forced) value to `param_type`.

        Delegates to the single engine-wide policy in
        `param_types.coerce_cli_value` (comma-split for a bare list string,
        TRUTHY bool, int base-0). `strict=True` so a bad int/float fails loudly
        for a task-param override, re-raised as a located ValueError."""
        try:
            return coerce_cli_value(value, param_type, strict=True)
        except ParamTypeError as e:
            raise ValueError(
                "Parameter '%s' on task '%s': %s" % (param_name, task_name, e))
