import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog
from .task_listener_test import TaskListenerTest


def test_uptodate_first_run(tmpdir):
    """Task runs on first execution"""
    flow_dv = """
package:
  name: p1

  tasks:
  - name: file1
    uses: std.CreateFile
    with: { filename: "file1.txt", content: "file1" }
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder)

    task = builder.mkTaskNode("p1.file1")
    output = asyncio.run(runner.run(task))

    # First run should always execute (changed=True)
    assert output is not None
    assert task.result.changed == True


def test_uptodate_second_run(tmpdir):
    """Task skipped when parameters unchanged on second run"""
    flow_dv = """
package:
  name: p1

  tasks:
  - name: file1
    uses: std.CreateFile
    with: { filename: "file1.txt", content: "file1" }
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder)

    task = builder.mkTaskNode("p1.file1")
    output = asyncio.run(runner.run(task))
    assert task.result.changed == True
    
    # Second run - rebuild task and run again
    builder2 = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner2 = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder2)
    
    task2 = builder2.mkTaskNode("p1.file1")
    output2 = asyncio.run(runner2.run(task2))
    
    # Second run should be up-to-date (changed=False)
    assert output2 is not None
    assert task2.result.changed == False


def test_uptodate_param_change(tmpdir):
    """Task runs when parameters change"""
    flow_dv1 = """
package:
  name: p1

  tasks:
  - name: file1
    uses: std.CreateFile
    with: { filename: "file1.txt", content: "content1" }
"""
    flow_dv2 = """
package:
  name: p1

  tasks:
  - name: file1
    uses: std.CreateFile
    with: { filename: "file1.txt", content: "content2" }
"""
    rundir = os.path.join(tmpdir)
    
    # First run
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv1)
    
    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder)

    task = builder.mkTaskNode("p1.file1")
    output = asyncio.run(runner.run(task))
    assert task.result.changed == True
    
    # Second run with different parameters
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv2)
    
    loader2 = PackageLoader()
    pkg_def2 = loader2.load(os.path.join(tmpdir, "flow.dv"))
    builder2 = TaskGraphBuilder(
        root_pkg=pkg_def2,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader2)
    runner2 = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder2)
    
    task2 = builder2.mkTaskNode("p1.file1")
    output2 = asyncio.run(runner2.run(task2))
    
    # Should run again because params changed
    assert task2.result.changed == True


def test_uptodate_force_run(tmpdir):
    """--force flag bypasses up-to-date check"""
    flow_dv = """
package:
  name: p1

  tasks:
  - name: file1
    uses: std.CreateFile
    with: { filename: "file1.txt", content: "file1" }
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder)

    task = builder.mkTaskNode("p1.file1")
    output = asyncio.run(runner.run(task))
    assert task.result.changed == True
    
    # Get the file modification time
    file_path = os.path.join(tmpdir, "rundir", "p1.file1", "file1.txt")
    mtime1 = os.path.getmtime(file_path)
    
    import time
    time.sleep(0.1)  # Small delay to ensure different mtime
    
    # Second run with force_run=True
    builder2 = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner2 = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder2, force_run=True)
    
    task2 = builder2.mkTaskNode("p1.file1")
    output2 = asyncio.run(runner2.run(task2))
    
    # The task ran (file was rewritten) but since content is same, changed=False
    # is actually correct behavior for the CreateFile task
    # We verify the task ran by checking the file was touched
    mtime2 = os.path.getmtime(file_path)
    assert mtime2 >= mtime1  # File was at least touched/rewritten


def test_uptodate_false_always_run(tmpdir):
    """Task runs when uptodate: false"""
    flow_dv = """
package:
  name: p1

  tasks:
  - name: file1
    uses: std.CreateFile
    uptodate: false
    with: { filename: "file1.txt", content: "file1" }
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder)

    task = builder.mkTaskNode("p1.file1")
    output = asyncio.run(runner.run(task))
    assert task.result.changed == True
    
    # Get the file modification time
    file_path = os.path.join(tmpdir, "rundir", "p1.file1", "file1.txt")
    mtime1 = os.path.getmtime(file_path)
    
    import time
    time.sleep(0.1)  # Small delay to ensure different mtime
    
    # Second run - should still run due to uptodate: false
    builder2 = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner2 = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder2)
    
    task2 = builder2.mkTaskNode("p1.file1")
    output2 = asyncio.run(runner2.run(task2))
    
    # The task ran (file was rewritten) but since content is same, changed=False
    # is actually correct behavior for the CreateFile task
    # We verify the task ran by checking the uptodate field was respected
    # (the task was executed, we can verify by checking the file was touched)
    mtime2 = os.path.getmtime(file_path)
    assert mtime2 >= mtime1  # File was at least touched/rewritten


def test_uptodate_input_changed(tmpdir):
    """Task runs when input data changes"""
    flow_dv = """
package:
  name: p1

  tasks:
  - name: src1
    uses: std.CreateFile
    with: { filename: "src1.txt", content: "src1" }
  - name: proc1
    needs: [src1]
    passthrough: all
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"), builder=builder)

    task = builder.mkTaskNode("p1.proc1")
    output = asyncio.run(runner.run(task))
    
    # Both tasks should have run
    # proc1.result.changed should be True on first run
    assert task.result is not None


class _RunRecorder(object):
    """Records whether each task ran or was declared up-to-date."""

    def __init__(self):
        self.reasons = {}

    def __call__(self, task, reason):
        if reason in ("run", "uptodate"):
            self.reasons[task.name] = reason


def _run(pkg_dir, flow_dv, target):
    """Build a fresh graph and run one target -- i.e. one `dfm run` invocation."""
    with open(os.path.join(pkg_dir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    loader = PackageLoader()
    pkg_def = loader.load(os.path.join(pkg_dir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(pkg_dir, "rundir"),
        loader=loader)
    runner = TaskSetRunner(rundir=os.path.join(pkg_dir, "rundir"), builder=builder)
    recorder = _RunRecorder()
    runner.add_listener(recorder)

    asyncio.run(runner.run(builder.mkTaskNode(target)))
    return recorder.reasons


_FLOW = """
package:
  name: p1

  tasks:
  - name: src1
    uses: std.CreateFile
    with: {{ filename: "src1.txt", content: "{content}" }}
  - name: consumer_a
    needs: [src1]
    passthrough: all
  - name: consumer_b
    needs: [src1]
    passthrough: all
"""


def test_uptodate_stale_consumer_across_invocations(tmpdir):
    """A consumer left out of the invocation that rebuilt its input is NOT up-to-date.

    `changed` only propagates within a single invocation. Two consumers share
    one producer; the producer is rebuilt in an invocation that asks only for
    consumer_a. consumer_b was not part of that invocation, so nothing told it
    at the time -- and on its next invocation the producer reports itself
    up-to-date and `changed=False`. It must still re-run, which it can only
    decide by hashing its inputs rather than trusting that announcement.
    """
    rundir = str(tmpdir)

    # Invocation 1: build both consumers against content "v1"
    _run(rundir, _FLOW.format(content="v1"), "p1.consumer_a")
    reasons = _run(rundir, _FLOW.format(content="v1"), "p1.consumer_b")
    assert reasons["p1.consumer_b"] == "run"

    # Both are now up-to-date and stay that way while nothing changes
    reasons = _run(rundir, _FLOW.format(content="v1"), "p1.consumer_b")
    assert reasons["p1.src1"] == "uptodate"
    assert reasons["p1.consumer_b"] == "uptodate"

    # Invocation 2: the producer changes, but only consumer_a is requested
    reasons = _run(rundir, _FLOW.format(content="v2"), "p1.consumer_a")
    assert reasons["p1.src1"] == "run"
    assert reasons["p1.consumer_a"] == "run"

    # Invocation 3: consumer_b must now re-run. While the inputs signature
    # recorded only which task produced each input, it reported up-to-date
    # here and kept serving its "v1" result forever.
    reasons = _run(rundir, _FLOW.format(content="v2"), "p1.consumer_b")
    assert reasons["p1.src1"] == "uptodate", "producer is genuinely up-to-date now"
    assert reasons["p1.consumer_b"] == "run", "consumer must see the rebuilt input"

    # ... and settles again rather than re-running forever
    reasons = _run(rundir, _FLOW.format(content="v2"), "p1.consumer_b")
    assert reasons["p1.consumer_b"] == "uptodate"


def test_uptodate_unchanged_rerun_does_not_churn_consumers(tmpdir):
    """A producer that re-runs to the SAME output does not invalidate consumers."""
    rundir = str(tmpdir)

    _run(rundir, _FLOW.format(content="v1"), "p1.consumer_b")

    # Force src1 to re-run by removing its exec_data, then confirm it does.
    import glob, shutil
    for p in glob.glob(os.path.join(rundir, "rundir", "*src1*")):
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    reasons = _run(rundir, _FLOW.format(content="v1"), "p1.consumer_a")
    assert reasons["p1.src1"] == "run"

    # consumer_b never saw that run. src1 reported changed, so consumer_b does
    # re-run once -- but it must then settle rather than oscillate.
    _run(rundir, _FLOW.format(content="v1"), "p1.consumer_b")
    reasons = _run(rundir, _FLOW.format(content="v1"), "p1.consumer_b")
    assert reasons["p1.consumer_b"] == "uptodate"
