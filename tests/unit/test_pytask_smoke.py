import asyncio
import pytest
import dataclasses as dc
from dv_flow.mgr.task import Task
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker
from dv_flow.mgr.task_runner import SingleTaskRunner


def test_smoke_1(tmpdir):

    @dc.dataclass
    class Params(object):
        p1 : str

    called = False
    @Task.ctor(Params)
    class MyTask(Task):
        async def run(self, runner, input):
            nonlocal called
            called = True
            print("Hello from run")
            pass

    task = MyTask("task1", "srcdir", MyTask.mkParams("p1"))
    runner = SingleTaskRunner("rundir")

    result = asyncio.run(runner.run(task))

    assert called

def test_smoke_2(tmpdir):

    @dc.dataclass
    class Params(object):
        p1 : str = None

    called = False
    @Task.ctor(Params)
    class MyTask(Task):
        async def run(self, runner, input):
            nonlocal called
            called = True
            print("Hello from run")
            return TaskDataResult(
                markers=[TaskMarker(msg="testing", severity="info")]
            )

    task = MyTask.mkTask("task1", "srcdir", MyTask.mkParams(
        p1="p1"
    ))
    runner = SingleTaskRunner("rundir")

    result = asyncio.run(runner.run(task))

    assert called
    assert result is not None
    assert len(result.markers) == 1


