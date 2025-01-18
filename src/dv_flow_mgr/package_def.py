#****************************************************************************
#* package_def.py
#*
#* Copyright 2023 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import json
import importlib
import sys
import pydantic
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List
from .flow import Flow
from .fragment_def import FragmentDef
from .package import Package
from .package_import_spec import PackageImportSpec, PackageSpec
from .task import TaskParamCtor, TaskCtorT, TaskParams
from .task_def import TaskDef, TaskSpec


class PackageDef(BaseModel):
    name : str
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    type : List[PackageSpec] = dc.Field(default_factory=list)
    tasks : List[TaskDef] = dc.Field(default_factory=list)
    imports : List[PackageImportSpec] = dc.Field(default_factory=list)
    fragments: List[str] = dc.Field(default_factory=list)

    fragment_l : List['FragmentDef'] = dc.Field(default_factory=list, exclude=True)

#    import_m : Dict['PackageSpec','Package'] = dc.Field(default_factory=dict)

    basedir : str = None

    def getTask(self, name : str) -> 'TaskDef':
        for t in self.tasks:
            if t.name == name:
                return t
    
    def mkPackage(self, session, params : Dict[str,Any] = None) -> 'Package':
        ret = Package(self.name)

        for task in self.tasks:
            if task.pyclass is not None:
                # This task provides a Python implementation
                # Our task is to create a TaskCtor that includes a 
                # parameters class and task class
                if task.uses is not None:
                    # Find the base for this task
                    ctor_t = session.getTaskCtor(task_t, self)
                else:
                    ctor_t = None
                    
                # Construct a composite set of parameters
                # - Merge parameters from the base (if any) with local
                field_m = {}
                print("task.params: %s" % str(task.params))
                ptype_m = {
                    "str" : str,
                    "int" : int,
                    "float" : float,
                    "bool" : bool
                }
                for p in task.params.keys():
                    param = task.params[p]
                    if "type" in param.keys():
                        ptype_s = param["type"]
                        if ptype_s not in ptype_m.keys():
                            raise Exception("Unknown type %s" % ptype_s)
                        ptype = ptype_m[ptype_s]

                        if p in field_m.keys():
                            raise Exception("Duplicate field %s" % p)
                        if "value" in param.keys():
                            field_m[p] = (ptype, param["value"])
                        else:
                            field_m[p] = (ptype, )
                    else:
                        if p not in field_m.keys():
                            raise Exception("Field %s not found" % p)
                        if "value" not in param.keys():
                            raise Exception("No value specified for param %p" % p)
                        field_m[p] = (field_m[p][0], params["value"])
                task_p = pydantic.create_model("Task%sParams" % task.name, **field_m)

                # Now, lookup the class
                last_dot = task.pyclass.rfind('.')
                clsname = task.pyclass[last_dot+1:]
                modname = task.pyclass[:last_dot]

                try:
                    if modname not in sys.modules:
                        if self.basedir not in sys.path:
                            sys.path.append(self.basedir)
                        mod = importlib.import_module(modname)
                    else:
                        mod = sys.modules[modname]
                except ModuleNotFoundError as e:
                    raise Exception("Failed to import module %s" % modname)
                
                if not hasattr(mod, clsname):
                    raise Exception("Class %s not found in module %s" % (clsname, modname))
                cls = getattr(mod, clsname)

                ctor_t = TaskCtorT(task_p, cls)
            elif task.uses is None:
                # We use the built-in Null task 
                pass
            else:
                    # Find package (not package_def) that implements this task
                    # Insert an indirect reference to that tasks's constructor

                    # Only call getTaskCtor if the task is in a different package
                    task_t = task.uses if isinstance(task.uses, TaskSpec) else TaskSpec(task.uses)
                    ctor_t = session.getTaskCtor(task_t, self)

                    ctor_t = TaskParamCtor(
                        base=ctor_t, 
                        params=task.params, 
                        basedir=self.basedir,
                        depend_refs=task.depends)
            ret.tasks[task.name] = ctor_t

        for frag in self.fragment_l:
            for task in frag.tasks:
                if task.uses is not None:
                    # Find package (not package_def) that implements this task
                    # Insert an indirect reference to that tasks's constructor

                    # Only call getTaskCtor if the task is in a different package
                    task_t = task.uses if isinstance(task.uses, TaskSpec) else TaskSpec(task.uses)
                    ctor_t = session.getTaskCtor(task_t, self)

                    ctor_t = TaskParamCtor(
                        base=ctor_t, 
                        params=task.params, 
                        basedir=frag.basedir,
                        depend_refs=task.depends)
                else:
                    # We use the Null task from the std package
                    raise Exception("")
                if task.name in ret.tasks:
                    raise Exception("Task %s already defined" % task.name)
                ret.tasks[task.name] = ctor_t

        return ret

