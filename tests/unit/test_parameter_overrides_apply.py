import os
from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


def _body(pkg, task_name, rundir):
    """The body of the built *node*.

    `Task.run` is the raw authored text -- it is expanded once per node at
    graph build, from that node's final parameter values (see
    run_body_expansion_plan.md Phase B). Reading it off the Task would test
    the template, not the substitution.
    """
    builder = TaskGraphBuilder(
        root_pkg=pkg, rundir=os.path.join(str(rundir), "rundir"))
    return builder.mkTaskNode(task_name).task.body

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

    # The authored body is stored raw...
    assert "${{ x }}" in pkg.task_m["foo.show"].run

    # ...and expansion at graph build uses the overridden values.
    body = _body(pkg, "foo.show", tmpdir)
    assert "echo" in body
    # Booleans stringify via JSON ('true'/'false')
    assert "5 true" in body

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
    assert "${{ s }}" in pkg.task_m["mypkg.show"].run
    assert "ovr" in _body(pkg, "mypkg.show", tmpdir)
