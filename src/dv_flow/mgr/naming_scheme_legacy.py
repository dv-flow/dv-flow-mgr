"""
Legacy naming scheme — reproduces the current (pre-redesign) behavior.

- Rundir segments use the fully-qualified task name.
- Sentinel ``.in`` nodes get their own directory.
- Matrix tasks use numeric index suffixes (``_0_1``).
- File prefixes always use the fully-qualified name.
- Display names are the raw ``task.name``.
"""

from typing import Optional
from .naming_scheme import (
    NamingScheme,
    NamingSchemeRegistry,
    TaskNamingContext,
    MatrixNamingContext,
    IterationNamingContext,
    BranchNamingContext,
)


class LegacyNamingScheme(NamingScheme):
    """Reproduces the naming behavior of the current codebase."""

    # -- Graph-build time ---------------------------------------------------

    def rundir_segment(self, ctx: TaskNamingContext) -> Optional[str]:
        return ctx.fq_name

    def task_node_name(self, ctx: TaskNamingContext) -> str:
        return ctx.fq_name

    def sentinel_rundir_segment(self, ctx: TaskNamingContext) -> Optional[str]:
        if ctx.fq_name.endswith(".in"):
            return ctx.fq_name
        return ctx.fq_name + ".in"

    # -- Matrix strategy ----------------------------------------------------

    def matrix_rundir_segment(self, ctx: MatrixNamingContext) -> str:
        suffix = "_".join(str(idx) for _, idx in ctx.matrix_indices)
        return "%s_%s" % (ctx.fq_name, suffix)

    def matrix_task_node_name(self, ctx: MatrixNamingContext) -> str:
        suffix = "_".join(str(idx) for _, idx in ctx.matrix_indices)
        return "%s_%s" % (ctx.fq_name, suffix)

    # -- Control-flow iterations --------------------------------------------

    def iteration_rundir_segment(self, ctx: IterationNamingContext) -> str:
        return "iter_%d" % ctx.iteration

    def branch_rundir_segment(self, ctx: BranchNamingContext) -> str:
        return ctx.branch

    # -- Run time -----------------------------------------------------------

    def file_prefix(self, ctx: TaskNamingContext) -> str:
        return ctx.fq_name

    def display_name(self, ctx: TaskNamingContext) -> str:
        return ctx.fq_name


NamingSchemeRegistry.register("legacy", LegacyNamingScheme)
