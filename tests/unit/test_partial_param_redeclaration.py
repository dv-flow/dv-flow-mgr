"""Re-declaring an inherited parameter without restating `type:`.

A derived task usually wants to change exactly one thing about an inherited
parameter -- its default, or nothing but `cli: false` to drop the flag. Written
the natural way, without repeating `type:`, that declaration took a different
code path from the fully-restated form, and on that path two things went wrong:

1. The whole `ParamDef` was stored as the parameter's *value*. `dfm show task`
   printed a pydantic repr where the default belongs, and if the base declared a
   `values:` set, the task failed value-set validation outright -- the stored
   "value" was, of course, not one of the accepted values.
2. Everything except the value was dropped, so `cli: false` -- the only spelling
   for "remove a flag inherited from a base task" -- had no effect at all.

Both were invisible to the existing tests because those restate `type:`, which
takes the typed-declaration branch.

The rule these pin: a re-declaration inherits, per field, whatever it does not
mention. `values:` and `cli:` already worked that way; `value`, `doc` and `desc`
now do too.
"""
import os

import pytest

from dv_flow.mgr import PackageLoader
from dv_flow.mgr.cli_args import resolve_task_cli
from dv_flow.mgr.task import collect_task_params, collect_param_value_sets
from .marker_collector import MarkerCollector


def _load(tmpdir, flow, name="flow.dv"):
    with open(os.path.join(str(tmpdir), name), "w") as f:
        f.write(flow)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), name))
    assert [m.msg for m in collector.markers] == []
    return pkg


BASE = """\
package:
    name: p
    tasks:
    - name: Base
      with:
        opt:
          type: str
          value: base-value
          cli: true
          doc: What opt does.
          values:
          - {value: base-value, desc: The base pick.}
          - {value: leaf-value, desc: The leaf pick.}
        keep:
          type: str
          value: kept
          cli: true
          doc: Has a flag until someone removes it.
%s
"""


def _derived(body):
    return BASE % body


# ----------------------------------------------------- value-only declaration

def test_value_only_override_stores_the_value_not_the_paramdef(tmpdir):
    """The regression itself: `{value: x}` must store `x`."""
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        opt:
          value: leaf-value
"""))
    defs, _ = collect_task_params(pkg.task_m["p.Leaf"])
    assert defs["opt"].value == "leaf-value"


def test_value_only_override_keeps_the_inherited_doc(tmpdir):
    """Changing a default is not a claim about the documentation."""
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        opt:
          value: leaf-value
"""))
    defs, _ = collect_task_params(pkg.task_m["p.Leaf"])
    assert defs["opt"].doc.strip() == "What opt does."


def test_value_only_override_keeps_the_inherited_value_set(tmpdir):
    """The engine's documented rule: a value set inherits independently."""
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        opt:
          value: leaf-value
"""))
    vs = collect_param_value_sets(pkg.task_m["p.Leaf"])
    assert vs["opt"].describe() == "base-value, leaf-value"


def test_value_only_override_survives_value_set_validation(tmpdir, tmp_path):
    """This is what actually broke a real flow, not just its documentation.

    With the whole ParamDef stored as the value, building the parameter type
    raised ParamValueError: the "value" was a pydantic repr, which is not one
    of the accepted values.
    """
    from dv_flow.mgr.task_graph_builder import TaskGraphBuilder
    from dv_flow.mgr.util import loadProjPkgDef

    with open(os.path.join(str(tmpdir), "flow.yaml"), "w") as f:
        f.write(_derived("""\
    - name: Leaf
      uses: Base
      with:
        opt:
          value: leaf-value
"""))
    loader, pkg = loadProjPkgDef(str(tmpdir))
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"), loader=loader)
    values = builder.resolveTaskParams(pkg.task_m["p.Leaf"])
    assert values["opt"] == "leaf-value"


# --------------------------------------------------------- `cli:`-only change

def test_cli_false_without_restating_type_removes_the_flag(tmpdir):
    """`cli: false` is the ONLY spelling for removing an inherited flag.

    Restating `type:` alongside it worked; omitting it silently did nothing,
    which is the form anyone would write.
    """
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        keep:
          cli: false
"""))
    assert [a.param for a in resolve_task_cli(pkg.task_m["p.Leaf"])] == ["opt"]


def test_cli_false_keeps_the_parameter_and_its_value(tmpdir):
    """Removing the flag removes the flag, not the parameter.

    `keep` is still settable with -D, so erasing its default would change what
    the task does -- not merely how it is documented.
    """
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        keep:
          cli: false
"""))
    defs, types = collect_task_params(pkg.task_m["p.Leaf"])
    assert "keep" in defs
    assert defs["keep"].value == "kept"
    assert defs["keep"].doc.strip() == "Has a flag until someone removes it."
    assert types["keep"] is str


# ------------------------------------------------------------- non-regression

def test_a_bare_value_override_still_works(tmpdir):
    """`opt: leaf-value` -- the terse form, which never went through ParamDef."""
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        opt: leaf-value
"""))
    defs, _ = collect_task_params(pkg.task_m["p.Leaf"])
    assert defs["opt"].value == "leaf-value"


def test_restating_type_still_replaces_what_it_restates(tmpdir):
    """Per-field inheritance fills gaps; it does not override a statement."""
    pkg = _load(tmpdir, _derived("""\
    - name: Leaf
      uses: Base
      with:
        opt:
          type: str
          value: leaf-value
          doc: Leaf has its own words.
          values:
          - {value: leaf-value, desc: The only one now.}
"""))
    defs, _ = collect_task_params(pkg.task_m["p.Leaf"])
    assert defs["opt"].doc.strip() == "Leaf has its own words."
    vs = collect_param_value_sets(pkg.task_m["p.Leaf"])
    assert vs["opt"].describe() == "leaf-value"


def test_a_three_level_chain_inherits_from_the_nearest_declaration(tmpdir):
    pkg = _load(tmpdir, _derived("""\
    - name: Middle
      uses: Base
      with:
        opt:
          doc: Middle rewrote the docs.
    - name: Leaf
      uses: Middle
      with:
        opt:
          value: leaf-value
"""))
    defs, _ = collect_task_params(pkg.task_m["p.Leaf"])
    assert defs["opt"].value == "leaf-value"
    assert defs["opt"].doc.strip() == "Middle rewrote the docs."
