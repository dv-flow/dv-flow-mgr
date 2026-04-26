"""Tests for append/prepend on list-typed task parameters and config extensions."""
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.param_def import ParamDef
from dv_flow.mgr.util import loadProjPkgDef
from .marker_collector import MarkerCollector


# ------------------------------------------------------------------ #
# 9a. ParamDef.resolve_value unit tests                               #
# ------------------------------------------------------------------ #

def test_resolve_append_only():
    pd = ParamDef(append=["C"])
    assert pd.resolve_value(["A", "B"]) == ["A", "B", "C"]

def test_resolve_prepend_only():
    pd = ParamDef(prepend=["C"])
    assert pd.resolve_value(["A", "B"]) == ["C", "A", "B"]

def test_resolve_both():
    pd = ParamDef(prepend=["X"], append=["Y"])
    assert pd.resolve_value(["A"]) == ["X", "A", "Y"]

def test_resolve_value_plus_append():
    """When both value and append are set, value is the base, append extends it."""
    pd = ParamDef(value=["-O2"], append=["-kdb"])
    assert pd.resolve_value(["ignored"]) == ["-O2", "-kdb"]

def test_resolve_value_plus_prepend():
    pd = ParamDef(value=["-O2"], prepend=["-g"])
    assert pd.resolve_value(["ignored"]) == ["-g", "-O2"]

def test_resolve_value_only():
    """Plain value with no list ops returns value as-is."""
    pd = ParamDef(value="hello")
    assert pd.resolve_value("old") == "hello"

def test_resolve_empty_base():
    pd = ParamDef(append=["A"])
    assert pd.resolve_value(None) == ["A"]
    assert pd.resolve_value([]) == ["A"]

def test_resolve_scalar_wrap():
    """Single-item append wraps to list."""
    pd = ParamDef(append="single")
    assert pd.resolve_value(["A"]) == ["A", "single"]

def test_has_list_op():
    assert ParamDef(append=["x"]).has_list_op()
    assert ParamDef(prepend=["x"]).has_list_op()
    assert not ParamDef(value="x").has_list_op()
    assert not ParamDef().has_list_op()


# ------------------------------------------------------------------ #
# 9b. Inline append on derived task                                   #
# ------------------------------------------------------------------ #

def test_inline_append(tmp_path):
    """Derived task appends to base task's list param."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: base
      with:
        args:
          type: list
          value: ["-O2"]
    - name: derived
      uses: pkg.base
      with:
        args: { append: ["-Wall", "-kdb"] }
    - name: entry
      uses: std.Null
      needs: [derived]
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    derived = builder.findTask("pkg.derived")
    assert list(derived.params.args) == ["-O2", "-Wall", "-kdb"]


# ------------------------------------------------------------------ #
# 9c. Inline prepend on derived task                                  #
# ------------------------------------------------------------------ #

def test_inline_prepend(tmp_path):
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: base
      with:
        args:
          type: list
          value: ["-O2"]
    - name: derived
      uses: pkg.base
      with:
        args: { prepend: ["-g"] }
    - name: entry
      uses: std.Null
      needs: [derived]
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    derived = builder.findTask("pkg.derived")
    assert list(derived.params.args) == ["-g", "-O2"]


# ------------------------------------------------------------------ #
# 9d. Config extension with append                                    #
# ------------------------------------------------------------------ #

def test_config_extension_append(tmp_path):
    """Config extension appends to a task's list param."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: build
      with:
        args:
          type: list
          value: ["-O2"]
    - name: entry
      uses: std.Null
      needs: [build]
    configs:
    - name: debug
      extensions:
      - task: pkg.build
        with:
          args: { append: ["-debug_access+all", "-kdb"] }
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="debug")
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    build = builder.findTask("pkg.build")
    assert list(build.params.args) == ["-O2", "-debug_access+all", "-kdb"]


# ------------------------------------------------------------------ #
# 9e. Config extension with prepend                                   #
# ------------------------------------------------------------------ #

def test_config_extension_prepend(tmp_path):
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: build
      with:
        args:
          type: list
          value: ["-O2"]
    - name: entry
      uses: std.Null
      needs: [build]
    configs:
    - name: debug
      extensions:
      - task: pkg.build
        with:
          args: { prepend: ["-g"] }
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="debug")
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    build = builder.findTask("pkg.build")
    assert list(build.params.args) == ["-g", "-O2"]


# ------------------------------------------------------------------ #
# 9f. Config inheritance -- extensions accumulate                     #
# ------------------------------------------------------------------ #

def test_config_inheritance_extensions(tmp_path):
    """Base config appends X, derived config appends Y."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: build
      with:
        args:
          type: list
          value: ["-O2"]
    - name: entry
      uses: std.Null
      needs: [build]
    configs:
    - name: base_dbg
      extensions:
      - task: pkg.build
        with:
          args: { append: ["-debug_access+all"] }
    - name: full_dbg
      uses: base_dbg
      extensions:
      - task: pkg.build
        with:
          args: { append: ["-kdb"] }
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="full_dbg")
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    build = builder.findTask("pkg.build")
    assert list(build.params.args) == ["-O2", "-debug_access+all", "-kdb"]


# ------------------------------------------------------------------ #
# 9g. Extension on a fragment-defined task                            #
# ------------------------------------------------------------------ #

def test_extension_fragment_task(tmp_path):
    """Extension targets a task defined inside a named fragment."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    fragments:
    - tb
    tasks:
    - name: entry
      uses: std.Null
      needs: [tb.build]
    configs:
    - name: debug
      extensions:
      - task: pkg.tb.build
        with:
          args: { append: ["-kdb"] }
""")
    tb_dir = tmp_path / "tb"
    tb_dir.mkdir()
    (tb_dir / "flow.dv").write_text("""\
fragment:
    name: tb
    tasks:
    - name: build
      with:
        args:
          type: list
          value: ["-O2"]
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="debug")
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    build = builder.findTask("pkg.tb.build")
    assert list(build.params.args) == ["-O2", "-kdb"]


# ------------------------------------------------------------------ #
# 9h. Extension injects additional needs                              #
# ------------------------------------------------------------------ #

def test_extension_adds_needs(tmp_path):
    """Extension adds a needs dependency to the target task."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: setup
      uses: std.Null
    - name: build
      with:
        args:
          type: list
          value: ["-O2"]
    - name: entry
      uses: std.Null
      needs: [build]
    configs:
    - name: debug
      extensions:
      - task: pkg.build
        needs: [setup]
        with:
          args: { append: ["-g"] }
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="debug")
    assert pkg is not None
    build_task = pkg.task_m.get("pkg.build")
    assert build_task is not None
    need_names = [n.name if hasattr(n, 'name') else str(n) for n in build_task.needs]
    assert any("setup" in n for n in need_names)


# ------------------------------------------------------------------ #
# 9i. Extension target not found -- error                             #
# ------------------------------------------------------------------ #

def test_extension_target_not_found(tmp_path):
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: entry
      uses: std.Null
    configs:
    - name: debug
      extensions:
      - task: pkg.nonexistent
        with:
          args: { append: ["-g"] }
""")
    collector = MarkerCollector()
    loader, pkg = loadProjPkgDef(str(tmp_path), config="debug",
                                  listener=collector)
    assert any("not found" in m.msg for m in collector.markers)


# ------------------------------------------------------------------ #
# 9j. append on non-list param -- error                               #
# ------------------------------------------------------------------ #

def test_append_on_non_list_param(tmp_path):
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: build
      with:
        mode:
          type: str
          value: "release"
    - name: derived
      uses: pkg.build
      with:
        mode: { append: ["extra"] }
    - name: entry
      uses: std.Null
      needs: [derived]
""")
    collector = MarkerCollector()
    loader, pkg = loadProjPkgDef(str(tmp_path), listener=collector)
    assert any("non-list" in m.msg for m in collector.markers)


# ------------------------------------------------------------------ #
# 9k. No config selected -- extensions do not apply                   #
# ------------------------------------------------------------------ #

def test_no_config_no_extension(tmp_path):
    """Without -c debug, the extension must not modify the param."""
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: build
      with:
        args:
          type: list
          value: ["-O2"]
    - name: entry
      uses: std.Null
      needs: [build]
    configs:
    - name: debug
      extensions:
      - task: pkg.build
        with:
          args: { append: ["-kdb"] }
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))  # no config
    assert pkg is not None
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "r"), loader=loader)
    node = builder.mkTaskNode("pkg.entry")
    build = builder.findTask("pkg.build")
    assert list(build.params.args) == ["-O2"]


# ------------------------------------------------------------------ #
# 9l. Override + extension on same task -- warning                    #
# ------------------------------------------------------------------ #

def test_override_plus_extension_warns(tmp_path):
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: build
      uses: std.Message
      with:
        msg: "original"
    - name: entry
      uses: std.Null
      needs: [build]
    configs:
    - name: debug
      overrides:
      - task: pkg.build
        with: std.Null
      extensions:
      - task: pkg.build
        with:
          msg: { value: "extended" }
""")
    collector = MarkerCollector()
    loader, pkg = loadProjPkgDef(str(tmp_path), config="debug",
                                  listener=collector)
    assert any("no effect" in m.msg.lower() for m in collector.markers)
