"""
Tests for CLI task resolution with suffix-based flexible matching.

Covers:
- Exact FQ match
- Suffix matching at every level (leaf, fragment.leaf, pkg.fragment.leaf)
- Ambiguity detection and error reporting
- Fuzzy suggestions on typos
- Non-root task filtering with scope hints
- Tab-completion API
- Integration with TaskGraphBuilder.mkTaskNode
"""
import os
import pytest
from dv_flow.mgr import PackageLoader
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
from dv_flow.mgr.cli_task_resolver import (
    CLITaskResolver,
    TaskResolutionError,
    TaskNotFoundError,
    AmbiguousTaskError,
)
from .marker_collector import MarkerCollector


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _load_pkg(tmpdir, flow_dv, extra_files=None):
    """Write flow files and return (loader, pkg)."""
    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    if extra_files:
        for name, content in extra_files.items():
            path = os.path.join(str(tmpdir), name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fp:
                fp.write(content)
    mc = MarkerCollector()
    loader = PackageLoader(marker_listeners=[mc])
    pkg = loader.load(os.path.join(str(tmpdir), "flow.dv"))
    assert len(mc.markers) == 0, "unexpected markers: %s" % [m.msg for m in mc.markers]
    return loader, pkg


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

SINGLE_FRAGMENT_FLOW = """
package:
    name: myapp
    tasks:
    - root: main-task
      run: echo main
    fragments:
    - tools.dv
"""

SINGLE_FRAGMENT_TOOLS = """
fragment:
    name: build
    tasks:
    - root: compile
      run: echo compile
    - root: link
      needs: [compile]
      run: echo link
    - export: helper
      run: echo helper
"""


MULTI_FRAGMENT_FLOW = """
package:
    name: multiapp
    fragments:
    - frontend.dv
    - backend.dv
"""

MULTI_FRONTEND = """
fragment:
    name: frontend
    tasks:
    - root: build
      run: echo fe-build
    - root: test
      run: echo fe-test
"""

MULTI_BACKEND = """
fragment:
    name: backend
    tasks:
    - root: build
      run: echo be-build
    - root: test
      run: echo be-test
"""

DEEP_FRAGMENT_FLOW = """
package:
    name: chip
    fragments:
    - src.dv
"""

DEEP_FRAGMENT_SRC = """
fragment:
    name: verif.tb
    tasks:
    - root: smoke-test
      run: echo smoke
    - root: reg_smoke-test
      run: echo reg_smoke
"""


# ------------------------------------------------------------------ #
# Exact FQ match
# ------------------------------------------------------------------ #

def test_exact_fq_match(tmpdir):
    """Exact fully-qualified name resolves immediately."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("myapp.build.compile")
    assert task.name == "myapp.build.compile"


def test_exact_root_task(tmpdir):
    """Exact FQ name for a root-level task."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("myapp.main-task")
    assert task.name == "myapp.main-task"


# ------------------------------------------------------------------ #
# Suffix matching — unique leaf
# ------------------------------------------------------------------ #

def test_suffix_leaf_only(tmpdir):
    """Bare leaf name resolves when unique among root tasks."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("compile")
    assert task.name == "myapp.build.compile"


def test_suffix_fragment_dot_leaf(tmpdir):
    """fragment.leaf suffix resolves."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("build.compile")
    assert task.name == "myapp.build.compile"


def test_suffix_deep_fragment(tmpdir):
    """Multi-level fragment path (verif.tb.smoke-test)."""
    loader, pkg = _load_pkg(tmpdir, DEEP_FRAGMENT_FLOW,
                            {"src.dv": DEEP_FRAGMENT_SRC})
    resolver = CLITaskResolver.from_package(pkg)

    assert resolver.resolve("smoke-test").name == "chip.verif.tb.smoke-test"
    assert resolver.resolve("tb.smoke-test").name == "chip.verif.tb.smoke-test"
    assert resolver.resolve("verif.tb.smoke-test").name == "chip.verif.tb.smoke-test"
    assert resolver.resolve("chip.verif.tb.smoke-test").name == "chip.verif.tb.smoke-test"


def test_suffix_with_underscore_hyphen(tmpdir):
    """Task names with mixed hyphens and underscores resolve by suffix."""
    loader, pkg = _load_pkg(tmpdir, DEEP_FRAGMENT_FLOW,
                            {"src.dv": DEEP_FRAGMENT_SRC})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("reg_smoke-test")
    assert task.name == "chip.verif.tb.reg_smoke-test"


# ------------------------------------------------------------------ #
# Ambiguity detection
# ------------------------------------------------------------------ #

def test_ambiguous_leaf_raises(tmpdir):
    """Leaf name shared by multiple root tasks raises AmbiguousTaskError."""
    loader, pkg = _load_pkg(tmpdir, MULTI_FRAGMENT_FLOW,
                            {"frontend.dv": MULTI_FRONTEND,
                             "backend.dv": MULTI_BACKEND})
    resolver = CLITaskResolver.from_package(pkg)

    with pytest.raises(AmbiguousTaskError) as exc_info:
        resolver.resolve("build")

    err = exc_info.value
    assert err.spec == "build"
    assert len(err.candidates) == 2
    fq_names = {c.name for c in err.candidates}
    assert "multiapp.frontend.build" in fq_names
    assert "multiapp.backend.build" in fq_names
    assert "disambiguate" in str(err).lower()


def test_ambiguous_resolved_by_fragment(tmpdir):
    """Disambiguating with fragment prefix succeeds."""
    loader, pkg = _load_pkg(tmpdir, MULTI_FRAGMENT_FLOW,
                            {"frontend.dv": MULTI_FRONTEND,
                             "backend.dv": MULTI_BACKEND})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("frontend.build")
    assert task.name == "multiapp.frontend.build"

    task2 = resolver.resolve("backend.test")
    assert task2.name == "multiapp.backend.test"


# ------------------------------------------------------------------ #
# Task-not-found with fuzzy suggestions
# ------------------------------------------------------------------ #

def test_not_found_raises(tmpdir):
    """Completely unknown name raises TaskNotFoundError."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    with pytest.raises(TaskNotFoundError) as exc_info:
        resolver.resolve("nonexistent")
    assert exc_info.value.spec == "nonexistent"


def test_not_found_fuzzy_suggestion(tmpdir):
    """Typo produces a fuzzy suggestion."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    with pytest.raises(TaskNotFoundError) as exc_info:
        resolver.resolve("compil")
    assert len(exc_info.value.suggestions) > 0
    assert any("compile" in s for s in exc_info.value.suggestions)


# ------------------------------------------------------------------ #
# Non-root task filtering & scope hint
# ------------------------------------------------------------------ #

def test_non_root_resolvable_by_suffix(tmpdir):
    """Non-root tasks are resolvable by suffix (backward-compatible)."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("helper")
    assert task.name == "myapp.build.helper"


def test_exact_fq_bypasses_root_filter(tmpdir):
    """Exact FQ match works even for non-root tasks (escape hatch)."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("myapp.build.helper")
    assert task.name == "myapp.build.helper"


# ------------------------------------------------------------------ #
# Tab-completion API
# ------------------------------------------------------------------ #

def test_completions_all(tmpdir):
    """completions('') returns all task suffixes."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    all_c = resolver.completions()
    # Should contain at least leaf names for root tasks
    assert "compile" in all_c
    assert "link" in all_c
    assert "main-task" in all_c
    # Non-root 'helper' is also included
    assert "helper" in all_c


def test_completions_prefix(tmpdir):
    """completions(prefix) filters correctly."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    matches = resolver.completions("comp")
    assert "compile" in matches
    assert "link" not in matches


def test_completions_fragment_prefix(tmpdir):
    """completions('build.') returns fragment-qualified suffixes."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    matches = resolver.completions("build.")
    assert "build.compile" in matches
    assert "build.link" in matches


# ------------------------------------------------------------------ #
# Integration with TaskGraphBuilder
# ------------------------------------------------------------------ #

def test_resolver_then_builder(tmpdir):
    """Resolver produces FQ names that mkTaskNode accepts without allow_root_prefix."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmpdir), loader=loader)

    resolved = resolver.resolve("link")
    node = builder.mkTaskNode(resolved.name)
    assert node is not None
    assert node.name == "myapp.build.link"


def test_multi_fragment_resolver_then_builder(tmpdir):
    """Disambiguated suffix resolves and builds correctly."""
    loader, pkg = _load_pkg(tmpdir, MULTI_FRAGMENT_FLOW,
                            {"frontend.dv": MULTI_FRONTEND,
                             "backend.dv": MULTI_BACKEND})
    resolver = CLITaskResolver.from_package(pkg)
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmpdir), loader=loader)

    resolved = resolver.resolve("frontend.build")
    node = builder.mkTaskNode(resolved.name)
    assert node is not None
    assert node.name == "multiapp.frontend.build"


# ------------------------------------------------------------------ #
# Error message formatting
# ------------------------------------------------------------------ #

def test_ambiguous_error_message_lists_candidates(tmpdir):
    """AmbiguousTaskError message lists all matching FQ names."""
    loader, pkg = _load_pkg(tmpdir, MULTI_FRAGMENT_FLOW,
                            {"frontend.dv": MULTI_FRONTEND,
                             "backend.dv": MULTI_BACKEND})
    resolver = CLITaskResolver.from_package(pkg)

    with pytest.raises(AmbiguousTaskError) as exc_info:
        resolver.resolve("test")

    msg = str(exc_info.value)
    assert "multiapp.frontend.test" in msg
    assert "multiapp.backend.test" in msg


def test_not_found_message_includes_dfm_run_hint(tmpdir):
    """TaskNotFoundError message suggests 'dfm run' when no fuzzy match."""
    loader, pkg = _load_pkg(tmpdir, SINGLE_FRAGMENT_FLOW,
                            {"tools.dv": SINGLE_FRAGMENT_TOOLS})
    resolver = CLITaskResolver.from_package(pkg)

    with pytest.raises(TaskNotFoundError) as exc_info:
        resolver.resolve("zzzzz_no_match")
    msg = str(exc_info.value)
    assert "dfm run" in msg


# ------------------------------------------------------------------ #
# Edge: empty package
# ------------------------------------------------------------------ #

def test_empty_package_not_found(tmpdir):
    """Resolver on a package with no tasks raises TaskNotFoundError."""
    flow = """
package:
    name: empty
"""
    loader, pkg = _load_pkg(tmpdir, flow)
    resolver = CLITaskResolver.from_package(pkg)

    with pytest.raises(TaskNotFoundError):
        resolver.resolve("anything")


# ------------------------------------------------------------------ #
# Root-preference when ambiguous
# ------------------------------------------------------------------ #

ROOT_PREFERRED_FLOW = """
package:
    name: proj
    fragments:
    - a.dv
    - b.dv
"""

ROOT_PREFERRED_A = """
fragment:
    name: alpha
    tasks:
    - root: action
      run: echo alpha-action
"""

ROOT_PREFERRED_B = """
fragment:
    name: beta
    tasks:
    - export: action
      run: echo beta-action
"""


def test_root_preferred_over_non_root(tmpdir):
    """When a suffix matches one root and one non-root task, prefer root."""
    loader, pkg = _load_pkg(tmpdir, ROOT_PREFERRED_FLOW,
                            {"a.dv": ROOT_PREFERRED_A,
                             "b.dv": ROOT_PREFERRED_B})
    resolver = CLITaskResolver.from_package(pkg)

    task = resolver.resolve("action")
    assert task.name == "proj.alpha.action"
    assert task.is_root
