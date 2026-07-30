"""
CLI Task Resolver — flexible, suffix-based task name resolution for CLI usage.

flow.yaml references use strict, scope-based resolution (PackageScope / LoaderScope).
The CLI, by contrast, needs to support partial names so that users can type the
shortest unambiguous suffix of a fully-qualified task name.

Resolution order:
  1. Exact match against all known FQ task names.
  2. Suffix match against root-scoped tasks (is_root == True).
  3. Fuzzy fallback via difflib for "did you mean?" suggestions.
"""

import dataclasses as dc
import difflib
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .task import Task
    from .package import Package


class TaskResolutionError(Exception):
    """Base for user-facing task resolution errors."""
    pass


class TaskNotFoundError(TaskResolutionError):
    """Raised when no task matches the user-supplied spec."""

    def __init__(self, spec: str, suggestions: List[str] = None,
                 scope_hint: Optional[str] = None):
        self.spec = spec
        self.suggestions = suggestions or []
        self.scope_hint = scope_hint
        super().__init__(self._format())

    def _format(self) -> str:
        msg = "Task '%s' not found." % self.spec
        if self.scope_hint:
            msg += " " + self.scope_hint
        if self.suggestions:
            formatted = ", ".join("'%s'" % s for s in self.suggestions)
            msg += " Did you mean: %s?" % formatted
        else:
            msg += " Run 'dfm run' with no arguments to list all runnable tasks."
        return msg


class AmbiguousTaskError(TaskResolutionError):
    """Raised when a partial name matches more than one root-scoped task."""

    def __init__(self, spec: str, candidates: List['Task']):
        self.spec = spec
        self.candidates = candidates
        super().__init__(self._format())

    def _format(self) -> str:
        names = "\n  ".join(t.name for t in self.candidates)
        return (
            "'%s' matches multiple tasks:\n  %s\n\n"
            "Use a more specific name to disambiguate."
            % (self.spec, names)
        )


class AmbiguousCellError(TaskResolutionError):
    """A partial cell key that could mean more than one thing."""

    def __init__(self, spec: str, value: str, axes: List[str], detail=None):
        self.spec = spec
        self.value = value
        self.axes = axes
        reason = detail or (
            "'%s' is a value of more than one axis (%s)" % (
                value, ", ".join(axes)))
        super().__init__(
            "'%s' is ambiguous: %s. Name the cell in full, or select the axes "
            "with their flags." % (spec, reason))


@dc.dataclass
class CLITaskResolver:
    """Resolves partial / flexible task names from the CLI against the task graph.

    The resolver builds a *suffix index* over all ``is_root`` tasks so that any
    dotted suffix of a fully-qualified name can be used to refer to a task — as
    long as it is unambiguous.
    """

    _task_m: Dict[str, 'Task'] = dc.field(default_factory=dict)
    _root_pkg_name: str = ""
    _suffix_index: Dict[str, List['Task']] = dc.field(default_factory=dict)
    _all_suffixes: List[str] = dc.field(default_factory=list)
    _log: logging.Logger = dc.field(default=None)

    def __post_init__(self):
        if self._log is None:
            self._log = logging.getLogger(type(self).__name__)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_package(cls, pkg: 'Package') -> 'CLITaskResolver':
        """Build a resolver from a loaded Package (root package).

        This walks ``pkg.task_m`` (and sub-packages) to collect every task,
        then builds the suffix index over root-scoped tasks.
        """
        task_m: Dict[str, 'Task'] = {}
        cls._collect_tasks(pkg, task_m)

        resolver = cls(
            _task_m=task_m,
            _root_pkg_name=pkg.name,
        )
        resolver._build_index()
        return resolver

    @staticmethod
    def _collect_tasks(pkg: 'Package', out: Dict[str, 'Task']):
        for name, task in pkg.task_m.items():
            out[name] = task
        for subpkg in pkg.pkg_m.values():
            CLITaskResolver._collect_tasks(subpkg, out)

    def _build_index(self):
        """Populate ``_suffix_index`` from ``_task_m``."""
        index: Dict[str, list] = {}
        for fq_name, task in self._task_m.items():
            parts = fq_name.split('.')
            for i in range(len(parts)):
                suffix = '.'.join(parts[i:])
                index.setdefault(suffix, []).append(task)
        self._suffix_index = index
        self._all_suffixes = sorted(index.keys())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, spec: str) -> 'Task':
        """Resolve *spec* to a single :class:`Task`, or raise a descriptive error.

        Resolution order:
          1. Exact FQ match (any task, regardless of scope).
          2. Suffix match against all tasks (prefers root-scoped when ambiguous).
          3. Fuzzy fallback → ``TaskNotFoundError`` with suggestions.
        """
        self._log.debug("resolve('%s')", spec)

        # 1. Exact match (all tasks)
        if spec in self._task_m:
            return self._task_m[spec]

        # 2. Suffix match
        candidates = self._suffix_index.get(spec, [])
        if len(candidates) == 1:
            self._log.debug("  suffix match: %s -> %s", spec, candidates[0].name)
            return candidates[0]
        if len(candidates) > 1:
            # If some candidates are root-scoped and others aren't, prefer root
            root_candidates = [c for c in candidates if getattr(c, 'is_root', False)]
            if len(root_candidates) == 1:
                return root_candidates[0]
            if len(root_candidates) > 1:
                # Among root-scoped, prefer tasks from the root package
                root_pkg_candidates = [c for c in root_candidates
                                       if self._is_root_pkg_task(c)]
                if len(root_pkg_candidates) == 1:
                    return root_pkg_candidates[0]
                raise AmbiguousTaskError(spec, root_candidates)
            # No root-scoped candidates — try preferring root package
            root_pkg_candidates = [c for c in candidates
                                   if self._is_root_pkg_task(c)]
            if len(root_pkg_candidates) == 1:
                return root_pkg_candidates[0]
            raise AmbiguousTaskError(spec, candidates)

        # 3. A partial cell key -- `sim-img.prof` for a family whose full cell
        #    names are `sim-img.<view>.<build>`.
        partial = self._resolve_partial_cell(spec)
        if partial is not None:
            return partial

        # 4. Fuzzy fallback
        suggestions = difflib.get_close_matches(
            spec, self._all_suffixes, n=5, cutoff=0.6)
        raise TaskNotFoundError(spec, suggestions)

    def _resolve_partial_cell(self, spec: str):
        """`<family>.<value>...` naming only some of a select family's axes.

        **Command line only.** The unnamed axes fall back to the family's own
        default, which `-D`/`--flag` can move -- so the same partial key can
        denote different cells from one invocation to the next. That is fine for
        something a user types and wrong for something a flow file declares, so
        `needs:` requires the full key (enforced at load, not here).

        Returns the family Task with `select_partial` carrying the bindings, or
        None if `spec` is not a partial key. Ambiguity is an error rather than a
        guess.
        """
        for fq_name, task in self._task_m.items():
            select = getattr(getattr(task, 'strategy', None), 'select', None)
            if select is None:
                continue
            parts = fq_name.split('.')
            suffixes = ['.'.join(parts[i:]) for i in range(len(parts))]
            for suffix in suffixes:
                if not spec.startswith(suffix + "."):
                    continue
                values = spec[len(suffix) + 1:].split('.')
                bindings = {}
                for value in values:
                    axes = [a for a, members in select.axes.items()
                            if value in [str(m) for m in members]]
                    if not axes:
                        return None       # not a partial key at all
                    if len(axes) > 1:
                        raise AmbiguousCellError(spec, value, axes)
                    if axes[0] in bindings:
                        raise AmbiguousCellError(
                            spec, value, [axes[0]],
                            "two values were given for axis '%s'" % axes[0])
                    bindings[axes[0]] = value
                if not bindings:
                    return None
                import copy as _copy
                ret = _copy.copy(task)
                ret.select_partial = bindings
                return ret
        return None

    def completions(self, prefix: str = "") -> List[str]:
        """Return suffix-index entries that start with *prefix*.

        Designed for shell tab-completion integration.  When *prefix* is
        empty, all root-task suffixes are returned.
        """
        if not prefix:
            return self._all_suffixes
        return [s for s in self._all_suffixes if s.startswith(prefix)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------


    def _is_root_pkg_task(self, task: 'Task') -> bool:
        """Return True if *task* belongs to the root package."""
        if not self._root_pkg_name:
            return False
        return task.name.startswith(self._root_pkg_name + ".")

    def _check_non_root_match(self, spec: str) -> Optional[str]:
        """Return a hint string if *spec* matches a non-root task by suffix."""
        for fq_name, task in self._task_m.items():
            if getattr(task, 'is_root', False):
                continue
            parts = fq_name.split('.')
            for i in range(len(parts)):
                suffix = '.'.join(parts[i:])
                if suffix == spec:
                    scope = "export" if getattr(task, 'is_export', False) else "local"
                    return (
                        "A task with this name exists (%s) but is not "
                        "marked 'scope: root'. Only root-scoped tasks can "
                        "be run from the CLI." % fq_name
                    )
        return None
