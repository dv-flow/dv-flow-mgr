import os
import pytest
from dv_flow.mgr import PackageLoader


def test_param_in_needs_after_extpkg_load(tmpdir):
    flow_dv = """
package:
  name: repro
  with:
    sim:
      type: str
      value: vlt
  tasks:
  - name: sim_img
    uses: "hdlsim.${{ sim }}.SimImage"
    needs:
    - "hdlsim.${{ sim }}.SimLibUVM"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    # Previously failed by resolving 'sim' in the wrong package scope; should load successfully now.
    PackageLoader().load(os.path.join(rundir, "flow.dv"))
