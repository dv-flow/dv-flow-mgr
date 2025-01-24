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
    uses: std.FileSet
    with:
      type: textFiles
      include: "*.txt"

  - name: print
    uses: std.Message
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

    assert output.find("Running Print") != -1