import asyncio
import pytest
from typing import List, Union
import dataclasses as dc
import pydantic.dataclasses as pdc
from pydantic import BaseModel
from dv_flow.mgr.param import Param, ParamT
from dv_flow.mgr.task_data import TaskDataResult, TaskMarker, TaskDataItem
from dv_flow.mgr import task
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

    task1 = MyTask(name="task1", srcdir="srcdir", p1="p1")
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

    class TaskData(TaskDataItem):
        val : int = -1

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(type="foo", src=input.name, id="bar", val=1)]
            )

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(type="foo", src=input.name, id="bar", val=2)]
            )

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            called.append(("MyTask3", [o.val for o in input.inputs]))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="1")
    task2 = MyTask2(srcdir="srcdir", p1="2")
    task3 = MyTask3(srcdir="srcdir", needs=[task1, task2])

    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[-1][0] == "MyTask3"
    assert called[-1][1] == [1, 2] or called[-1][1] == [2, 1]

def test_smoke_5(tmpdir):

    class Params(BaseModel):
        p1 : ParamT[List[str]] = pdc.Field(default_factory=list)

    class TaskData(TaskDataItem):
        files : ParamT[List[str]] = pdc.Field(default_factory=list)

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(src=input.name, type="foo", id="bar", files=["f1", "f2", "f3"])]
            )

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(src=input.name, type="foo", id="bar", files=["f4", "f5", "f6"])]
            )

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            files = []
            for inp in input.inputs:
                  files.extend(inp.files)
            called.append(("MyTask3", files))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="1")
    task2 = MyTask2(srcdir="srcdir", p1="2")
    task3 = MyTask3(srcdir="srcdir", needs=[task1, task2])
    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[-1][0] == "MyTask3"
    for it in ["f1", "f2", "f3", "f4", "f5", "f6"]:
        assert it in called[-1][1]

def test_smoke_6(tmpdir):

    class Params(BaseModel):
        p1 : ParamT[List[str]] = pdc.Field(default=["1","2"])

    class TaskData(TaskDataItem):
        files : ParamT[List[str]] = pdc.Field(default_factory=list)

    called = []

    @task(Params)
    async def MyTask1(runner, input):
            nonlocal called
            called.append(("MyTask1", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(src=input.name, type="foo", id="bar", files=["f1", "f2", "f3"])]
            )

    @task(Params)
    async def MyTask2(runner, input):
            nonlocal called
            called.append(("MyTask2", input.params.p1))
            return TaskDataResult(
                  output=[TaskData(src=input.name, type="foo", id="bar", files=["f4", "f5", "f6"])]
            )

    @task(Params)
    async def MyTask3(runner, input):
            nonlocal called
            files = []
            for inp in input.inputs:
                  files.extend(inp.files)
            called.append(("MyTask3", files))
            return TaskDataResult()

    task1 = MyTask1(srcdir="srcdir", p1="3")
    task2 = MyTask2(srcdir="srcdir", p1=Param(append=["4"]))
    task3 = MyTask3(srcdir="srcdir", needs=[task1, task2])
    runner = TaskSetRunner("rundir")

    result = asyncio.run(runner.run(task3))

    assert len(called) == 3
    assert called[1][0] == "MyTask2"
    for it in ["1", "2", "4"]:
        assert it in called[1][1]
    assert called[-1][0] == "MyTask3"
    for it in ["f1", "f2", "f3", "f4", "f5", "f6"]:
        assert it in called[-1][1]

def test_compound_node(tmpdir):
    import sys
    import os
    import site
    import asyncio
    import subprocess
    import pydantic.dataclasses as pdc

    with open(os.path.join(tmpdir, "file1.c"), "w") as fp:
        fp.write("")

    with open(os.path.join(tmpdir, "file2.c"), "w") as fp:
        fp.write("")

    with open(os.path.join(tmpdir, "file3.c"), "w") as fp:
        fp.write("int main() { }")
    
    # # Ensure user site-packages are available (for --user installs)
    # user_site = site.getusersitepackages()
    # if user_site not in sys.path:
    #     sys.path.insert(0, user_site)
    
    # # Insert the absolute path to 'src' into sys.path
    # src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
    # if src_path not in sys.path:
    #     sys.path.insert(0, src_path)
    
    from dv_flow.mgr import task, FileSet
    from dv_flow.mgr.task_gen_ctxt import TaskGenCtxt
    from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
    from dv_flow.mgr.task_node_compound import TaskNodeCompound
    from dv_flow.mgr.task_node_ctxt import TaskNodeCtxt
    from dv_flow.mgr.task_runner import TaskSetRunner
    from dv_flow.mgr.task_data import TaskDataInput, TaskDataResult, TaskDataItem
    from dv_flow.mgr.task_def import PassthroughE, ConsumesE

    srcdir = os.path.join(tmpdir)
    rundir = os.path.join(tmpdir, "rundir")
    
    @pdc.dataclass
    class CompileParams:
        # Params objects must have default values
        src: str = pdc.Field(default="")
        obj: str = pdc.Field(default="")
    
    @pdc.dataclass
    class LinkParams:
        objects : list = pdc.Field(default_factory=list)
        exe: str = pdc.Field(default="")

    # I'd use the built-in fileset type for both of these    
    # class ObjectFile(TaskDataItem):
    #     type: str
    #     obj: str
    
    # class ExecutableFile(TaskDataItem):
    #     type: str
    #     exe: str

    @task(CompileParams)
    async def compile_task(run_ctxt, input: TaskDataInput):
        src = input.params.src
        obj = input.params.obj
        rundir = input.rundir
        src = input.srcdir
        print(f"Compiling {src} -> {obj} (cwd={rundir})")
        result = subprocess.run(["gcc", "-c", src, "-o", obj], capture_output=True, text=True, cwd=rundir)
        if result.returncode != 0:
            print(result.stderr)
            raise Exception(f"Compilation failed for {src}")
        # Output object file info
        output_item = FileSet(
             filetype="objFile",
             basedir=input.rundir,
             files=[obj])
        print(f"DEBUG: compile_task output_item = {output_item}, dict = {output_item.__dict__}")
        return TaskDataResult(
            status=0,
            changed=True,
            output=[output_item],
            markers=[],
            memento=None
        )

    @task(LinkParams)    
    async def link_task(run_ctxt, input: TaskDataInput):
        print(f"DEBUG: link input.inputs = {input.inputs}")
        # print(f"DEBUG: link ctx input.inputs = {run_ctxt.getInputs()}")
        obj_files = []
        for i, item in enumerate(input.inputs):
            print(f"DEBUG: link input.inputs[{i}] type={type(item)}, dict={getattr(item, '__dict__', str(item))}")
            for file in item.files:
                 obj_files.append(os.path.join(item.basedir, file))
        
#        obj_files = [getattr(item, "obj", None) for item in input.inputs]
        exe_file = input.params.exe
        rundir = input.srcdir
        print(f"Linking {obj_files} -> {exe_file} (cwd={rundir})")
        result = subprocess.run(["gcc"] + obj_files + ["-o", exe_file], capture_output=True, text=True, cwd=rundir)
        if result.returncode != 0:
            print(result.stderr)
            raise Exception("Linking failed")
        output_item = ExecutableFile(type="executable", exe=exe_file)
        return TaskDataResult(
            status=0,
            changed=True,
            output=[output_item],
            markers=[],
            memento=None
        )
    
#    rundir = os.path.dirname(__file__)
#    ctxt = TaskNodeCtxt(root_pkgdir="", root_rundir=rundir, env={})
    
    sources = ["file1.c", "file2.c", "file3.c"]
    objects = [src.replace(".c", ".o") for src in sources]
    compile_nodes = []
    for src, obj in zip(sources, objects):
        node = compile_task(
            name=f"compile_{src}",
            srcdir=srcdir,
#            rundir=os.path.join(rundir, f"compile_{src}"),
            # Values for task parameters as passed through as kwargs
            src=src,
            obj=obj)
        compile_nodes.append(node)
    
    # Linking task depends directly on the three compilation tasks
    link_node = link_task(
         name="link", 
         srcdir=srcdir, 
         needs=compile_nodes,
        rundir=os.path.join(rundir, f"compile_{src}"))

    # link_node = TaskNodeLeaf(
    #     name="link",
    #     srcdir=rundir,
    #     params=LinkParams(objects=objects, exe="a.out"),
    #     ctxt=ctxt,
    #     task=link_task,
    #     needs=compile_nodes # [(compound_node, False)] #(compound_node, False) for node in compile_nodes]
    # )
    
    
    runner = TaskSetRunner(rundir=rundir)
    # Only need to run the terminal node. 
    asyncio.run(runner.run([link_node]))

    assert runner.status == 0
   
    print("Build completed. Run './a.out' to execute.")
    
    pass
    