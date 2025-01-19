import os
import asyncio
import pytest
from dv_flow_mgr import Session, TaskData

def test_message(tmpdir, capsys):
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    uses: std.Message
    with:
      msg: "Hello, World!"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    rundir = os.path.join(tmpdir, "rundir")
    session = Session(os.path.join(tmpdir), rundir)
    session.load()

    output = asyncio.run(session.run("pkg1.foo"))

    captured = capsys.readouterr()
    assert captured.out.find("Hello, World!") >= 0
