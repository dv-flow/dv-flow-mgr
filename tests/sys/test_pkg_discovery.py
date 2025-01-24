import os
import pytest
import subprocess
import sys
from dv_flow.mgr import PkgRgy


def test_import_specific(tmpdir):
    flow_dv = """
package:
  name: p1

  imports:
  - name: p2

  tasks:
  - name: my_task
    uses: p2.doit
"""

    p2_flow_dv = """
package:
  name: p2

  tasks:
  - name: doit
    uses: std.Message
    with:
      msg: "Hello There"
"""

    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    os.makedirs(os.path.join(rundir, "p2"))
    with open(os.path.join(rundir, "p2/flow.dv"), "w") as fp:
        fp.write(p2_flow_dv)

    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir

    cmd = [
        sys.executable,
        "-m",
        "dv_flow.mgr",
        "run",
        "my_task"
    ]

    output = subprocess.check_output(cmd, cwd=rundir, env=env)

    output = output.decode()

    assert output.find("Hello There") != -1


def test_import_alias(tmpdir):
    flow_dv = """
package:
  name: p1

  imports:
  - name: p2.foo
    as: p2

  tasks:
  - name: my_task
    uses: p2.doit
"""

    p2_flow_dv = """
package:
  name: p2

  tasks:
  - name: doit
    uses: std.Message
    with:
      msg: "Hello There (p2)"
"""

    p2_foo_flow_dv = """
package:
  name: p2.foo

  tasks:
  - name: doit
    uses: std.Message
    with:
      msg: "Hello There (p2.foo)"
"""

    rundir = os.path.join(tmpdir)

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    os.makedirs(os.path.join(rundir, "p2"))
    with open(os.path.join(rundir, "p2/flow.dv"), "w") as fp:
        fp.write(p2_flow_dv)

    with open(os.path.join(rundir, "p2/foo.dv"), "w") as fp:
        fp.write(p2_foo_flow_dv)

#    pkg_rgy = PkgRgy()
#    pkg_rgy.registerPackage("p2", os.path.join(rundir, "p2/flow.dv"))
#    pkg_rgy.registerPackage("p2.foo", os.path.join(rundir, "p2/foo.dv"))

    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir

    cmd = [
        sys.executable,
        "-m",
        "dv_flow.mgr",
        "run",
        "my_task"
    ]

    output = subprocess.check_output(cmd, cwd=rundir, env=env)

    output = output.decode()

    assert output.find("Hello There (p2.foo)") != -1

