"""
Regression: a `type: list` parameter whose value is a list of maps must keep
each map intact. Previously TaskGraphBuilder._expandParam appended an extra
one-key map for every string-valued key of each map element, e.g.
[{a: x, n: 1}] -> [{'a': 'x'}, {'a': 'x', 'n': 1}].
"""
import os
from dv_flow.mgr import PackageLoader, TaskGraphBuilder


FLOW = '''
package:
  name: lm
  with:
    who: {type: str, value: world}
  tasks:
  - name: base
    with:
      items: {type: list, value: []}
  - name: use
    uses: base
    with:
      items:
      - {a: x, n: 1}
      - {a: y, b: z, n: 2, f: true}
  - name: direct
    with:
      items:
        type: list
        value:
        - {a: x, n: 1}
  - name: strs_only
    with:
      items:
        type: list
        value:
        - {a: x, b: y}
  - name: expr
    uses: base
    with:
      items:
      - {a: "hello ${{ who }}", n: 3}
'''


def _items(tmpdir, taskname):
    rundir = os.path.join(tmpdir, "rundir")
    os.makedirs(rundir, exist_ok=True)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(FLOW)
    pkg_def = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg_def, rundir)
    node = builder.mkTaskNode(taskname)
    return node.params.items


def test_list_of_maps_override(tmpdir):
    assert _items(tmpdir, "lm.use") == [
        {"a": "x", "n": 1},
        {"a": "y", "b": "z", "n": 2, "f": True},
    ]


def test_list_of_maps_direct(tmpdir):
    assert _items(tmpdir, "lm.direct") == [{"a": "x", "n": 1}]


def test_list_of_maps_all_strings(tmpdir):
    assert _items(tmpdir, "lm.strs_only") == [{"a": "x", "b": "y"}]


def test_list_of_maps_with_expression(tmpdir):
    assert _items(tmpdir, "lm.expr") == [{"a": "hello world", "n": 3}]
