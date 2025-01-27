import os
import pytest
import subprocess
import sys

def test_seq_1(tmpdir):
    rundir = os.path.join(tmpdir)

    flow_dv = """
package:
  name: p1

  tasks:
  - name: files
    uses: std.Message
    with:
      msg: "Running Files"

  - name: print
    uses: std.Message
    needs: [files]
    with:
      msg: "Running Print"
"""

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    with open(os.path.join(rundir, "file.txt"), "w") as fp:
        fp.write("Hello There\n")
    
    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir

    cmd = [
        sys.executable,
        "-m",
        "dv_flow.mgr",
        "run",
        "print"
    ]

    output = subprocess.check_output(cmd, cwd=rundir, env=env)

    output = output.decode()

    print("output: %s" % output)

    assert output.find("Running Files") != -1
    assert output.find("Running Print") != -1

def test_seq_2(tmpdir):
    rundir = os.path.join(tmpdir)

    flow_dv = """
package:
  name: p1

  tasks:
  - name: print1
    uses: std.Message
    with:
      msg: "Running Print 1"

  - name: print
    uses: std.Message
    needs: [print1]
    with:
      msg: "Running Print 2"
"""

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    with open(os.path.join(rundir, "file.txt"), "w") as fp:
        fp.write("Hello There\n")
    
    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir

    cmd = [
        sys.executable,
        "-m",
        "dv_flow.mgr",
        "run",
        "print"
    ]

    output = subprocess.check_output(cmd, cwd=rundir, env=env)

    output = output.decode()
    print("Output: %s" % output)

    assert output.find("Running Print 1") != -1
    assert output.find("Running Print 2") != -1

def test_seq_3(tmpdir):
    rundir = os.path.join(tmpdir)

    flow_dv = """
package:
  name: p1

  tasks:
  - name: print1
    uses: std.Message
    with:
      msg: "Running Print 1"
  - name: print2
    uses: std.Message
    needs: [print1]
    with:
      msg: "Running Print 2"
  - name: print
    uses: std.Message
    needs: [print2]
    with:
      msg: "Running Print 3"
"""

    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    with open(os.path.join(rundir, "file.txt"), "w") as fp:
        fp.write("Hello There\n")
    
    env = os.environ.copy()
    env["DV_FLOW_PATH"] = rundir

    cmd = [
        sys.executable,
        "-m",
        "dv_flow.mgr",
        "run",
        "print"
    ]

    output = subprocess.check_output(cmd, cwd=rundir, env=env)

    output = output.decode()

    print("Output: %s" % output)

    assert output.find("Running Print 1") != -1
    assert output.find("Running Print 2") != -1
    assert output.find("Running Print 3") != -1