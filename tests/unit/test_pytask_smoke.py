import asyncio
import pytest
from typing import List, Union
import dataclasses as dc
import pydantic.dataclasses as pdc
from pydantic import BaseModel
from dv_flow.mgr.param import Param, ParamT
from dv_flow.mgr.task import Task
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, TaskParameterSet
from dv_flow.mgr.task_node import task as t_decorator
from dv_flow.mgr.task_node import task
from dv_flow.mgr.task_runner import SingleTaskRunner, TaskSetRunner


def test_smoke_1(tmpdir):

    @dc.dataclass
    class Params(object):
        p1 : str = None

    called = False

    @task(Params)
    async def MyTask(runner, input):
            nonlocal called
            called = True
            print("Hello from run")
            return TaskDataResult()

    task1 = MyTask(srcdir="srcdir", p1="p1")
    runner = SingleTaskRunner("rundir")

    result = asyncio.run(runner.run(task1))

    assert called

def test_smoke_2(tmpdir):

    @dc.dataclass
    class Params(object):
        p1 : str = None

    called = False
    @task(Params)
    async def MyTask(runner, input):
        nonlocal called
        called = True
        print("Hello from run")
        return TaskDataResult(
            markers=[TaskMarker(msg="testing", severity="info")]
        )

    task1 = MyTask(name="task1", srcdir="srcdir", p1="p1")
    runner = SingleTaskRunner("rundir")

    result = asyncio.run(runner.run(task1))

    assert called
    assert result is not None
    assert len(result.markers) == 1

def test_smoke_3(tmpdir):

    class Params(BaseModel):
        p1 : str = None

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult()

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult()

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            called.append(("MyTask3", input.params.p1))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="1")
    task2 = MyTask2(srcdir="srcdir", p1="2")
    task3 = MyTask3(srcdir="srcdir", p1="3", needs=[task1, task2])
    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[-1][0] == "MyTask3"
    assert called[-1][1] == "3"

def test_smoke_4(tmpdir):

    class Params(BaseModel):
        p1 : str = None

    class TaskData(TaskParameterSet):
        val : int = -1

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(val=1)]
            )

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(val=2)]
            )

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            called.append(("MyTask3", input.params.p1))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="1")
    task2 = MyTask2(srcdir="srcdir", p1="2")
    task3 = MyTask3(srcdir="srcdir", 
                    p1="${{ in | jq('[.[] .val]') }}", 
                    needs=[task1, task2])
    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[-1][0] == "MyTask3"
    assert called[-1][1] == "[1, 2]"

def test_smoke_5(tmpdir):

    class Params(BaseModel):
        p1 : ParamT[List[str]] = pdc.Field(default_factory=list)

    class TaskData(TaskParameterSet):
        files : ParamT[List[str]] = pdc.Field(default_factory=list)

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(files=["f1", "f2", "f3"])]
            )

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(files=["f4", "f5", "f6"])]
            )

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            called.append(("MyTask3", input.params.p1))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="1")
    task2 = MyTask2(srcdir="srcdir", p1="2")
    task3 = MyTask3(srcdir="srcdir", 
                    p1="${{ in | jq('[.[] .files]') | jq('flatten') }}", 
#                    p1="${{ in | jq('.[] .files') }}", 
                    needs=[task1, task2])
    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[-1][0] == "MyTask3"
    assert called[-1][1] == '["f1", "f2", "f3", "f4", "f5", "f6"]'

def test_smoke_6(tmpdir):

    class Params(BaseModel):
        p1 : ParamT[List[str]] = pdc.Field(default=["1","2"])

    class TaskData(TaskParameterSet):
        files : ParamT[List[str]] = pdc.Field(default_factory=list)

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(files=["f1", "f2", "f3"])]
            )

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(files=["f4", "f5", "f6"])]
            )

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            called.append(("MyTask3", input.params.p1))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="3")
    task2 = MyTask2(srcdir="srcdir", p1=Param(append=["4"]))
    task3 = MyTask3(srcdir="srcdir", 
                    p1="${{ in | jq('[.[] .files]') | jq('flatten') }}", 
#                    p1="${{ in | jq('.[] .files') }}", 
                    needs=[task1, task2])
    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[1][0] == "MyTask2"
    assert called[1][1] == ["1", "2", "4"]
    assert called[-1][0] == "MyTask3"
    assert called[-1][1] == '["f1", "f2", "f3", "f4", "f5", "f6"]'
