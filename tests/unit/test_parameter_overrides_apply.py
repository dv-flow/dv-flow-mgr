import os
from dv_flow.mgr.util import loadProjPkgDef

def test_parameter_overrides_apply_before_elaboration(tmpdir):
    flow_dv = """
package:
  name: foo
  with:
    x:
      type: int
      value: 1
    flag:
      type: bool
      value: false

  tasks:
  - name: show
    shell: bash
    run: |
      echo "${{ x }} ${{ flag }}"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    # Provide parameter overrides via loader API
    loader, pkg = loadProjPkgDef(
        rundir,
        parameter_overrides={"x": "5", "flag": "true"}
    )
    assert pkg is not None

    # Ensure defaults on the package param type are overridden (coerced types)
    assert pkg.paramT.model_fields["x"].default == 5
    assert pkg.paramT.model_fields["flag"].default is True

    # Find the task and ensure expansion uses overridden values
    t = pkg.task_m["foo.show"]
    # run is evaluated at elaboration time using ParamRefEval + resolver
    assert "echo" in t.run
    # Booleans stringify via JSON ('true'/'false')
    assert "5 true" in t.run

def test_parameter_overrides_package_qualified(tmpdir):
    flow_dv = """
package:
  name: mypkg
  with:
    s:
      type: str
      value: def

  tasks:
  - name: show
    shell: bash
    run: |
      echo "${{ s }}"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    # Use a qualified override form "pkg.param"
    loader, pkg = loadProjPkgDef(
        rundir,
        parameter_overrides={"mypkg.s": "ovr"}
    )
    assert pkg is not None
    assert pkg.paramT.model_fields["s"].default == "ovr"
    t = pkg.task_m["mypkg.show"]
    assert "ovr" in t.run
