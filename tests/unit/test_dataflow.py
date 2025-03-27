import asyncio
import io
import json
import os
import dataclasses as dc
import pytest
from typing import Any, List, Union
import yaml
from dv_flow.mgr import PackageDef, TaskGraphBuilder, TaskSetRunner, task, TaskDataResult
from dv_flow.mgr.fileset import FileSet
from pydantic import BaseModel
from shutil import copytree

def test_dual_outputs(tmpdir):

    class Params(BaseModel):
        pass

    @task(paramT=Params, passthrough=True)
    async def producer(runner, input) -> TaskDataResult:
        return TaskDataResult(
            output=[
                FileSet(filetype="verilogInclude", basedir="foo"),
                FileSet(filetype="simLib", basedir="bar")
            ])

    inputs = []
    @task(paramT=Params, passthrough=True,
          consumes=[
              {"type": "std.FileSet", "filetype": "verilogInclude"},
              {"type": "std.FileSet", "filetype": "simLib"}])
    async def consumer(runner, input) -> TaskDataResult:
        nonlocal inputs
        inputs.extend(input.inputs)
        return TaskDataResult()

    p = producer(srcdir="srcdir")
    c = consumer(srcdir="srcdir", needs=[p])

    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(c))

    print("input.inputs: %s" % str(inputs))
    
    assert len(inputs) == 2
    assert "verilogInclude" in [x.filetype for x in inputs]
    assert "simLib" in [x.filetype for x in inputs]

def test_dual_source(tmpdir):

    class Params(BaseModel):
        pass

    @task(paramT=Params, passthrough=True)
    async def producer(runner, input) -> TaskDataResult:
        return TaskDataResult(
            output=[
                FileSet(filetype="verilogInclude", basedir="foo"),
                FileSet(filetype="simLib", basedir="bar")
            ])

    @task(paramT=Params, passthrough=True)
    async def passthrough(runner, input) -> TaskDataResult:
        return TaskDataResult()

    inputs = []
    @task(paramT=Params, passthrough=True,
          consumes=[
              {"type": "std.FileSet", "filetype": "verilogInclude"},
              {"type": "std.FileSet", "filetype": "simLib"}])
    async def consumer(runner, input) -> TaskDataResult:
        nonlocal inputs
        inputs.extend(input.inputs)
        return TaskDataResult()

    p = producer(srcdir="srcdir")
    pt = passthrough(srcdir="srcdir", needs=[p])
    c = consumer(srcdir="srcdir", needs=[p, pt])

    runner = TaskSetRunner(rundir=os.path.join(tmpdir, "rundir"))

    out = asyncio.run(runner.run(c))

    print("input.inputs: %s" % str(inputs))
    
    assert len(inputs) == 2
    assert "verilogInclude" in [x.filetype for x in inputs]
    assert "simLib" in [x.filetype for x in inputs]


