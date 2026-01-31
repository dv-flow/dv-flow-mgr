"""
Test that output items are validated to have non-empty type fields
"""
import os
import asyncio
import dataclasses as dc
import pytest
from dv_flow.mgr import task
from dv_flow.mgr.task_data import TaskDataResult
from dv_flow.mgr.task_runner import SingleTaskRunner
from pydantic import BaseModel

def test_output_without_type_field_rejected(tmpdir):
    """Test that outputs without a type field are rejected"""
    
    @dc.dataclass
    class Params(object):
        pass
    
    # Create an output item without a type field
    class BadOutput(BaseModel):
        value: str = "test"
    
    @task(Params)
    async def bad_task(ctxt, input):
        output = []
        bad_item = BadOutput(value="test")
        output.append(bad_item)
        return TaskDataResult(output=output)
    
    rundir = str(tmpdir)
    task1 = bad_task(name="bad_task", srcdir=rundir)
    runner = SingleTaskRunner(rundir)
    
    with pytest.raises(Exception) as exc_info:
        asyncio.run(runner.run(task1))
    
    assert "without a valid type field" in str(exc_info.value)

def test_output_with_empty_type_field_rejected(tmpdir):
    """Test that outputs with empty type field are rejected"""
    
    @dc.dataclass
    class Params(object):
        pass
    
    # Create an output item with an empty type field
    class BadOutput(BaseModel):
        type: str = ""
        value: str = "test"
    
    @task(Params)
    async def bad_task(ctxt, input):
        output = []
        bad_item = BadOutput(type="", value="test")
        output.append(bad_item)
        return TaskDataResult(output=output)
    
    rundir = str(tmpdir)
    task1 = bad_task(name="bad_task", srcdir=rundir)
    runner = SingleTaskRunner(rundir)
    
    with pytest.raises(Exception) as exc_info:
        asyncio.run(runner.run(task1))
    
    assert "without a valid type field" in str(exc_info.value)

def test_output_with_valid_type_field_accepted(tmpdir):
    """Test that outputs with valid type field are accepted"""
    
    @dc.dataclass
    class Params(object):
        pass
    
    # Create an output item with a valid type field
    class GoodOutput(BaseModel):
        type: str = "std.FileSet"
        value: str = "test"
    
    @task(Params)
    async def good_task(ctxt, input):
        output = []
        good_item = GoodOutput(type="std.CustomType", value="test")
        output.append(good_item)
        return TaskDataResult(output=output)
    
    rundir = str(tmpdir)
    task1 = good_task(name="good_task", srcdir=rundir)
    runner = SingleTaskRunner(rundir)
    
    # Should not raise an exception
    result = asyncio.run(runner.run(task1))
    assert result.status == 0
