"""
Pluggable naming scheme for rundir directories, file prefixes, and TUI display.

A naming scheme controls how DV Flow maps logical task identities to
on-disk directory names, artifact filenames, and progress-display labels.
Schemes are selected at the TaskGraphBuilder / TaskSetRunner level and
can be swapped without changing any other code.

To add a new scheme, subclass ``NamingScheme`` and implement all abstract
methods.  Register it via ``NamingSchemeRegistry.register()`` so it can
be selected by name from configuration.
"""

import dataclasses as dc
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Context objects — passed to NamingScheme methods so they have all the
# information they need without coupling to internal TaskNode types.
# ---------------------------------------------------------------------------

@dc.dataclass(frozen=True)
class TaskNamingContext:
    """Immutable snapshot of everything a naming method might need."""

    # The fully-qualified task name (e.g. "ioapic.bench.tests.reg_smoke")
    fq_name: str

    # Leaf name — last segment after the final "."
    leaf_name: str

    # Package name that owns this task (e.g. "ioapic.bench")
    package_name: str

    # The root (top-level) package name for this session
    root_package_name: str

    # Parent compound's leaf name, if this task is inside a compound body.
    # None for top-level tasks.
    parent_leaf: Optional[str] = None

    # Parent compound's fully-qualified name
    parent_fq: Optional[str] = None

    # True when the task uses ``rundir: inherit``
    inherits_rundir: bool = False

    # True when this is the ``.in`` sentinel node of a compound task
    is_sentinel: bool = False

    # Set of leaf names already claimed by sibling tasks in the same
    # compound scope.  Used by schemes that need collision detection.
    sibling_leaves: Tuple[str, ...] = ()


@dc.dataclass(frozen=True)
class MatrixNamingContext(TaskNamingContext):
    """Extended context for tasks produced by a matrix strategy."""

    # Ordered list of (key, value) pairs for this matrix cell.
    # e.g. [("model", "claude-opus-4-6")]
    matrix_bindings: Tuple[Tuple[str, Any], ...] = ()

    # Ordered list of (key, index) pairs.
    # e.g. [("model", 0)]
    matrix_indices: Tuple[Tuple[str, int], ...] = ()


@dc.dataclass(frozen=True)
class IterationNamingContext(TaskNamingContext):
    """Extended context for tasks produced by control-flow loops."""

    # 0-based iteration number
    iteration: int = 0

    # Optional user-supplied label from loop state (``_label`` key)
    iteration_label: Optional[str] = None

    # Control type: "repeat", "while", "do-while"
    control_type: Optional[str] = None


@dc.dataclass(frozen=True)
class BranchNamingContext(TaskNamingContext):
    """Extended context for tasks produced by if/match control flow."""

    # Branch identifier: "then", "else", or match-case label/index
    branch: str = ""

    # Control type: "if", "match"
    control_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class NamingScheme(ABC):
    """
    Abstract base for rundir naming schemes.

    Subclasses control four naming decisions:

    1. **rundir_segment** — the directory name pushed onto the rundir stack
       at graph-build time.
    2. **task_node_name** — the internal name assigned to the TaskNode
       (used in memento keys, cache keys, exec_data ``name`` fields).
    3. **file_prefix** — the prefix prepended to framework-managed files
       (exec_data.json, .log, _cmd.sh) inside the rundir.
    4. **display_name** — the human-readable label shown in TUI progress.
    """

    # -- Graph-build time ---------------------------------------------------

    @abstractmethod
    def rundir_segment(self, ctx: TaskNamingContext) -> Optional[str]:
        """Return the directory-name segment for this task, or None to
        suppress directory creation (e.g. for sentinel nodes).

        For ``rundir: inherit`` tasks this is not called (the task shares
        its parent's directory).
        """
        ...

    @abstractmethod
    def task_node_name(self, ctx: TaskNamingContext) -> str:
        """Return the internal task-node name.

        This is persisted in exec_data.json, used as memento / cache keys,
        and must be unique across the entire task graph.
        """
        ...

    @abstractmethod
    def sentinel_rundir_segment(self, ctx: TaskNamingContext) -> Optional[str]:
        """Return the directory segment for a compound's ``.in`` sentinel,
        or None to suppress its directory entirely."""
        ...

    # -- Matrix strategy ----------------------------------------------------

    @abstractmethod
    def matrix_rundir_segment(self, ctx: MatrixNamingContext) -> str:
        """Return the directory segment for a matrix-expanded task."""
        ...

    @abstractmethod
    def matrix_task_node_name(self, ctx: MatrixNamingContext) -> str:
        """Return the internal name for a matrix-expanded task."""
        ...

    # -- Control-flow iterations --------------------------------------------

    @abstractmethod
    def iteration_rundir_segment(self, ctx: IterationNamingContext) -> str:
        """Return the directory segment for a loop iteration container."""
        ...

    @abstractmethod
    def branch_rundir_segment(self, ctx: BranchNamingContext) -> str:
        """Return the directory segment for an if/match branch container."""
        ...

    # -- Run time -----------------------------------------------------------

    @abstractmethod
    def file_prefix(self, ctx: TaskNamingContext) -> str:
        """Return the filename prefix for framework-managed artifacts.

        For ``rundir: unique`` tasks this is typically empty (the directory
        already identifies the task).  For ``rundir: inherit`` tasks this
        must be non-empty to avoid collisions with siblings.

        Examples:
          - ``""``           → ``exec_data.json``, ``run.log``
          - ``"setup"``      → ``setup.exec_data.json``, ``setup.log``
        """
        ...

    @abstractmethod
    def display_name(self, ctx: TaskNamingContext) -> str:
        """Return the human-readable label for TUI progress display."""
        ...

    # -- Convenience helpers (non-abstract) ---------------------------------

    def exec_data_filename(self, ctx: TaskNamingContext) -> str:
        """Full filename for the exec_data JSON artifact."""
        prefix = self.file_prefix(ctx)
        if prefix:
            return "%s.exec_data.json" % prefix
        return "exec_data.json"

    def log_filename(self, ctx: TaskNamingContext) -> str:
        """Full filename for the shell log artifact."""
        prefix = self.file_prefix(ctx)
        if prefix:
            return "%s.log" % prefix
        return "run.log"

    def script_filename(self, ctx: TaskNamingContext) -> str:
        """Full filename for the shell command script."""
        prefix = self.file_prefix(ctx)
        if prefix:
            return "%s_cmd.sh" % prefix
        return "cmd.sh"

    def prompt_filename(self, ctx: TaskNamingContext) -> str:
        """Full filename for agent prompt text."""
        prefix = self.file_prefix(ctx)
        if prefix:
            return "%s.prompt.txt" % prefix
        return "prompt.txt"

    def result_filename(self, ctx: TaskNamingContext) -> str:
        """Full filename for agent result JSON."""
        prefix = self.file_prefix(ctx)
        if prefix:
            return "%s.result.json" % prefix
        return "result.json"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class NamingSchemeRegistry:
    """Global registry mapping scheme names to factory callables."""

    _schemes: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, scheme_cls: type):
        cls._schemes[name] = scheme_cls

    @classmethod
    def get(cls, name: str) -> 'NamingScheme':
        if name not in cls._schemes:
            raise KeyError(
                "Unknown naming scheme '%s'. Available: %s"
                % (name, ", ".join(sorted(cls._schemes.keys())))
            )
        return cls._schemes[name]()

    @classmethod
    def available(cls) -> List[str]:
        return sorted(cls._schemes.keys())
