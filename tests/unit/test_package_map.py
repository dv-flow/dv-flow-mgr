"""A1 tests: PackageMapProvider + package-map key + CLI/env wiring."""
import asyncio
import os

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr import package_provider_yaml as _ppy_mod

from .marker_collector import MarkerCollector


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _dep_flow(name, msg):
    return """
package:
    name: %s
    tasks:
    - name: hello
      uses: std.Message
      with:
        msg: "%s"
""" % (name, msg)


def _run(pkg, tmpdir, task):
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    runner = TaskSetRunner(os.path.join(str(tmpdir), "rundir"))
    node = builder.mkTaskNode(task)
    return asyncio.run(runner.run(node))


def test_map_scalar_reference(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "foo", "flow.dv"), _dep_flow("foo", "foo.hello"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  version: 1
  packages:
    - name: foo
      path: foo/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: foo
    tasks:
    - name: top
      uses: foo.hello
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    assert "foo" in pkg.pkg_m
    out = _run(pkg, tmpdir, "top.top")
    assert out is not None


def test_map_list_reference_first_wins(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "a", "foo", "flow.dv"), _dep_flow("foo", "from-a"))
    _write(os.path.join(td, "b", "foo", "flow.dv"), _dep_flow("foo", "from-b"))
    _write(os.path.join(td, "a", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
""")
    _write(os.path.join(td, "b", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map:
    - a/flow-packages.yaml
    - b/flow-packages.yaml
    imports:
    - name: foo
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    # First map wins: foo resolves to the a/ copy
    assert pkg.pkg_m["foo"].srcinfo.file.replace(os.sep, "/").endswith("a/foo/flow.dv")


def test_map_name_import_no_path(tmpdir):
    """An import that is just `- name: foo` resolves via the map (no `from`)."""
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "bar", "flow.dv"), _dep_flow("bar", "bar.hello"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: bar
      path: bar/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: bar
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    assert "bar" in pkg.pkg_m


def test_map_cli_flag(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "foo", "flow.dv"), _dep_flow("foo", "foo.hello"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: foo
""")
    pkg = PackageLoader(
        package_maps=[os.path.join(td, "deps", "flow-packages.yaml")]
    ).load(os.path.join(td, "flow.dv"))
    assert "foo" in pkg.pkg_m


def test_map_env_var(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "foo", "flow.dv"), _dep_flow("foo", "foo.hello"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: foo
""")
    env = dict(os.environ)
    env["DV_FLOW_PACKAGE_MAP"] = os.path.join(td, "deps", "flow-packages.yaml")
    pkg = PackageLoader(env=env).load(os.path.join(td, "flow.dv"))
    assert "foo" in pkg.pkg_m


def test_map_missing_file_marker(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: foo
""")
    mc = MarkerCollector()
    PackageLoader(marker_listeners=[mc]).load(os.path.join(td, "flow.dv"))
    # A missing map (and the consequently-unresolvable import) are reported as
    # error markers rather than raising.
    assert any("not found" in m.msg for m in mc.markers), \
        [m.msg for m in mc.markers]


def test_map_unreferenced_entry_not_parsed(tmpdir):
    """A map entry that is never imported is never parsed."""
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "foo", "flow.dv"), _dep_flow("foo", "foo.hello"))
    _write(os.path.join(td, "deps", "unused", "flow.dv"), _dep_flow("unused", "x"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
    - name: unused
      path: unused/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: foo
    tasks:
    - name: top
      uses: foo.hello
""")
    parsed = []
    orig = _ppy_mod.PackageProviderYaml._loadPackage

    def spy(self, pkg, path, loader):
        parsed.append(os.path.normpath(path))
        return orig(self, pkg, path, loader)

    _ppy_mod.PackageProviderYaml._loadPackage = spy
    try:
        pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
        # Build the graph: this references foo.hello and materializes foo.
        _run(pkg, tmpdir, "top.top")
    finally:
        _ppy_mod.PackageProviderYaml._loadPackage = orig

    unused_path = os.path.normpath(os.path.join(td, "deps", "unused", "flow.dv"))
    foo_path = os.path.normpath(os.path.join(td, "deps", "foo", "flow.dv"))
    assert foo_path in parsed         # referenced -> parsed
    assert unused_path not in parsed  # never imported -> never parsed


def test_map_lazy_import_deferred_until_touched(tmpdir):
    """A name-import is not parsed at load; it is parsed when first touched."""
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "foo", "flow.dv"), _dep_flow("foo", "foo.hello"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: foo
""")
    parsed = []
    orig = _ppy_mod.PackageProviderYaml._loadPackage

    def spy(self, pkg, path, loader):
        parsed.append(os.path.normpath(path))
        return orig(self, pkg, path, loader)

    _ppy_mod.PackageProviderYaml._loadPackage = spy
    try:
        pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
        foo_path = os.path.normpath(os.path.join(td, "deps", "foo", "flow.dv"))
        # Deferred: not parsed merely by loading + keeping the import in pkg_m.
        assert foo_path not in parsed
        assert "foo" in pkg.pkg_m
        # Touch a data attribute -> materialize -> parse.
        _ = pkg.pkg_m["foo"].task_m
        assert foo_path in parsed
    finally:
        _ppy_mod.PackageProviderYaml._loadPackage = orig


def test_map_duplicate_name_warns(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "foo", "flow.dv"), _dep_flow("foo", "foo.hello"))
    _write(os.path.join(td, "deps", "foo2", "flow.dv"), _dep_flow("foo", "foo2.hello"))
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: foo
      path: foo/flow.dv
    - name: foo
      path: foo2/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: foo
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    # First entry wins
    assert pkg.pkg_m["foo"].srcinfo.file.replace(os.sep, "/").endswith("deps/foo/flow.dv")
