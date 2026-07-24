import os
from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def test_failed_uses_reports_expanded_name(tmpdir):
    # SIM expands inside uses to a non-existent sim backend ("nope")
    flow_dv = """
package:
  name: foo
  with:
    SIM:
      type: str
      value: nope

  tasks:
  - name: T
  - name: U
    uses: "hdlsim.${{ SIM }}.SimImage"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    markers = MarkerCollector()
    _ = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 1
    # Message should include the evaluated uses target, not the raw template
    assert "failed to resolve task-uses hdlsim.nope.SimImage" in markers.markers[0].msg


def test_failed_needs_reports_expanded_name(tmpdir):
    # NEED expands inside needs to a non-existent task ("nope")
    flow_dv = """
package:
  name: foo
  with:
    NEED:
      type: str
      value: nope

  tasks:
  - name: T
  - name: U
    needs: ["${{ NEED }}"]
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    markers = MarkerCollector()
    _ = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))

    assert len(markers.markers) == 1
    # Message should include the evaluated need name, not the raw template
    assert "failed to find task 'nope'" in markers.markers[0].msg


def test_failed_needs_suggests_close_match(tmpdir):
    # A typo'd needs reference should report a clean error (no NoneType crash from
    # a dangling None appended to task.needs) AND suggest the closest task name.
    flow_dv = """
package:
  name: foo

  tasks:
  - name: build-image
  - name: run
    needs: [build-imag]
"""
    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    markers = MarkerCollector()
    _ = PackageLoader(marker_listeners=[markers]).load(os.path.join(tmpdir, "flow.dv"))

    # Exactly one clean error marker -- not an opaque parse crash.
    assert len(markers.markers) == 1
    msg = markers.markers[0].msg
    assert "failed to find task 'build-imag'" in msg
    assert "did you mean 'build-image'?" in msg
