"""
Resolution of unqualified references to tasks inherited via package-level
`uses:`, from within the deriving package (root file or a fragment, named or
unnamed).

The namespace is a *stack*, and the nearest enclosing match wins. When package
`derived_pkg` does `uses: base_pkg`, base task `base-env` is aliased into
`derived_pkg` as `derived_pkg.base-env`. A named fragment `frag` adds one more
level. An unqualified reference resolves outward:

    derived_pkg.frag.base-env   (fragment)   -- searched first
    derived_pkg.base-env        (package)     -- the inherited alias
    base_pkg.base-env           (used pkg)    -- searched last

Regression: the aliased task was keyed only under its fully-qualified name, so
the unqualified reference missed it and failed with an ambiguous
"Did you mean 'derived_pkg.base-env, base_pkg.base-env'?" error. Resolution must
also behave identically whether or not the referencing task lives in a *named*
fragment -- a fragment simply adds a level to the stack.
"""
import os

from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


BASE_PKG = """
package:
    name: base_pkg
    tasks:
    - name: base-env
      with:
        msg:
          type: str
          value: from-base
"""


def _load(tmpdir, root_text, frag_files=None):
    """Write base_pkg + a derived flow.dv (root_text) and optional fragments."""
    td = str(tmpdir)
    _write(os.path.join(td, "base", "flow.dv"), BASE_PKG)
    for name, text in (frag_files or {}).items():
        _write(os.path.join(td, name), text)
    _write(os.path.join(td, "flow.dv"), root_text)
    mc = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[mc]).load(os.path.join(td, "flow.dv"))
    return pkg, mc


def _errors(mc):
    return [m for m in mc.markers if "Error" in str(m.severity)]


# --- 1. named fragment, `uses` an inherited task by bare name ----------------
def test_named_fragment_uses_inherited_task(tmpdir):
    pkg, mc = _load(tmpdir, """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    fragments:
    - frag.dv
""", {"frag.dv": """
fragment:
    name: frag
    tasks:
    - root: user-env
      uses: base-env
"""})

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["derived_pkg.frag.user-env"]
    # nearest enclosing match wins: the deriving package's own alias
    assert user.uses is not None
    assert user.uses.name == "derived_pkg.base-env", user.uses.name


# --- 2. UNnamed fragment: resolution must be identical -----------------------
def test_unnamed_fragment_uses_inherited_task(tmpdir):
    pkg, mc = _load(tmpdir, """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    fragments:
    - frag.dv
""", {"frag.dv": """
fragment:
    tasks:
    - root: user-env
      uses: base-env
"""})

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["derived_pkg.user-env"]
    assert user.uses is not None
    assert user.uses.name == "derived_pkg.base-env", user.uses.name


# --- 3. task in the root package file (no fragment) --------------------------
def test_root_package_uses_inherited_task(tmpdir):
    pkg, mc = _load(tmpdir, """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    tasks:
    - root: user-env
      uses: base-env
""")

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["derived_pkg.user-env"]
    assert user.uses is not None
    assert user.uses.name == "derived_pkg.base-env", user.uses.name


# --- 4. `needs` (shares the resolver) ---------------------------------------
def test_named_fragment_needs_inherited_task(tmpdir):
    pkg, mc = _load(tmpdir, """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    fragments:
    - frag.dv
""", {"frag.dv": """
fragment:
    name: frag
    tasks:
    - root: user-env
      needs: [base-env]
"""})

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["derived_pkg.frag.user-env"]
    need_names = [n.name for n in user.needs]
    assert "derived_pkg.base-env" in need_names, need_names


# --- 5. fragment-level task shadows a same-named package task ----------------
# A bare reference from within the fragment must bind the *fragment* task
# (nearest), not the package-level one -- this exercises the innermost-first
# ordering of `uses` resolution.
def test_fragment_task_shadows_package_task(tmpdir):
    pkg, mc = _load(tmpdir, """
package:
    name: derived_pkg
    tasks:
    - name: thing
      with:
        who:
          type: str
          value: package-level
    fragments:
    - frag.dv
""", {"frag.dv": """
fragment:
    name: frag
    tasks:
    - name: thing
      with:
        who:
          type: str
          value: fragment-level
    - root: user
      uses: thing
"""})

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["derived_pkg.frag.user"]
    assert user.uses is not None
    assert user.uses.name == "derived_pkg.frag.thing", (
        "nearest (fragment) task should win, got %s" % user.uses.name)


# --- 6. transitive inheritance: A uses B uses C -----------------------------
def test_transitive_inheritance_uses(tmpdir):
    td = str(tmpdir)
    _write(os.path.join(td, "c", "flow.dv"), """
package:
    name: pkg_c
    tasks:
    - name: deep-task
      with:
        msg:
          type: str
          value: from-c
""")
    _write(os.path.join(td, "b", "flow.dv"), """
package:
    name: pkg_b
    uses: pkg_c
    imports:
    - name: pkg_c
      from: ../c/flow.dv
""")
    _write(os.path.join(td, "frag.dv"), """
fragment:
    name: frag
    tasks:
    - root: user
      uses: deep-task
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: pkg_a
    uses: pkg_b
    imports:
    - name: pkg_b
      from: b/flow.dv
    fragments:
    - frag.dv
""")
    mc = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[mc]).load(os.path.join(td, "flow.dv"))

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["pkg_a.frag.user"]
    assert user.uses is not None
    # nearest wins all the way up the chain: pkg_a's own alias
    assert user.uses.name == "pkg_a.deep-task", user.uses.name


# --- 7. qualified reference still resolves (regression guard) ----------------
def test_qualified_reference_still_works(tmpdir):
    pkg, mc = _load(tmpdir, """
package:
    name: derived_pkg
    uses: base_pkg
    imports:
    - name: base_pkg
      from: base/flow.dv
    fragments:
    - frag.dv
""", {"frag.dv": """
fragment:
    name: frag
    tasks:
    - root: user-env
      uses: base_pkg.base-env
"""})

    assert not _errors(mc), [m.msg for m in _errors(mc)]
    user = pkg.task_m["derived_pkg.frag.user-env"]
    assert user.uses is not None
    assert user.uses.name == "base_pkg.base-env", user.uses.name
