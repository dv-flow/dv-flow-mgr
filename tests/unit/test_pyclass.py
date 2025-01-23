
import os
import asyncio
import pytest
from dv_flow.mgr import TaskGraphBuilder, TaskGraphRunnerLocal, PackageDef
#from dv_flow_mgr.tasklib.builtin_pkg import TaskPyClass, TaskPyClassParams

# def test_smoke(tmpdir):
#     module = """
# from dv_flow_mgr import Task, TaskData

# class foo(Task):

#     async def run(self, input : TaskData) -> TaskData:
#         print("foo::run", flush=True)
#         return input
# """
#     print("test_smoke")

#     with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
#         f.write(module)

#     params = TaskPyClassParams(pyclass="my_module.foo")
#     basedir = os.path.join(tmpdir)
#     task = TaskPyClass("t1", -1, None, params, basedir, srcdir=basedir)

#     in_data = TaskData()
#     out_data = asyncio.run(task.run(in_data))

#     assert in_data is out_data

def test_class_load(tmpdir):
    # Test that we can 
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    pyclass: my_module.foo
    with:
      param1:
        type: str
        value: "1"
"""
    module = """
from dv_flow.mgr import Task, TaskData

class foo(Task):
    async def run(self, input : TaskData) -> TaskData:
        print("foo::run", flush=True)
        print("params: %s" % str(self.params), flush=True)
        return input
"""

    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(module)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    rundir = os.path.join(tmpdir, "rundir")
    pkg_def = PackageDef.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskGraphRunnerLocal(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskGraph("pkg1.foo")
    output = asyncio.run(runner.run(task))


def test_class_use(tmpdir):
    # Test that we can 
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    pyclass: my_module.foo
    with:
      param1:
        type: str
        value: "1"
  - name: foo2
    uses: foo
"""
    module = """
from dv_flow.mgr import Task, TaskData

class foo(Task):
    async def run(self, input : TaskData) -> TaskData:
        print("foo::run", flush=True)
        print("params: %s" % str(self.params), flush=True)
        return input
"""

    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(module)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    pkg_def = PackageDef.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskGraphRunnerLocal(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskGraph("pkg1.foo2")
    output = asyncio.run(runner.run(task))

def test_class_use_with(tmpdir):
    # Test that we can 
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    pyclass: my_module.foo
    with:
      param1:
        type: str
        value: "1"
  - name: foo2
    uses: foo
    with:
      param1: "2"

"""
    module = """
from dv_flow.mgr import Task, TaskData

class foo(Task):
    async def run(self, input : TaskData) -> TaskData:
        print("foo::run", flush=True)
        print("params: %s" % str(self.params), flush=True)
        return input
"""

    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(module)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    pkg_def = PackageDef.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskGraphRunnerLocal(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskGraph("pkg1.foo")
    output = asyncio.run(runner.run(task))

def test_class_use_with_new_param(tmpdir):
    # Test that we can 
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    pyclass: my_module.foo
    with:
      param1:
        type: str
        value: "1"
  - name: foo2
    uses: foo
    with:
      param1: "2"
      param2:
        type: str
        value: "3"

"""
    module = """
from dv_flow.mgr import Task, TaskData

class foo(Task):
    async def run(self, input : TaskData) -> TaskData:
        print("foo::run", flush=True)
        print("params: %s" % str(self.params), flush=True)
        return input
"""

    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(module)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    pkg_def = PackageDef.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskGraphRunnerLocal(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskGraph("pkg1.foo2")
    output = asyncio.run(runner.run(task))

def test_broad_parallel(tmpdir):
    # Test that we can 
    flow = """
package:
  name: pkg1
  tasks:
  - name: foo
    pyclass: my_module.foo
    with:
      param1:
        type: str
        value: "1"
"""

    count = 1000

    for t in range(count):
        flow += "  - name: foo_%02d\n" % t
        flow += "    uses: foo\n"
        flow += "    with:\n"
        flow += "      param1: \"%d\"\n" % t
    flow += "  - name: final\n"
    flow += "    needs: [" + ",".join("foo_%02d" % t for t in range(count)) + "]\n"

    module = """
from dv_flow.mgr import Task, TaskData

class foo(Task):
    async def run(self, input : TaskData) -> TaskData:
        print("foo::run", flush=True)
        print("params: %s" % str(self.params), flush=True)
        return input
"""

    with open(os.path.join(tmpdir, "my_module.py"), "w") as f:
        f.write(module)
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(flow)

    pkg_def = PackageDef.load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(tmpdir, "rundir"))
    runner = TaskGraphRunnerLocal(rundir=os.path.join(tmpdir, "rundir"))

    task = builder.mkTaskGraph("pkg1.final")
    output = asyncio.run(runner.run(task))

