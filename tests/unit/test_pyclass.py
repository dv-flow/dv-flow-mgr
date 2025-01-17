
import os
import asyncio
import pytest
from dv_flow_mgr import TaskData
from dv_flow_mgr.tasklib.builtin_pkg import TaskPyClass, TaskPyClassParams

def test_smoke(tmpdir):
    module = """
from dv_flow_mgr import Task, TaskData

class foo(Task):

    async def run(self, input : TaskData) -> TaskData:
        print("foo::run", flush=True)
        return input
"""
    print("test_smoke")

    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(module)

    params = TaskPyClassParams(pyclass="my_module.foo")
    basedir = os.path.join(tmpdir)
    task = TaskPyClass("t1", -1, None, params, basedir, srcdir=basedir)

    in_data = TaskData()
    asyncio.run(task.run(in_data))
    pass