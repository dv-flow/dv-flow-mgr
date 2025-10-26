import os
from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def test_expand_vars_in_uses_and_needs_top_level(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      BASE:
        type: str
        value: t1
      NEED:
        type: str
        value: t1

    tasks:
    - name: t1
    - name: t2
      uses: "${{ BASE }}"
      needs: ["${{ NEED }}"]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))

    # No error markers expected
    assert len(markers.markers) == 0

    assert "foo.t1" in pkg.task_m
    assert "foo.t2" in pkg.task_m

    t1 = pkg.task_m["foo.t1"]
    t2 = pkg.task_m["foo.t2"]

    # uses should resolve to the task referenced by the package variable
    assert t2.uses is not None
    assert getattr(t2.uses, "name", None) == t1.name

    # needs should resolve to the task referenced by the package variable
    assert len(t2.needs) == 1
    assert t2.needs[0] is not None
    assert t2.needs[0].name == t1.name


def test_expand_vars_in_uses_and_needs_in_subtasks(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      BASE:
        type: str
        value: t3
      NEED:
        type: str
        value: t1

    tasks:
    - name: t1
    - name: t3
    - name: P
      body:
      - name: C1
        uses: "${{ BASE }}"
      - name: C2
        needs: ["${{ NEED }}"]
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    markers = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))

    # No error markers expected
    assert len(markers.markers) == 0

    assert "foo.P" in pkg.task_m
    P = pkg.task_m["foo.P"]
    assert len(P.subtasks) == 2

    C1 = P.subtasks[0]
    C2 = P.subtasks[1]

    # Subtask uses should resolve via package variable
    assert C1.uses is not None
    assert getattr(C1.uses, "name", None) == "foo.t3"

    # Subtask needs should resolve via package variable
    assert len(C2.needs) == 1
    assert C2.needs[0] is not None
    assert C2.needs[0].name == "foo.t1"
