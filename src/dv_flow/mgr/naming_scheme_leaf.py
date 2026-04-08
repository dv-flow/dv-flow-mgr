"""
Leaf naming scheme — the proposed ergonomic redesign.

- Rundir segments use the task's leaf name (last segment after final ".").
- Sentinel ``.in`` nodes are suppressed (no on-disk directory).
- Matrix tasks embed short variable values in directory names (``~``-joined).
- ``rundir: unique`` tasks get unqualified filenames (``exec_data.json``).
- ``rundir: inherit`` tasks get leaf-qualified filenames (``setup.exec_data.json``).
- TUI display strips the root package prefix and uses ``›`` hierarchy separators.
"""

import re
from typing import Any, Optional, Tuple
from .naming_scheme import (
    NamingScheme,
    NamingSchemeRegistry,
    TaskNamingContext,
    MatrixNamingContext,
    IterationNamingContext,
    BranchNamingContext,
)

# A matrix value is used directly in the directory name when it matches
# this pattern.  Otherwise we fall back to ``{key}{index}``.
_SAFE_VALUE_RE = re.compile(r'^[A-Za-z0-9_.\-]{1,24}$')


class LeafNamingScheme(NamingScheme):
    """Ergonomic naming scheme using leaf names and matrix values."""

    # -- Graph-build time ---------------------------------------------------

    def rundir_segment(self, ctx: TaskNamingContext) -> Optional[str]:
        seg = ctx.leaf_name

        # Disambiguate if a sibling already uses the same leaf name
        if ctx.sibling_leaves and seg in ctx.sibling_leaves:
            seg = self._disambiguate(ctx)

        return seg

    def task_node_name(self, ctx: TaskNamingContext) -> str:
        return ctx.fq_name

    def sentinel_rundir_segment(self, ctx: TaskNamingContext) -> Optional[str]:
        return None

    # -- Matrix strategy ----------------------------------------------------

    def matrix_rundir_segment(self, ctx: MatrixNamingContext) -> str:
        value_part = self._matrix_value_suffix(ctx.matrix_bindings,
                                                ctx.matrix_indices)
        return "%s~%s" % (ctx.leaf_name, value_part)

    def matrix_task_node_name(self, ctx: MatrixNamingContext) -> str:
        value_part = self._matrix_value_suffix(ctx.matrix_bindings,
                                                ctx.matrix_indices)
        if ctx.parent_fq:
            return "%s.%s~%s" % (ctx.parent_fq, ctx.leaf_name, value_part)
        return "%s~%s" % (ctx.leaf_name, value_part)

    # -- Control-flow iterations --------------------------------------------

    def iteration_rundir_segment(self, ctx: IterationNamingContext) -> str:
        if ctx.iteration_label and _SAFE_VALUE_RE.match(str(ctx.iteration_label)):
            return "iter~%s" % ctx.iteration_label
        return "iter~%d" % ctx.iteration

    def branch_rundir_segment(self, ctx: BranchNamingContext) -> str:
        if ctx.control_type == "if":
            return ctx.branch  # "then" or "else"
        # match: use case label
        if ctx.branch and _SAFE_VALUE_RE.match(ctx.branch):
            return "case~%s" % ctx.branch
        return ctx.branch or "case"

    # -- Run time -----------------------------------------------------------

    def file_prefix(self, ctx: TaskNamingContext) -> str:
        if ctx.inherits_rundir:
            return ctx.leaf_name
        return ""

    def display_name(self, ctx: TaskNamingContext) -> str:
        # Strip root package prefix to reduce noise
        name = ctx.fq_name
        root = ctx.root_package_name
        if root and name.startswith(root + "."):
            name = name[len(root) + 1:]

        if isinstance(ctx, MatrixNamingContext) and ctx.matrix_bindings:
            vals = ", ".join(str(v) for _, v in ctx.matrix_bindings)
            # Extract the task leaf from the name for cleaner display
            parts = name.rsplit(".", 1)
            if len(parts) == 2:
                return "%s › %s [%s]" % (parts[0], parts[1], vals)
            return "%s [%s]" % (name, vals)

        if isinstance(ctx, IterationNamingContext):
            label = ctx.iteration_label or str(ctx.iteration)
            parts = name.rsplit(".", 1)
            if len(parts) == 2:
                return "%s › %s [iter %s]" % (parts[0], parts[1], label)
            return "%s [iter %s]" % (name, label)

        if isinstance(ctx, BranchNamingContext):
            parts = name.rsplit(".", 1)
            if len(parts) == 2:
                return "%s › %s [%s]" % (parts[0], parts[1], ctx.branch)
            return "%s [%s]" % (name, ctx.branch)

        # Default: use hierarchy separator for compound body tasks
        if ctx.parent_leaf:
            parts = name.rsplit(".", 1)
            if len(parts) == 2:
                return "%s › %s" % (parts[0], parts[1])

        return name

    # -- Private helpers ----------------------------------------------------

    @staticmethod
    def _matrix_value_suffix(
        bindings: Tuple[Tuple[str, Any], ...],
        indices: Tuple[Tuple[str, int], ...],
    ) -> str:
        """Build the ``~``-joined value suffix for a matrix cell.

        Uses the actual value when it's short and filesystem-safe;
        otherwise falls back to ``{key}{index}``.
        """
        parts = []
        idx_map = dict(indices)
        for key, value in bindings:
            s = str(value)
            if _SAFE_VALUE_RE.match(s):
                parts.append(s)
            else:
                parts.append("%s%d" % (key, idx_map.get(key, 0)))
        return "~".join(parts)

    @staticmethod
    def _disambiguate(ctx: TaskNamingContext) -> str:
        """Build a minimally-qualified segment to avoid collision.

        Works backwards through the dotted name, adding one segment at a
        time until the result is unique among ``ctx.sibling_leaves``.
        """
        parts = ctx.fq_name.split(".")
        for depth in range(2, len(parts) + 1):
            candidate = ".".join(parts[-depth:])
            if candidate not in ctx.sibling_leaves:
                return candidate
        # Ultimate fallback — full name (should never happen)
        return ctx.fq_name


NamingSchemeRegistry.register("leaf", LeafNamingScheme)
