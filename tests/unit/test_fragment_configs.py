"""Tests for fragment-level configs support."""
import asyncio
import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef
from .marker_collector import MarkerCollector


def test_fragment_config_basic(tmp_path):
    """Fragment defines a config; selecting it by qualified name works."""
    frag_dir = tmp_path / "sim"
    frag_dir.mkdir()
    (frag_dir / "flow.dv").write_text("""\
fragment:
    name: sim
    tasks:
    - name: compile
      uses: std.Message
      with:
        msg: "compile_base"
    configs:
    - name: debug
      tasks:
      - name: compile
        uses: std.Message
        with:
          msg: "compile_debug"
""")
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    fragments:
    - sim
    tasks:
    - name: entry
      uses: std.Message
      needs: [sim.compile]
      with:
        msg: "entry_msg"
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="sim.debug")
    assert pkg is not None
    # The unified configs list should contain the qualified config name
    assert any(c.name == "sim.debug" for c in pkg.all_configs)


def test_fragment_config_default(tmp_path):
    """Fragment can define a 'default' config; it gets qualified name."""
    frag_dir = tmp_path / "sim"
    frag_dir.mkdir()
    (frag_dir / "flow.dv").write_text("""\
fragment:
    name: sim
    tasks:
    - name: run
      uses: std.Message
      with:
        msg: "run_base"
    configs:
    - name: default
      tasks:
      - name: run
        uses: std.Message
        with:
          msg: "run_cfg"
""")
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    fragments:
    - sim
    tasks: []
""")
    # Fragment 'default' config becomes 'sim.default', NOT the package default
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert pkg is not None
    # 'sim.default' should not be auto-selected (only bare 'default' is)
    config_names = [c.name for c in pkg.all_configs]
    assert "sim.default" in config_names


def test_fragment_config_no_name_error(tmp_path):
    """Fragment without a name that defines configs produces an error."""
    frag_dir = tmp_path / "unnamed"
    frag_dir.mkdir()
    (frag_dir / "flow.dv").write_text("""\
fragment:
    tasks:
    - name: t1
      uses: std.Message
      with:
        msg: "t1"
    configs:
    - name: debug
      tasks:
      - name: t1
        uses: std.Message
        with:
          msg: "t1_debug"
""")
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    fragments:
    - unnamed
    tasks: []
""")
    mc = MarkerCollector()
    loader, pkg = loadProjPkgDef(str(tmp_path), listener=mc)
    # Should have an error about missing fragment name
    assert any("must have a name" in m.msg for m in mc.markers), \
        f"Expected 'must have a name' error, got: {[m.msg for m in mc.markers]}"


def test_config_fragment_with_configs_error(tmp_path):
    """Fragments loaded via a config that define configs produce an error."""
    # Fragment loaded from config
    cfg_frag_dir = tmp_path / "cfg_frag"
    cfg_frag_dir.mkdir()
    (cfg_frag_dir / "flow.dv").write_text("""\
fragment:
    name: cfg_frag
    tasks:
    - name: t1
      uses: std.Message
      with:
        msg: "t1"
    configs:
    - name: nested
      tasks:
      - name: t1
        uses: std.Message
        with:
          msg: "t1_nested"
""")
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    tasks:
    - name: entry
      uses: std.Message
      with:
        msg: "entry"
    configs:
    - name: myconf
      fragments:
      - cfg_frag
""")
    mc = MarkerCollector()
    loader, pkg = loadProjPkgDef(str(tmp_path), config="myconf", listener=mc)
    # Should have an error about config-loaded fragments defining configs
    assert any("cannot define configs" in m.msg.lower() for m in mc.markers), \
        f"Expected 'cannot define configs' error, got: {[m.msg for m in mc.markers]}"


def test_fragment_config_merged_with_package(tmp_path, capsys):
    """Package configs and fragment configs coexist in all_configs."""
    frag_dir = tmp_path / "frag"
    frag_dir.mkdir()
    (frag_dir / "flow.dv").write_text("""\
fragment:
    name: myfrag
    tasks:
    - name: t1
      uses: std.Message
      with:
        msg: "frag_t1"
    configs:
    - name: fast
      tasks:
      - name: t1
        uses: std.Message
        with:
          msg: "frag_t1_fast"
""")
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    fragments:
    - frag
    tasks:
    - name: entry
      uses: std.Message
      with:
        msg: "entry"
    configs:
    - name: release
      tasks:
      - name: extra
        uses: std.Message
        with:
          msg: "entry_release"
""")
    loader, pkg = loadProjPkgDef(str(tmp_path))
    config_names = sorted([c.name for c in pkg.all_configs])
    assert "release" in config_names
    assert "myfrag.fast" in config_names


def test_fragment_config_uses_package_config(tmp_path):
    """A fragment config can inherit from a package-level config via 'uses'."""
    frag_dir = tmp_path / "frag"
    frag_dir.mkdir()
    (frag_dir / "flow.dv").write_text("""\
fragment:
    name: myfrag
    tasks:
    - name: t1
      uses: std.Message
      with:
        msg: "base"
    configs:
    - name: extended
      uses: base_cfg
      tasks:
      - name: t1
        uses: std.Message
        with:
          msg: "extended_from_base"
""")
    (tmp_path / "flow.dv").write_text("""\
package:
    name: pkg
    fragments:
    - frag
    tasks:
    - name: entry
      uses: std.Message
      with:
        msg: "entry"
    configs:
    - name: base_cfg
      tasks:
      - name: extra
        uses: std.Message
        with:
          msg: "entry_base_cfg"
""")
    loader, pkg = loadProjPkgDef(str(tmp_path), config="myfrag.extended")
    assert pkg is not None
    # Config was selected and applied (no errors)
    config_names = [c.name for c in pkg.all_configs]
    assert "myfrag.extended" in config_names
    assert "base_cfg" in config_names
