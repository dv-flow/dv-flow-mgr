"""C1 tests: LazyPackage deferral + transparent materialization."""
import asyncio
import os

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.package import LazyPackage
from dv_flow.mgr import package_provider_yaml as _ppy_mod

from .marker_collector import MarkerCollector


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _run(pkg, tmpdir, task):
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    runner = TaskSetRunner(os.path.join(str(tmpdir), "rundir"))
    node = builder.mkTaskNode(task)
    return asyncio.run(runner.run(node))


def _dep(name, msg):
    return """
package:
    name: %s
    tasks:
    - name: hello
      uses: std.Message
      with:
        msg: "%s"
""" % (name, msg)


class _ParseSpy:
    def __init__(self):
        self.paths = []
        self._orig = _ppy_mod.PackageProviderYaml._loadPackage

    def __enter__(self):
        spy = self
        orig = self._orig

        def patched(self, pkg, path, loader):
            spy.paths.append(os.path.normpath(path))
            return orig(self, pkg, path, loader)
        _ppy_mod.PackageProviderYaml._loadPackage = patched
        return self

    def __exit__(self, *a):
        _ppy_mod.PackageProviderYaml._loadPackage = self._orig

    def parsed(self, path):
        return os.path.normpath(path) in self.paths


def test_lazy_name_from_deferred(tmpdir):
    """A `{name, from}` import is a LazyPackage, parsed only when touched."""
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "foo", "flow.dv"), _dep("foo", "foo"))
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: foo
      from: vendor/foo/flow.dv
""")
    foo_path = os.path.join(td, "vendor", "foo", "flow.dv")
    with _ParseSpy() as spy:
        pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
        assert isinstance(pkg.pkg_m["foo"], LazyPackage)
        assert not pkg.pkg_m["foo"].is_materialized()
        assert not spy.parsed(foo_path)
        # Touch -> materialize -> parse
        assert "hello" in [t.split(".")[-1] for t in pkg.pkg_m["foo"].task_m.keys()]
        assert pkg.pkg_m["foo"].is_materialized()
        assert spy.parsed(foo_path)


def test_lazy_alias_deferred(tmpdir):
    """An aliased name-import records the alias without materializing."""
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "foo", "flow.dv"), _dep("foo", "foo"))
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: foo
      from: vendor/foo/flow.dv
      as: f
""")
    foo_path = os.path.join(td, "vendor", "foo", "flow.dv")
    with _ParseSpy() as spy:
        pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
        # Alias recorded; package still not parsed.
        assert pkg.pkg_alias_m.get("f") == "foo"
        assert not spy.parsed(foo_path)


def test_lazy_build_materializes_all_imports(tmpdir):
    """The builder flattens every import, so an import is materialized by graph
    build even when the built task does not reference it (an enumerate site).

    Note: a root package with no tasks is used so load-time name resolution
    does not itself scan (and thus materialize) imports -- isolating the
    builder as the trigger.
    """
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "foo", "flow.dv"), _dep("foo", "foo"))
    # Root imports foo but defines no tasks of its own that scan packages.
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: foo
      from: vendor/foo/flow.dv
""")
    foo_path = os.path.join(td, "vendor", "foo", "flow.dv")
    with _ParseSpy() as spy:
        pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
        assert not spy.parsed(foo_path)  # nothing touched foo at load
        # Constructing the builder flattens all imports -> foo materializes.
        TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(td, "rundir"))
        assert spy.parsed(foo_path)


def test_lazy_uses_reference_materializes_at_load(tmpdir):
    """A root task that `uses:` an imported package materializes it at load."""
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "foo", "flow.dv"), _dep("foo", "foo"))
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: foo
      from: vendor/foo/flow.dv
    tasks:
    - name: top
      uses: foo.hello
""")
    foo_path = os.path.join(td, "vendor", "foo", "flow.dv")
    with _ParseSpy() as spy:
        pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
        assert spy.parsed(foo_path)  # resolving `uses: foo.hello` touched foo
        out = _run(pkg, tmpdir, "top.top")
        assert out is not None


def test_lazy_unresolved_name_errors_at_load(tmpdir):
    """An import naming a package no provider can resolve errors at load time
    (deferral must not hide unresolved imports)."""
    td = str(tmpdir)
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: does_not_exist
""")
    mc = MarkerCollector()
    PackageLoader(marker_listeners=[mc]).load(os.path.join(td, "flow.dv"))
    assert any("does_not_exist" in m.msg and "not found" in m.msg for m in mc.markers), \
        [m.msg for m in mc.markers]


def test_lazy_cycle_resolves(tmpdir):
    """Lazy imports break a cyclic import graph naturally: a<->b resolves and
    runs instead of looping or erroring (each side defers the other)."""
    td = str(tmpdir)
    _write(os.path.join(td, "deps", "a", "flow.dv"), """
package:
    name: a
    imports:
    - name: b
    tasks:
    - name: t
      uses: b.hello
""")
    _write(os.path.join(td, "deps", "b", "flow.dv"), """
package:
    name: b
    imports:
    - name: a
    tasks:
    - name: hello
      uses: std.Message
      with:
        msg: "b"
""")
    _write(os.path.join(td, "deps", "flow-packages.yaml"), """
package-map:
  packages:
    - name: a
      path: a/flow.dv
    - name: b
      path: b/flow.dv
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    package-map: deps/flow-packages.yaml
    imports:
    - name: a
    tasks:
    - name: top
      uses: a.t
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    # Cycle resolves and runs (terminates -- no infinite loop).
    out = _run(pkg, tmpdir, "top.top")
    assert out is not None
