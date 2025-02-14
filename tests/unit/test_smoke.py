import asyncio
import io
import os
import dataclasses as dc
import pytest
import jq
from typing import List
import yaml
from dv_flow.mgr import FileSet, PackageDef, TaskData, TaskGraphBuilder
from pydantic import BaseModel
from shutil import copytree

def test_smoke_1():
    flowdv = """
package:
    name: my_pkg

    tasks:
    - name: entry
      with:
      - name: p1
        type: int
      - name: p2
        type: int
"""

    pkg_def = PackageDef.loads(flowdv)
    builder = TaskGraphBuilder(pkg_def, os.getcwd())
    task = builder.mkTaskGraph("my_pkg.entry")

def test_jq():
    data = [
        {
            "type": "FileSet",
            "kind": "systemVerilogSource"
        },
        {
            "type": "FileSet",
            "kind": "vhdlSource"
        },
        {
            "type": "FileSet",
            "kind": "verilogSource"
        }
    ]

    result = jq.compile(""".[] | 
                        select(
                            .kind == "systemVerilogSource" 
                            or .kind == "verilogSource")
                        """).input(data).all()
    value = """
    with:
    - name: files
      list-append: |
      ${{ 
      in | jq('.[] | select(
        .kind == "systemVerilogSource" 
        or .kind == "verilogSource")')
      }}
"""
    print("result: %s" % str(result))



# def test_smoke():
#     file = """
# package:
#     name: my_pkg
# """

#     data = yaml.load(io.StringIO(file), Loader=yaml.FullLoader)
#     print("data: %s" % str(data))

#     file = PackageDef(**(data["package"]))

# def test_smoke_2():
#     file = """
# package:
#     name: my_pkg
#     tasks:
#     - name: my_task
#       type: my_type
#     - name: my_task2
#       depends: 
#       - my_task
#     import:
#       - name: hdl.sim.vcs
#         as: hdl.sim
# """

#     data = yaml.load(io.StringIO(file), Loader=yaml.FullLoader)
#     print("data: %s" % str(data))

#     file = Package(**(data["package"]))

#     print("file: %s" % str(file))

#     print("Schema: %s" % str(Package.model_json_schema()))

# def test_smoke_3(tmpdir):
#     datadir = os.path.join(os.path.dirname(__file__), "data")

#     copytree(
#         os.path.join(datadir, "proj1"), 
#         os.path.join(tmpdir, "proj1"))
    
#     class HelloTask(TaskImpl):

#         async def run(self):
#             print("Hello: %s" % self.spec.msg)

#     session = Session()
#     session.addImpl("SayHello", HelloTask)
#     session.load(os.path.join(tmpdir, "proj1"))

#     asyncio.run(session.run("proj1.hello"))

# def test_smoke_4(tmpdir):
#     datadir = os.path.join(os.path.dirname(__file__), "data")

#     copytree(
#         os.path.join(datadir, "proj2"), 
#         os.path.join(tmpdir, "proj2"))
    
#     class FileSetTask(TaskImpl):
        
#         async def run(self) -> TaskData:
#             fs = FileSet(
#                 src=self.spec, 
#                 type="systemVerilogSource", 
#                 basedir=self.spec.basedir)
#             fs.files.extend(self.spec.getField("paths"))
#             data = TaskData(filesets=[fs])
#             print("Spec: %s" % self.spec.name)
#             await asyncio.sleep(1)
#             print("FileSet: %s" % str(self.spec.getField("paths")))
#             return data
    
#     class HelloTask(TaskImpl):

#         async def run(self):
#             print("HelloTask")
#             for d in self.deps:
#                 print("Hello: %s" % str(d.output))

#             print("Hello: %s" % self.spec.msg)

#     session = Session()
#     session.addImpl("SayHello", HelloTask)
#     session.addImpl("FileSet", FileSetTask)
#     session.load(os.path.join(tmpdir, "proj2"))

#     asyncio.run(session.run("proj2.hello"))


# def test_smoke_5(tmpdir):
#     datadir = os.path.join(os.path.dirname(__file__), "data")

#     copytree(
#         os.path.join(datadir, "proj3"),
#         os.path.join(tmpdir, "proj3"))
    
#     class Test(PackageDef):
#         pass
    
#     class FileSetTask(TaskImpl):
        
#         async def run(self) -> TaskData:
#             fs = FileSet(
#                 src=self.spec, 
#                 type="systemVerilogSource", 
#                 basedir=self.spec.basedir)
#             fs.files.extend(self.spec.getField("paths"))
#             data = TaskData(filesets=[fs])
#             print("Spec: %s" % self.spec.name, flush=True)
#             if self.spec.name == "files1":
#                 await asyncio.sleep(1)
#             else:
#                 await asyncio.sleep(2)
#             print("FileSet: %s" % str(self.spec.getField("paths")))
#             return data
    
#     class HelloTask(TaskImpl):

#         async def run(self):
#             print("HelloTask")
#             for d in self.deps:
#                 print("Hello: %s" % str(d.getOutput()))

#             print("Hello: %s" % self.spec.msg)

#     session = Session()
#     session.addPackageDef()
#     session.addImpl("SayHello", HelloTask)
#     session.addImpl("FileSet", FileSetTask)
#     session.load(os.path.join(tmpdir, "proj3"))

#     asyncio.run(session.run("proj3.hello"))
