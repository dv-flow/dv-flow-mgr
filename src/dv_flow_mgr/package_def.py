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
from typing import Any, Dict, List, Callable, Tuple
from .flow import Flow
from .fragment_def import FragmentDef
from .package import Package
from .package_import_spec import PackageImportSpec, PackageSpec
from .task import TaskCtor, TaskParams
from .task_def import TaskDef, TaskSpec
from .tasklib.builtin_pkg import TaskNull


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

        session.push_package(ret)

        tasks_m : Dict[str,TaskCtor]= {}

        for task in self.tasks:
            if task.name in tasks_m.keys():
                raise Exception("Duplicate task %s" % task.name)
            tasks_m[task.name] = (task, self.basedir, ) # We'll add a TaskCtor later

        for frag in self.fragment_l:
            for task in frag.tasks:
                if task.name in tasks_m.keys():
                    raise Exception("Duplicate task %s" % task.name)
                tasks_m[task.name] = (task, frag.basedir, ) # We'll add a TaskCtor later

        # Now we have a unified map of the tasks declared in this package
        for name in list(tasks_m.keys()):
            task_i = tasks_m[name]
            if len(task_i) < 3:
                # Need to create the task ctor
                ctor_t = self.mkTaskCtor(session, task_i[0], task_i[1], tasks_m)
                tasks_m[name] = (task_i[0], task_i[1], ctor_t)
            ret.tasks[name] = tasks_m[name][2]

        session.pop_package(ret)

        return ret
    
    def mkTaskCtor(self, session, task, basedir, tasks_m) -> TaskCtor:
        ctor_t : TaskCtor = None

        if task.uses is not None:
            # Find package (not package_def) that implements this task
            # Insert an indirect reference to that tasks's constructor
            last_dot = task.uses.rfind('.')

            if last_dot != -1:
                pkg_name = task.uses[:last_dot]
                task_name = task.uses[last_dot+1:]
            else:
                pkg_name = None
                task_name = task.uses

            if pkg_name is not None:
                pkg = session.getPackage(PackageSpec(pkg_name))
                if pkg is None:
                    raise Exception("Failed to find package %s" % pkg_name)
                ctor_t = pkg.getTaskCtor(task_name)
            else:
                if task_name not in tasks_m.keys():
                    raise Exception("Failed to find task %s" % task_name)
                if len(tasks_m[task_name]) == 3:
                    ctor_t = tasks_m[task_name][2]
                else:
                    task_i = tasks_m[task_name]
                    ctor_t = self.mkTaskCtor(session, task_i[0], task_i[1], tasks_m)
                    tasks_m[task_name] = ctor_t

        if ctor_t is None:
            # Provide a default implementation
            ctor_t = TaskCtor(
                task_ctor=TaskNull,
                param_ctor=TaskParams)

        if task.pyclass is not None:
            # Built-in impl
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
            ctor_t.task_ctor = getattr(mod, clsname)

            if task.uses is None:
                ctor_t.param_ctor = TaskParams

        decl_params = False
        for value in task.params.values():
            if "type" in value:
                decl_params = True
                break
        
        if decl_params:
            # We need to combine base parameters with new parameters
            field_m = {}
            # First, add parameters from the base class
            for fname,info in ctor_t.param_ctor.model_fields.items():
                print("Field: %s (%s)" % (fname, info.default))
                field_m[fname] = (info.annotation, info.default)
            ptype_m = {
                "str" : str,
                "int" : int,
                "float" : float,
                "bool" : bool
            }
            for p in task.params.keys():
                param = task.params[p]
                if type(param) == dict and "type" in param.keys():
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
                    if type(param) != dict:
                        value = param
                    elif "value" in param.keys():
                        value = param["value"]
                    else:
                        raise Exception("No value specified for param %s: %s" % (
                            p, str(param)))
                    field_m[p] = (field_m[p][0], value)
            print("field_m: %s" % str(field_m))
            ctor_t.param_ctor = pydantic.create_model(
                "Task%sParams" % task.name, **field_m)
        else:
            if len(task.params) > 0:
                ctor_t.params = task.params
            if len(task.depends) > 0:
                ctor_t.depends.extends(task.depends)

        return ctor_t

