"""`consumes_declared` across a `uses:` chain.

The flag exists to separate "the author declared what this task consumes" from
"the engine defaulted it", because reading the default as a claim is what made
the dataflow check silently pass for every task that declared nothing.

That held for a task with no base. One `uses:` away it did not: `consumes` was
inherited from the base first, and the flag was derived from the result
afterwards -- but the base has already had `ConsumesE.All` applied, so it always
hands down a non-None value. Every derived task in every project therefore
reported a `consumes:` declaration nobody wrote.

The rule these pin: an inherited *declaration* is a declaration, because the
reader is subject to that contract. An inherited *default* is not.
"""
import os

from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def _load(tmpdir, flow, name="flow.dv"):
    with open(os.path.join(str(tmpdir), name), "w") as f:
        f.write(flow)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), name))
    assert [m.msg for m in collector.markers] == []
    return pkg


def test_an_undeclared_base_does_not_make_the_derived_task_declared(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: p
    tasks:
    - name: Base
    - name: Derived
      uses: Base
""")
    assert pkg.task_m["p.Base"].consumes_declared is False
    assert pkg.task_m["p.Derived"].consumes_declared is False


def test_the_default_does_not_accumulate_down_a_chain(tmpdir):
    """Three levels, nobody declaring anything."""
    pkg = _load(tmpdir, """\
package:
    name: p
    tasks:
    - name: A
    - name: B
      uses: A
    - name: C
      uses: B
""")
    for name in ("p.A", "p.B", "p.C"):
        assert pkg.task_m[name].consumes_declared is False, name


def test_an_inherited_declaration_is_still_a_declaration(tmpdir):
    """Derived says nothing, but inherits a real contract and is subject to it.

    Reporting this as "not declared" would hide a constraint the reader has to
    satisfy.
    """
    pkg = _load(tmpdir, """\
package:
    name: p
    imports:
    - std
    tasks:
    - name: Base
      consumes:
      - type: std.FileSet
    - name: Derived
      uses: Base
""")
    derived = pkg.task_m["p.Derived"]
    assert derived.consumes_declared is True
    assert derived.consumes == [{"type": "std.FileSet"}]


def test_consumes_none_inherits_as_a_declaration(tmpdir):
    """`consumes: none` is an authored claim of "no inputs", not silence."""
    pkg = _load(tmpdir, """\
package:
    name: p
    tasks:
    - name: Base
      consumes: none
    - name: Derived
      uses: Base
""")
    assert pkg.task_m["p.Derived"].consumes_declared is True


def test_a_derived_declaration_overrides_an_undeclared_base(tmpdir):
    pkg = _load(tmpdir, """\
package:
    name: p
    imports:
    - std
    tasks:
    - name: Base
    - name: Derived
      uses: Base
      consumes:
      - type: std.FileSet
""")
    assert pkg.task_m["p.Base"].consumes_declared is False
    assert pkg.task_m["p.Derived"].consumes_declared is True


def test_a_task_with_no_base_is_unaffected(tmpdir):
    """The no-`uses:` case always worked; pin it so the fix cannot regress it."""
    pkg = _load(tmpdir, """\
package:
    name: p
    imports:
    - std
    tasks:
    - name: Undeclared
    - name: Declared
      consumes:
      - type: std.FileSet
""")
    assert pkg.task_m["p.Undeclared"].consumes_declared is False
    assert pkg.task_m["p.Declared"].consumes_declared is True
