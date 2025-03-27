import asyncio
import pytest
from pydantic import BaseModel
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, TaskMarkerLoc
from dv_flow.mgr import task
from dv_flow.mgr.task_runner import TaskSetRunner
from dv_flow.mgr.task_listener_log import TaskListenerLog

def test_smoke_1(tmpdir):

    class Params(BaseModel):
        p1 : str = None

    called = False

    @task(Params)
    async def MyTask(runner, input):
            nonlocal called
            called = True
            print("Hello from run")
            return TaskDataResult(
                 status=1,
                 markers=[
                      TaskMarker(msg="testing", severity="info",
                      loc=TaskMarkerLoc(
                          path="file1",
                          line=1,
                          pos=1
                      ))
                 ]
            )

    task1 = MyTask("task1", srcdir="srcdir", p1="p1")
    runner = TaskSetRunner("rundir")
    runner.add_listener(TaskListenerLog().event)

    result = asyncio.run(runner.run(task1))

    assert called