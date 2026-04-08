"""
Tests for the pluggable naming scheme infrastructure and both shipped
implementations (LegacyNamingScheme and LeafNamingScheme).

Covers:
  - NamingSchemeRegistry registration and lookup
  - TaskNamingContext / MatrixNamingContext / IterationNamingContext / BranchNamingContext
  - LegacyNamingScheme method contracts
  - LeafNamingScheme method contracts
  - Convenience filename helpers (exec_data, log, script, prompt, result)
  - Integration with TaskNode helpers (_get_exec_data_filename, _get_display_name, etc.)
  - Integration with TaskGraphBuilder (rundir segments, sentinel suppression, matrix naming)
  - Integration with ShellCallable filename selection
"""
import asyncio
import os
import sys
import pytest

from dv_flow.mgr.naming_scheme import (
    NamingScheme,
    NamingSchemeRegistry,
    TaskNamingContext,
    MatrixNamingContext,
    IterationNamingContext,
    BranchNamingContext,
)
from dv_flow.mgr.naming_scheme_legacy import LegacyNamingScheme
from dv_flow.mgr.naming_scheme_leaf import LeafNamingScheme


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TestNamingSchemeRegistry:
    def test_legacy_registered(self):
        scheme = NamingSchemeRegistry.get("legacy")
        assert isinstance(scheme, LegacyNamingScheme)

    def test_leaf_registered(self):
        scheme = NamingSchemeRegistry.get("leaf")
        assert isinstance(scheme, LeafNamingScheme)

    def test_available_includes_both(self):
        avail = NamingSchemeRegistry.available()
        assert "legacy" in avail
        assert "leaf" in avail

    def test_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown naming scheme"):
            NamingSchemeRegistry.get("nonexistent_scheme")


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _leaf_ctx(fq="pkg.task", **overrides):
    """Build a simple TaskNamingContext for testing."""
    leaf = fq.rsplit(".", 1)[-1] if "." in fq else fq
    defaults = dict(
        fq_name=fq,
        leaf_name=leaf,
        package_name="pkg",
        root_package_name="pkg",
    )
    defaults.update(overrides)
    return TaskNamingContext(**defaults)


def _matrix_ctx(fq="pkg.parent.task", bindings=(("key", "val"),), indices=((("key", 0),)), **overrides):
    leaf = fq.rsplit(".", 1)[-1] if "." in fq else fq
    defaults = dict(
        fq_name=fq,
        leaf_name=leaf,
        package_name="pkg",
        root_package_name="pkg",
        parent_leaf="parent",
        parent_fq="pkg.parent",
        matrix_bindings=tuple(bindings),
        matrix_indices=tuple(indices),
    )
    defaults.update(overrides)
    return MatrixNamingContext(**defaults)


def _iter_ctx(fq="pkg.loop", iteration=0, label=None, control_type="repeat"):
    leaf = fq.rsplit(".", 1)[-1] if "." in fq else fq
    return IterationNamingContext(
        fq_name=fq,
        leaf_name=leaf,
        package_name="pkg",
        root_package_name="pkg",
        iteration=iteration,
        iteration_label=label,
        control_type=control_type,
    )


def _branch_ctx(fq="pkg.cond", branch="then", control_type="if"):
    leaf = fq.rsplit(".", 1)[-1] if "." in fq else fq
    return BranchNamingContext(
        fq_name=fq,
        leaf_name=leaf,
        package_name="pkg",
        root_package_name="pkg",
        branch=branch,
        control_type=control_type,
    )


# ---------------------------------------------------------------------------
# LegacyNamingScheme
# ---------------------------------------------------------------------------

class TestLegacyNamingScheme:
    @pytest.fixture
    def scheme(self):
        return LegacyNamingScheme()

    def test_rundir_segment_is_fq(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.rundir_segment(ctx) == "chip.compile"

    def test_task_node_name_is_fq(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.task_node_name(ctx) == "chip.compile"

    def test_sentinel_appends_in(self, scheme):
        ctx = _leaf_ctx("chip.sim_flow")
        assert scheme.sentinel_rundir_segment(ctx) == "chip.sim_flow.in"

    def test_sentinel_already_suffixed(self, scheme):
        ctx = _leaf_ctx("chip.sim_flow.in")
        assert scheme.sentinel_rundir_segment(ctx) == "chip.sim_flow.in"

    def test_matrix_rundir_numeric_indices(self, scheme):
        ctx = _matrix_ctx(
            fq="foo.MatrixTest.Task",
            bindings=(("letter", "a"), ("number", 1)),
            indices=(("letter", 0), ("number", 0)),
        )
        assert scheme.matrix_rundir_segment(ctx) == "foo.MatrixTest.Task_0_0"

    def test_matrix_task_node_name_numeric(self, scheme):
        ctx = _matrix_ctx(
            fq="foo.MatrixTest.Task",
            bindings=(("letter", "b"), ("number", 2)),
            indices=(("letter", 1), ("number", 1)),
        )
        assert scheme.matrix_task_node_name(ctx) == "foo.MatrixTest.Task_1_1"

    def test_iteration_segment(self, scheme):
        ctx = _iter_ctx(iteration=3)
        assert scheme.iteration_rundir_segment(ctx) == "iter_3"

    def test_branch_segment(self, scheme):
        ctx = _branch_ctx(branch="then")
        assert scheme.branch_rundir_segment(ctx) == "then"

    def test_file_prefix_always_fq(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.file_prefix(ctx) == "chip.compile"

    def test_display_name_is_fq(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.display_name(ctx) == "chip.compile"

    def test_exec_data_filename(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.exec_data_filename(ctx) == "chip.compile.exec_data.json"

    def test_log_filename(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.log_filename(ctx) == "chip.compile.log"

    def test_script_filename(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.script_filename(ctx) == "chip.compile_cmd.sh"

    def test_prompt_filename(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.prompt_filename(ctx) == "chip.compile.prompt.txt"

    def test_result_filename(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.result_filename(ctx) == "chip.compile.result.json"


# ---------------------------------------------------------------------------
# LeafNamingScheme
# ---------------------------------------------------------------------------

class TestLeafNamingScheme:
    @pytest.fixture
    def scheme(self):
        return LeafNamingScheme()

    def test_rundir_segment_leaf_only(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.rundir_segment(ctx) == "compile"

    def test_rundir_segment_disambiguates(self, scheme):
        ctx = _leaf_ctx("pkgA.compile", sibling_leaves=("compile",))
        seg = scheme.rundir_segment(ctx)
        assert seg != "compile"
        assert seg.endswith("compile")
        assert "." in seg

    def test_task_node_name_preserves_fq(self, scheme):
        ctx = _leaf_ctx("chip.compile")
        assert scheme.task_node_name(ctx) == "chip.compile"

    def test_sentinel_returns_none(self, scheme):
        ctx = _leaf_ctx("chip.sim_flow")
        assert scheme.sentinel_rundir_segment(ctx) is None

    def test_matrix_rundir_safe_values(self, scheme):
        ctx = _matrix_ctx(
            fq="foo.MatrixTest.Task",
            bindings=(("letter", "a"), ("number", 1)),
            indices=(("letter", 0), ("number", 0)),
        )
        assert scheme.matrix_rundir_segment(ctx) == "Task~a~1"

    def test_matrix_rundir_single_value(self, scheme):
        ctx = _matrix_ctx(
            fq="foo.run_tests.step",
            bindings=(("test", "smoke"),),
            indices=(("test", 0),),
        )
        assert scheme.matrix_rundir_segment(ctx) == "step~smoke"

    def test_matrix_rundir_unsafe_fallback(self, scheme):
        long_val = "x" * 30
        ctx = _matrix_ctx(
            fq="foo.MatrixTest.Task",
            bindings=(("prompt", long_val),),
            indices=(("prompt", 0),),
        )
        seg = scheme.matrix_rundir_segment(ctx)
        assert seg == "Task~prompt0"

    def test_matrix_task_node_name_with_parent(self, scheme):
        ctx = _matrix_ctx(
            fq="foo.MatrixTest.Task",
            bindings=(("letter", "a"), ("number", 1)),
            indices=(("letter", 0), ("number", 0)),
            parent_fq="foo.MatrixTest",
        )
        name = scheme.matrix_task_node_name(ctx)
        assert name == "foo.MatrixTest.Task~a~1"

    def test_matrix_task_node_name_no_parent(self, scheme):
        ctx = _matrix_ctx(
            fq="Task",
            bindings=(("seed", 42),),
            indices=(("seed", 0),),
            parent_fq=None,
            leaf_name="Task",
        )
        name = scheme.matrix_task_node_name(ctx)
        assert name == "Task~42"

    def test_iteration_segment_numeric(self, scheme):
        ctx = _iter_ctx(iteration=2)
        assert scheme.iteration_rundir_segment(ctx) == "iter~2"

    def test_iteration_segment_with_label(self, scheme):
        ctx = _iter_ctx(iteration=0, label="warmup")
        assert scheme.iteration_rundir_segment(ctx) == "iter~warmup"

    def test_iteration_segment_unsafe_label_uses_index(self, scheme):
        ctx = _iter_ctx(iteration=5, label="x" * 30)
        assert scheme.iteration_rundir_segment(ctx) == "iter~5"

    def test_branch_if_then(self, scheme):
        ctx = _branch_ctx(branch="then", control_type="if")
        assert scheme.branch_rundir_segment(ctx) == "then"

    def test_branch_if_else(self, scheme):
        ctx = _branch_ctx(branch="else", control_type="if")
        assert scheme.branch_rundir_segment(ctx) == "else"

    def test_branch_match_case(self, scheme):
        ctx = _branch_ctx(branch="high_perf", control_type="match")
        assert scheme.branch_rundir_segment(ctx) == "case~high_perf"

    def test_branch_match_default(self, scheme):
        ctx = _branch_ctx(branch="default", control_type="match")
        assert scheme.branch_rundir_segment(ctx) == "case~default"

    def test_file_prefix_unique_empty(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=False)
        assert scheme.file_prefix(ctx) == ""

    def test_file_prefix_inherit_returns_leaf(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=True)
        assert scheme.file_prefix(ctx) == "compile"

    def test_exec_data_filename_unique(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=False)
        assert scheme.exec_data_filename(ctx) == "exec_data.json"

    def test_log_filename_unique(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=False)
        assert scheme.log_filename(ctx) == "run.log"

    def test_script_filename_unique(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=False)
        assert scheme.script_filename(ctx) == "cmd.sh"

    def test_prompt_filename_unique(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=False)
        assert scheme.prompt_filename(ctx) == "prompt.txt"

    def test_result_filename_unique(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=False)
        assert scheme.result_filename(ctx) == "result.json"

    def test_exec_data_filename_inherit(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=True)
        assert scheme.exec_data_filename(ctx) == "compile.exec_data.json"

    def test_log_filename_inherit(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=True)
        assert scheme.log_filename(ctx) == "compile.log"

    def test_script_filename_inherit(self, scheme):
        ctx = _leaf_ctx("chip.compile", inherits_rundir=True)
        assert scheme.script_filename(ctx) == "compile_cmd.sh"

    def test_display_strips_root_pkg(self, scheme):
        ctx = _leaf_ctx("pkg.compile")
        assert scheme.display_name(ctx) == "compile"

    def test_display_compound_body(self, scheme):
        ctx = _leaf_ctx("pkg.sim_flow.compile", parent_leaf="sim_flow")
        dn = scheme.display_name(ctx)
        assert "\u203a" in dn
        assert "compile" in dn

    def test_display_matrix(self, scheme):
        ctx = _matrix_ctx(
            fq="pkg.run_tests.compile",
            bindings=(("test", "smoke"), ("seed", 42)),
            indices=(("test", 0), ("seed", 0)),
        )
        dn = scheme.display_name(ctx)
        assert "smoke" in dn
        assert "42" in dn
        assert "[" in dn

    def test_display_iteration(self, scheme):
        ctx = _iter_ctx(fq="pkg.my_loop", iteration=2)
        dn = scheme.display_name(ctx)
        assert "iter 2" in dn

    def test_display_iteration_with_label(self, scheme):
        ctx = _iter_ctx(fq="pkg.my_loop", iteration=0, label="warmup")
        dn = scheme.display_name(ctx)
        assert "warmup" in dn

    def test_display_branch(self, scheme):
        ctx = _branch_ctx(fq="pkg.cond", branch="then")
        dn = scheme.display_name(ctx)
        assert "then" in dn


# ---------------------------------------------------------------------------
# Disambiguation
# ---------------------------------------------------------------------------

class TestLeafDisambiguation:
    @pytest.fixture
    def scheme(self):
        return LeafNamingScheme()

    def test_no_collision(self, scheme):
        ctx = _leaf_ctx("pkgA.compile", sibling_leaves=("elaborate",))
        assert scheme.rundir_segment(ctx) == "compile"

    def test_collision_adds_one_segment(self, scheme):
        ctx = _leaf_ctx("pkgA.compile", sibling_leaves=("compile",))
        seg = scheme.rundir_segment(ctx)
        assert seg == "pkgA.compile"

    def test_deeper_collision(self, scheme):
        ctx = _leaf_ctx(
            "root.pkgA.compile",
            sibling_leaves=("compile", "pkgA.compile"),
        )
        seg = scheme.rundir_segment(ctx)
        assert seg == "root.pkgA.compile"


# ---------------------------------------------------------------------------
# Matrix safe-value regex boundaries
# ---------------------------------------------------------------------------

class TestMatrixSafeValues:
    @pytest.fixture
    def scheme(self):
        return LeafNamingScheme()

    def test_alphanumeric_short(self, scheme):
        ctx = _matrix_ctx(
            bindings=(("k", "abc123"),),
            indices=(("k", 0),),
        )
        assert "abc123" in scheme.matrix_rundir_segment(ctx)

    def test_underscore_and_dash(self, scheme):
        ctx = _matrix_ctx(
            bindings=(("k", "foo-bar_baz"),),
            indices=(("k", 0),),
        )
        assert "foo-bar_baz" in scheme.matrix_rundir_segment(ctx)

    def test_dot_in_value(self, scheme):
        ctx = _matrix_ctx(
            bindings=(("k", "v1.2"),),
            indices=(("k", 0),),
        )
        assert "v1.2" in scheme.matrix_rundir_segment(ctx)

    def test_space_falls_back(self, scheme):
        ctx = _matrix_ctx(
            bindings=(("k", "has space"),),
            indices=(("k", 0),),
        )
        seg = scheme.matrix_rundir_segment(ctx)
        assert "k0" in seg

    def test_empty_string_falls_back(self, scheme):
        ctx = _matrix_ctx(
            bindings=(("k", ""),),
            indices=(("k", 0),),
        )
        seg = scheme.matrix_rundir_segment(ctx)
        assert "k0" in seg

    def test_exactly_24_chars(self, scheme):
        val = "a" * 24
        ctx = _matrix_ctx(
            bindings=(("k", val),),
            indices=(("k", 0),),
        )
        seg = scheme.matrix_rundir_segment(ctx)
        assert val in seg

    def test_25_chars_falls_back(self, scheme):
        val = "a" * 25
        ctx = _matrix_ctx(
            bindings=(("k", val),),
            indices=(("k", 0),),
        )
        seg = scheme.matrix_rundir_segment(ctx)
        assert "k0" in seg


# ---------------------------------------------------------------------------
# TaskNode integration
# ---------------------------------------------------------------------------

class TestTaskNodeNamingIntegration:

    def _make_node(self, name, scheme_name, inherits_rundir=False):
        from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
        from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
        from pydantic import BaseModel

        class DummyParams(BaseModel):
            pass

        scheme = NamingSchemeRegistry.get(scheme_name)
        ctxt = TaskNodeCtxt(
            root_pkgdir="/tmp",
            root_rundir="/tmp/rundir",
            env={},
            naming_scheme=scheme,
            root_package_name="pkg",
        )
        node = TaskNodeLeaf(
            name=name,
            srcdir="/tmp",
            params=DummyParams(),
            ctxt=ctxt,
            inherits_rundir=inherits_rundir,
        )
        return node

    def test_legacy_exec_data_filename(self):
        node = self._make_node("pkg.compile", "legacy")
        assert node._get_exec_data_filename() == "pkg.compile.exec_data.json"

    def test_leaf_exec_data_filename_unique(self):
        node = self._make_node("pkg.compile", "leaf")
        assert node._get_exec_data_filename() == "exec_data.json"

    def test_leaf_exec_data_filename_inherit(self):
        node = self._make_node("pkg.compile", "leaf", inherits_rundir=True)
        assert node._get_exec_data_filename() == "compile.exec_data.json"

    def test_legacy_display_name(self):
        node = self._make_node("pkg.compile", "legacy")
        assert node._get_display_name() == "pkg.compile"

    def test_leaf_display_name(self):
        node = self._make_node("pkg.compile", "leaf")
        assert node._get_display_name() == "compile"

    def test_legacy_log_filename(self):
        node = self._make_node("pkg.compile", "legacy")
        assert node._get_log_filename() == "pkg.compile.log"

    def test_leaf_log_filename_unique(self):
        node = self._make_node("pkg.compile", "leaf")
        assert node._get_log_filename() == "run.log"

    def test_leaf_log_filename_inherit(self):
        node = self._make_node("pkg.compile", "leaf", inherits_rundir=True)
        assert node._get_log_filename() == "compile.log"

    def test_legacy_script_filename(self):
        node = self._make_node("pkg.compile", "legacy")
        assert node._get_script_filename() == "pkg.compile_cmd.sh"

    def test_leaf_script_filename_unique(self):
        node = self._make_node("pkg.compile", "leaf")
        assert node._get_script_filename() == "cmd.sh"


# ---------------------------------------------------------------------------
# TaskGraphBuilder integration
# ---------------------------------------------------------------------------

class TestBuilderLeafSchemeRundir:

    @pytest.fixture(autouse=True)
    def reset_extrgy(self):
        from dv_flow.mgr.ext_rgy import ExtRgy
        original_modules = set(sys.modules.keys())
        original_path = sys.path.copy()
        if 'MAKEFLAGS' in os.environ:
            del os.environ['MAKEFLAGS']
        ExtRgy._inst = None
        yield
        ExtRgy._inst = None
        added_modules = set(sys.modules.keys()) - original_modules
        for mod_name in added_modules:
            del sys.modules[mod_name]
        sys.path[:] = original_path
        if 'MAKEFLAGS' in os.environ:
            del os.environ['MAKEFLAGS']

    def test_leaf_task_rundir_uses_leaf_name(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef

        flow_dv = """\
package:
    name: mypkg
    tasks:
    - name: compile
      uses: std.Message
      with:
        msg: "hello"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="leaf",
        )
        task = builder.mkTaskNode("mypkg.compile")
        rundir_path = "/".join(str(s) for s in task.rundir)
        assert rundir_path.endswith("/compile")
        assert "mypkg.compile" not in rundir_path

    def test_legacy_task_rundir_uses_fq_name(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef

        flow_dv = """\
package:
    name: mypkg
    tasks:
    - name: compile
      uses: std.Message
      with:
        msg: "hello"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="legacy",
        )
        task = builder.mkTaskNode("mypkg.compile")
        rundir_path = "/".join(str(s) for s in task.rundir)
        assert "mypkg.compile" in rundir_path

    def test_compound_sentinel_suppressed_leaf_scheme(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef

        flow_dv = """\
package:
    name: mypkg
    tasks:
    - name: sim_flow
      body:
      - name: compile
        uses: std.Message
        with:
          msg: "compiling"
      - name: run_sim
        uses: std.Message
        with:
          msg: "running"
        needs: [compile]
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="leaf",
        )
        task = builder.mkTaskNode("mypkg.sim_flow")
        assert task.input.save_exec_data is False

    def test_compound_sentinel_has_dir_legacy_scheme(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef

        flow_dv = """\
package:
    name: mypkg
    tasks:
    - name: sim_flow
      body:
      - name: compile
        uses: std.Message
        with:
          msg: "compiling"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="legacy",
        )
        task = builder.mkTaskNode("mypkg.sim_flow")
        sentinel_rundir = "/".join(str(s) for s in task.input.rundir)
        assert ".in" in sentinel_rundir

    def test_matrix_leaf_scheme_value_names(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef

        flow_dv = """\
package:
    name: foo
    tasks:
    - name: MatrixTest
      strategy:
        matrix:
          letter: ["a", "b"]
          number: [1, 2]
      body:
      - name: Task
        uses: std.Message
        with:
          msg: "${{ this.letter }}_${{ this.number }}"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="leaf",
        )
        task = builder.mkTaskNode("foo.MatrixTest")
        body_names = [t.name for t in task.tasks if t is not task.input]
        assert any("~a~1" in n for n in body_names)
        assert any("~a~2" in n for n in body_names)
        assert any("~b~1" in n for n in body_names)
        assert any("~b~2" in n for n in body_names)

    def test_matrix_leaf_scheme_runs(self, tmpdir, capsys):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef
        from dv_flow.mgr.task_runner import TaskSetRunner

        flow_dv = """\
package:
    name: foo
    tasks:
    - name: MatrixTest
      strategy:
        matrix:
          letter: ["a", "b"]
          number: [1, 2]
      body:
      - name: Task
        uses: std.Message
        with:
          msg: "${{ this.letter }}_${{ this.number }}"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="leaf",
        )
        runner = TaskSetRunner(rundir=rundir)
        task = builder.mkTaskNode("foo.MatrixTest")
        asyncio.run(runner.run(task))

        captured = capsys.readouterr()
        assert "a_1" in captured.out
        assert "a_2" in captured.out
        assert "b_1" in captured.out
        assert "b_2" in captured.out

    def test_leaf_scheme_exec_data_written(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef
        from dv_flow.mgr.task_runner import TaskSetRunner

        flow_dv = """\
package:
    name: mypkg
    tasks:
    - name: hello
      uses: std.Message
      with:
        msg: "hi"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="leaf",
        )
        runner = TaskSetRunner(rundir=rundir)
        task = builder.mkTaskNode("mypkg.hello")
        asyncio.run(runner.run(task))

        task_rundir = task.rundir if isinstance(task.rundir, str) else os.path.join(*task.rundir)
        assert os.path.isfile(os.path.join(task_rundir, "exec_data.json"))
        assert not os.path.isfile(os.path.join(task_rundir, "mypkg.hello.exec_data.json"))

    def test_legacy_scheme_exec_data_written(self, tmpdir):
        from dv_flow.mgr import TaskGraphBuilder
        from dv_flow.mgr.util import loadProjPkgDef
        from dv_flow.mgr.task_runner import TaskSetRunner

        flow_dv = """\
package:
    name: mypkg
    tasks:
    - name: hello
      uses: std.Message
      with:
        msg: "hi"
"""
        with open(os.path.join(str(tmpdir), "flow.dv"), "w") as f:
            f.write(flow_dv)

        rundir = os.path.join(str(tmpdir), "rundir")
        loader, pkg_def = loadProjPkgDef(str(tmpdir))
        builder = TaskGraphBuilder(
            root_pkg=pkg_def,
            rundir=rundir,
            naming_scheme="legacy",
        )
        runner = TaskSetRunner(rundir=rundir)
        task = builder.mkTaskNode("mypkg.hello")
        asyncio.run(runner.run(task))

        task_rundir = task.rundir if isinstance(task.rundir, str) else os.path.join(*task.rundir)
        assert os.path.isfile(os.path.join(task_rundir, "mypkg.hello.exec_data.json"))


# ---------------------------------------------------------------------------
# ShellCallable integration
# ---------------------------------------------------------------------------

class TestShellCallableNaming:

    def _make_ctxt_and_input(self, scheme_name, task_name, inherits=False):
        from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt

        scheme = NamingSchemeRegistry.get(scheme_name)
        ctxt_obj = TaskNodeCtxt(
            root_pkgdir="/tmp",
            root_rundir="/tmp/rundir",
            env={},
            naming_scheme=scheme,
            root_package_name="pkg",
        )

        class FakeCtxt:
            ctxt = ctxt_obj

        class FakeInput:
            name = task_name
            inherits_rundir = inherits

        return FakeCtxt(), FakeInput()

    def test_legacy_filenames(self):
        from dv_flow.mgr.shell_callable import ShellCallable

        sc = ShellCallable(body="echo hi", srcdir="/tmp", shell="bash")
        ctxt, inp = self._make_ctxt_and_input("legacy", "pkg.compile")
        log, script = sc._get_filenames(ctxt, inp)
        assert log == "pkg.compile.log"
        assert script == "pkg.compile_cmd.sh"

    def test_leaf_filenames_unique(self):
        from dv_flow.mgr.shell_callable import ShellCallable

        sc = ShellCallable(body="echo hi", srcdir="/tmp", shell="bash")
        ctxt, inp = self._make_ctxt_and_input("leaf", "pkg.compile")
        log, script = sc._get_filenames(ctxt, inp)
        assert log == "run.log"
        assert script == "cmd.sh"

    def test_leaf_filenames_inherit(self):
        from dv_flow.mgr.shell_callable import ShellCallable

        sc = ShellCallable(body="echo hi", srcdir="/tmp", shell="bash")
        ctxt, inp = self._make_ctxt_and_input("leaf", "pkg.compile", inherits=True)
        log, script = sc._get_filenames(ctxt, inp)
        assert log == "compile.log"
        assert script == "compile_cmd.sh"


# ---------------------------------------------------------------------------
# Control-flow node integration
# ---------------------------------------------------------------------------

class TestControlFlowNaming:

    def _make_control_node(self, scheme_name, name="pkg.loop"):
        from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
        from dv_flow.mgr.task_node_control import TaskNodeControl
        from dv_flow.mgr.task_def import ControlDef
        from pydantic import BaseModel

        class DummyParams(BaseModel):
            pass

        scheme = NamingSchemeRegistry.get(scheme_name)
        ctxt = TaskNodeCtxt(
            root_pkgdir="/tmp",
            root_rundir="/tmp/rundir",
            env={},
            naming_scheme=scheme,
            root_package_name="pkg",
        )
        control_def = ControlDef(type="repeat", count=3)
        node = TaskNodeControl(
            name=name,
            srcdir="/tmp",
            params=DummyParams(),
            ctxt=ctxt,
            control_def=control_def,
        )
        return node

    def test_legacy_iteration_segment(self):
        node = self._make_control_node("legacy")
        seg = node._get_iteration_segment(5)
        assert seg == "iter_5"

    def test_leaf_iteration_segment(self):
        node = self._make_control_node("leaf")
        seg = node._get_iteration_segment(5)
        assert seg == "iter~5"

    def test_leaf_iteration_segment_with_label(self):
        node = self._make_control_node("leaf")
        seg = node._get_iteration_segment(0, {"_label": "warmup"})
        assert seg == "iter~warmup"

    def test_legacy_branch_segment(self):
        node = self._make_control_node("legacy")
        seg = node._get_branch_segment("then", "if")
        assert seg == "then"

    def test_leaf_branch_segment_if(self):
        node = self._make_control_node("leaf")
        seg = node._get_branch_segment("then", "if")
        assert seg == "then"

    def test_leaf_branch_segment_match(self):
        node = self._make_control_node("leaf")
        seg = node._get_branch_segment("high_perf", "match")
        assert seg == "case~high_perf"
