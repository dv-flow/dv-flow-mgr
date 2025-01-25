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
        "-v",
        "run",
        "my_task"
    ]

    output = subprocess.check_output(cmd, cwd=rundir, env=env)

    output = output.decode()

    assert output.find("Hello There (p2.foo)") != -1

def test_interface_impl(tmpdir):

    libdir = os.path.join(tmpdir, "lib")

    os.makedirs(libdir)
    ifc_flow_dv = """
package:
  name: ifc

  tasks:
  - name: T1
    uses: std.Message
    with:
      msg: "T1.Interface"
"""

    imp_flow_dv = """
package:
  name: ifc.imp

  tasks:
  - name: T1
    uses: ifc.T1
    with:
      msg: "T1.Imp"
"""

    flow_dv = """
package:
  name: foo

  imports:
  - name: ifc.imp
    as: ifc

  tasks:
  - name: Top
    uses: ifc.T1
"""

    with open(os.path.join(libdir, "ifc.dv"), "w") as fp:
        fp.write(ifc_flow_dv)
    
    os.makedirs(os.path.join(libdir, "ifc"))

    with open(os.path.join(libdir, "ifc/imp.dv"), "w") as fp:
        fp.write(imp_flow_dv)

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    env = os.environ.copy()
    env["DV_FLOW_PATH"] = libdir

    cmd = [
        sys.executable,
        "-m",
        "dv_flow.mgr",
        "-d",
        "run",
        "Top"
    ]

    output = subprocess.check_output(
        cmd, 
        cwd=os.path.join(tmpdir),
        env=env)

    output_s = output.decode()

    print("Output: %s" % output_s)
    assert output_s.find("T1.Imp") != -1

