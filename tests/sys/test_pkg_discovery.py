import os
import pytest
import subprocess
import sys


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
  - name: p2
    as: p3

  tasks:
  - name: my_task
    uses: p3.doit
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

