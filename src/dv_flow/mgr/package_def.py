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
import io
import os
import json
import yaml
import importlib
import logging
import sys
import pydantic
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List, Callable, Tuple, ClassVar, Union
from .fragment_def import FragmentDef
from .package import Package
from .package_import_spec import PackageImportSpec, PackageSpec
from .task_node import TaskNodeCtor, TaskNodeCtorProxy, TaskNodeCtorTask
from .task_ctor import TaskCtor
from .task_def import TaskDef, TaskSpec
from .std.task_null import TaskNull, TaskNullParams
from .type_def import TypeDef


class PackageDef(BaseModel):
    name : str
    params : Dict[str,Any] = dc.Field(default_factory=dict)
    type : List[PackageSpec] = dc.Field(default_factory=list)
    tasks : List[TaskDef] = dc.Field(default_factory=list)
    imports : List[Union[str,PackageImportSpec]] = dc.Field(default_factory=list)
    fragments: List[str] = dc.Field(default_factory=list)
    types : List[TypeDef] = dc.Field(default_factory=list)

    fragment_l : List['FragmentDef'] = dc.Field(default_factory=list, exclude=True)
    subpkg_m : Dict[str,'PackageDef'] = dc.Field(default_factory=dict, exclude=True)

#    import_m : Dict['PackageSpec','Package'] = dc.Field(default_factory=dict)

    basedir : str = None
    _log : ClassVar = logging.getLogger("PackageDef")

    def __post_init__(self):
        for t in self.tasks:
            t.fullname = self.name + "." + t.name

    def getTask(self, name : str) -> 'TaskDef':
        for t in self.tasks:
            if t.name == name:
                return t
    
    def mkPackage(self, session, params : Dict[str,Any] = None) -> 'Package':
        self._log.debug("--> mkPackage %s" % self.name)
        ret = Package(self.name)

        session.push_package(ret, add=True)

        tasks_m : Dict[str,str,TaskCtor]= {}

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
            fullname = self.name + "." + name
            if len(task_i) < 3:
                # Need to create the task ctor
                ctor_t = self.mkTaskCtor(session, task_i[0], task_i[1], tasks_m)
                tasks_m[name] = (task_i[0], task_i[1], ctor_t)
            ret.tasks[name] = tasks_m[name][2]
            ret.tasks[fullname] = tasks_m[name][2]

        session.pop_package(ret)

        self._log.debug("<-- mkPackage %s" % self.name)
        return ret
    
    def getTaskCtor(self, session, task_name, tasks_m):
        self._log.debug("--> getTaskCtor %s" % task_name)
        # Find package (not package_def) that implements this task
        # Insert an indirect reference to that tasks's constructor
        last_dot = task_name.rfind('.')

        if last_dot != -1:
            pkg_name = task_name[:last_dot]
            task_name = task_name[last_dot+1:]
        else:
            pkg_name = None

        if pkg_name is not None:
            self._log.debug("Package-qualified 'uses'")
            pkg = session.getPackage(PackageSpec(pkg_name))
            if pkg is None:
                raise Exception("Failed to find package %s" % pkg_name)
            ctor_t = pkg.getTaskCtor(task_name)
        else:
            self._log.debug("Unqualified 'uses'")
            if task_name not in tasks_m.keys():
                raise Exception("Failed to find task %s" % task_name)
            if len(tasks_m[task_name]) != 3:
                raise Exception("Task %s not fully defined" % task_name)

            ctor_t = tasks_m[task_name][2]
        return ctor_t

    def mkTaskCtor(self, session, task, srcdir, tasks_m) -> TaskCtor:
        self._log.debug("--> %s::mkTaskCtor %s (srcdir: %s)" % (self.name, task.name, srcdir))
        base_ctor_t : TaskCtor = None
        ctor_t : TaskCtor = None
        base_params : BaseModel = None
        callable = None
        passthrough = task.passthrough
        consumes = task.consumes
        needs = [] if task.needs is None else task.needs.copy()

        if task.uses is not None:
            self._log.debug("Uses: %s" % task.uses)
            base_ctor_t = self.getTaskCtor(session, task.uses, tasks_m)
            base_params = base_ctor_t.mkTaskParams()

            if base_ctor_t is None:
                self._log.error("Failed to load task ctor %s" % task.uses)
        else:
            self._log.debug("No 'uses' specified")

        # Determine the implementation constructor first
        if task.pytask is not None:
            # Built-in impl
            # Now, lookup the class
            self._log.debug("Use PyTask implementation")
            last_dot = task.pytask.rfind('.')
            clsname = task.pytask[last_dot+1:]
            modname = task.pytask[:last_dot]

            try:
                if modname not in sys.modules:
                    if self.basedir not in sys.path:
                        sys.path.append(self.basedir)
                    mod = importlib.import_module(modname)
                else:
                    mod = sys.modules[modname]
            except ModuleNotFoundError as e:
                raise Exception("Failed to import module %s (basedir=%s): %s" % (
                    modname, self.basedir, str(e)))
                
            if not hasattr(mod, clsname):
                raise Exception("Method %s not found in module %s" % (clsname, modname))
            callable = getattr(mod, clsname)

        # Determine if we need to use a new 
        paramT = self._getParamT(session, task, base_params)
        
        if callable is not None:
            ctor_t = TaskNodeCtorTask(
                name=task.name,
                srcdir=srcdir,
                paramT=paramT, # TODO: need to determine the parameter type
                passthrough=passthrough,
                consumes=consumes,
                needs=needs, # TODO: need to determine the needs
                task=callable)
        elif base_ctor_t is not None:
            # Use the existing (base) to create the implementation
            ctor_t = TaskNodeCtorProxy(
                name=task.name,
                srcdir=srcdir,
                paramT=paramT, # TODO: need to determine the parameter type
                passthrough=passthrough,
                consumes=consumes,
                needs=needs,
                uses=base_ctor_t)
        else:
            self._log.debug("Use 'Null' as the class implementation")
            ctor_t = TaskNodeCtorTask(
                name=task.name,
                srcdir=srcdir,
                paramT=paramT,
                passthrough=passthrough,
                consumes=consumes,
                needs=needs,
                task=TaskNull)

        self._log.debug("<-- %s::mkTaskCtor %s" % (self.name, task.name))
        return ctor_t
    
    def _getParamT(self, session, task, base_t : BaseModel):
        self._log.debug("--> _getParamT %s" % task.fullname)
        # Get the base parameter type (if available)
        # We will build a new type with updated fields

        ptype_m = {
            "str" : str,
            "int" : int,
            "float" : float,
            "bool" : bool,
            "list" : List
        }
        pdflt_m = {
            "str" : "",
            "int" : 0,
            "float" : 0.0,
            "bool" : False,
            "list" : []
        }

        fields = []
        field_m : Dict[str,int] = {}

        pkg = session.package()

        # First, pull out existing fields (if there's a base type)
        if base_t is not None:
            self._log.debug("Base type: %s" % str(base_t))
            for name,f in base_t.model_fields.items():
                ff : dc.Field = f
                fields.append(f)
                field_m[name] = (f.annotation, getattr(base_t, name))
        else:
            self._log.debug("No base type")

        for p in task.params.keys():
            param = task.params[p]
            self._log.debug("param: %s %s (%s)" % (p, str(param), str(type(param))))
            if hasattr(param, "type") and param.type is not None:
                ptype_s = param.type
                if ptype_s not in ptype_m.keys():
                    raise Exception("Unknown type %s" % ptype_s)
                ptype = ptype_m[ptype_s]

                if p in field_m.keys():
                    raise Exception("Duplicate field %s" % p)
                if param.value is not None:
                    field_m[p] = (ptype, param.value)
                else:
                    field_m[p] = (ptype, pdflt_m[ptype_s])
                self._log.debug("Set param=%s to %s" % (p, str(field_m[p][1])))
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
                self._log.debug("Set param=%s to %s" % (p, str(field_m[p][1])))

        params_t = pydantic.create_model("Task%sParams" % task.name, **field_m)

        self._log.debug("== Params")
        for name,info in params_t.model_fields.items():
            self._log.debug("  %s: %s" % (name, str(info)))

        self._log.debug("<-- _getParamT %s" % task.name)
        return params_t

    @classmethod
    def load(cls, path, exp_pkg_name=None):
        return PackageDef._loadPkgDef(path, exp_pkg_name, [])
        pass

    @classmethod
    def _loadPkgDef(cls, root, exp_pkg_name, file_s):
        if root in file_s:
            raise Exception("Recursive file processing @ %s: %s" % (root, ",".join(file_s)))
        file_s.append(root)
        ret = None
        with open(root, "r") as fp:
            PackageDef._log.debug("open %s" % root)
            doc = yaml.load(fp, Loader=yaml.FullLoader)
            if "package" not in doc.keys():
                raise Exception("Missing 'package' key in %s" % root)
            try:
                pkg = PackageDef(**(doc["package"]))

                for t in pkg.tasks:
                    t.fullname = pkg.name + "." + t.name

            except Exception as e:
                PackageDef._log.error("Failed to load package from %s" % root)
                raise e
            pkg.basedir = os.path.dirname(root)

#            for t in pkg.tasks:
#                t.basedir = os.path.dirname(root)

        if exp_pkg_name is not None:
            if exp_pkg_name != pkg.name:
                raise Exception("Package name mismatch: %s != %s" % (exp_pkg_name, pkg.name))
            # else:
            #     self._pkg_m[exp_pkg_name] = [PackageSpec(pkg.name)
            #     self._pkg_spec_s.append(PackageSpec(pkg.name))

        # if not len(self._pkg_spec_s):
        #     self._pkg_spec_s.append(PackageSpec(pkg.name))
        # else:
        # self._pkg_def_m[PackageSpec(pkg.name)] = pkg

        for spec in pkg.fragments:
            PackageDef._loadFragmentSpec(pkg, spec, file_s)

        if len(pkg.imports) > 0:
            cls._log.info("Loading imported packages (basedir=%s)" % pkg.basedir)
        for imp in pkg.imports:
            if type(imp) == str:
                imp_path = imp
            elif imp.path is not None:
                imp_path = imp.path
            else:
                raise Exception("imp.path is none: %s" % str(imp))
            
            cls._log.info("Loading imported package %s" % imp_path)

            if not os.path.isabs(imp_path):
                cls._log.debug("basedir: %s ; imp_path: %s" % (pkg.basedir, imp_path))
                imp_path = os.path.join(pkg.basedir, imp_path)
            if os.path.isdir(imp_path) and os.path.isfile(os.path.join(imp_path, "flow.dv")):
                imp_path = os.path.join(imp_path, "flow.dv")
            if not os.path.isfile(imp_path):
                raise Exception("Import file %s not found" % imp_path)

            cls._log.info("Loading file %s" % imp_path)
                
            sub_pkg = PackageDef.load(imp_path)
            cls._log.info("Loaded imported package %s" % sub_pkg.name)
            pkg.subpkg_m[sub_pkg.name] = sub_pkg

        file_s.pop()

        return pkg

    @staticmethod
    def loads(data, exp_pkg_name=None):
        return PackageDef._loadPkgDefS(data, exp_pkg_name)
        pass

    @staticmethod
    def _loadPkgDefS(data, exp_pkg_name):
        ret = None
        doc = yaml.load(io.StringIO(data), Loader=yaml.FullLoader)
        if "package" not in doc.keys():
            raise Exception("Missing 'package' key in %s" % root)
        pkg = PackageDef(**(doc["package"]))
        pkg.basedir = None

#            for t in pkg.tasks:
#                t.basedir = os.path.dirname(root)

        if exp_pkg_name is not None:
            if exp_pkg_name != pkg.name:
                raise Exception("Package name mismatch: %s != %s" % (exp_pkg_name, pkg.name))

        if len(pkg.fragments) > 0:
            raise Exception("Cannot load a package-def with fragments from a string")

        return pkg
    
    @staticmethod
    def _loadFragmentSpec(pkg, spec, file_s):
        # We're either going to have:
        # - File path
        # - Directory path

        if os.path.isfile(os.path.join(pkg.basedir, spec)):
            PackageDef._loadFragmentFile(pkg, spec, file_s)
        elif os.path.isdir(os.path.join(pkg.basedir, spec)):
            PackageDef._loadFragmentDir(pkg, os.path.join(pkg.basedir, spec), file_s)
        else:
            raise Exception("Fragment spec %s not found" % spec)

    @staticmethod
    def _loadFragmentDir(pkg, dir, file_s):
        for file in os.listdir(dir):
            if os.path.isdir(os.path.join(dir, file)):
                PackageDef._loadFragmentDir(pkg, os.path.join(dir, file), file_s)
            elif os.path.isfile(os.path.join(dir, file)) and file == "flow.dv":
                PackageDef._loadFragmentFile(pkg, os.path.join(dir, file), file_s)

    @staticmethod
    def _loadFragmentFile(pkg, file, file_s):
        if file in file_s:
            raise Exception("Recursive file processing @ %s: %s" % (file, ", ".join(file_s)))
        file_s.append(file)

        with open(file, "r") as fp:
            doc = yaml.load(fp, Loader=yaml.FullLoader)
            PackageDef._log.debug("doc: %s" % str(doc))
            if "fragment" in doc.keys():
                # Merge the package definition
                frag = FragmentDef(**(doc["fragment"]))
                frag.basedir = os.path.dirname(file)
                pkg.fragment_l.append(frag)
            else:
                print("Warning: file %s is not a fragment" % file)
