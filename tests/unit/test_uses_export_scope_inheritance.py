"""
Regression tests: a package that inherits another via package-level `uses:`
must carry forward the base package's task visibility scope (export/root/local)
and description -- both for tasks it overrides and for tasks it inherits
unchanged (aliases).

Previously `is_export`/`is_root`/`is_local` were per-Task booleans set only from
a task's own `scope:` field and never propagated through the `uses` chain, so:
  * an aliased base task (not overridden) lost its export scope, and
  * an overridden base task lost both its export scope and its description
    (the `override:` form carries no inline scope marker).

The result was that `dfm show tasks --scope export` omitted tasks the base
package had exported. See the base<-derived reproduction below.
"""
import os

from dv_flow.mgr import PackageLoader


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


BASE_PKG = """
package:
    name: base_pkg
    tasks:
    - export: src-rtl
      desc: Provides synthesizable Verilog RTL sources
    - export: src-spl
      desc: Provides SPL SystemVerilog sources
"""


def _load_derived(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "base", "flow.dv"), BASE_PKG)
    # derived overrides src-rtl (adding a dependency) but inherits src-spl as-is
    _write(os.path.join(td, "flow.dv"), """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    tasks:
    - name: rtl
      run: echo "rtl"
    - override: src-rtl
      needs:
      - rtl
""")
    return PackageLoader().load(os.path.join(td, "flow.dv"))


def test_overridden_export_task_keeps_scope_and_desc(tmpdir):
    """An overridden base task retains its export scope and description."""
    pkg = _load_derived(tmpdir)

    src_rtl = pkg.task_m["derived_pkg.src-rtl"]
    assert src_rtl.is_export is True
    assert src_rtl.is_root is False
    assert src_rtl.is_local is False
    # desc is inherited from the overridden base task (override specified none)
    assert src_rtl.desc == "Provides synthesizable Verilog RTL sources"
    # the override's own dependency is still applied
    assert any(getattr(n, "name", None) == "derived_pkg.rtl" for n in src_rtl.needs)


def test_inherited_export_task_keeps_scope_and_desc(tmpdir):
    """A non-overridden (aliased) base task retains its export scope and desc."""
    pkg = _load_derived(tmpdir)

    src_spl = pkg.task_m["derived_pkg.src-spl"]
    assert src_spl.is_export is True
    assert src_spl.is_root is False
    assert src_spl.is_local is False
    assert src_spl.desc == "Provides SPL SystemVerilog sources"


def test_override_explicit_scope_is_not_clobbered(tmpdir):
    """An explicit scope on the override wins over the inherited base scope."""
    td = str(tmpdir)
    _write(os.path.join(td, "base", "flow.dv"), BASE_PKG)
    _write(os.path.join(td, "flow.dv"), """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    tasks:
    - override: src-rtl
      scope: root
      run: echo "rtl"
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))

    src_rtl = pkg.task_m["derived_pkg.src-rtl"]
    # explicit scope: root replaces the inherited export scope
    assert src_rtl.is_root is True
    assert src_rtl.is_export is False
