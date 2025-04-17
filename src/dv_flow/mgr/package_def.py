#****************************************************************************
#* package_def.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
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
import dataclasses
import io
import json
import os
import yaml
import importlib
import logging
import sys
import pydantic
import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List, Callable, Tuple, ClassVar, Union
from .config_def import ConfigDef
from .fragment_def import FragmentDef
from .package_import_spec import PackageImportSpec, PackageSpec
from .param_def import ParamDef
from .srcinfo import SrcInfo
from .task_def import TaskDef
from .type_def import TypeDef


class PackageDef(BaseModel):
    name : str = dc.Field(
        description="Name of the package")
    type : List[PackageSpec] = dc.Field(default_factory=list)
    tasks : List[TaskDef] = dc.Field(
        default_factory=list,
        description="List of tasks defined in the package")
    imports : List[Union[str,PackageImportSpec]] = dc.Field(
        default_factory=list,
        description="List of packages to import")
    fragments: List[str] = dc.Field(
        default_factory=list,
        description="List of fragments to include")
    types : List[TypeDef] = dc.Field(default_factory=list)
    uses : str = dc.Field(
        default=None,
        description="Name of the package to use as a base")
    params : Dict[str,Union[str,list,ParamDef]] = dc.Field(
        default_factory=dict, alias="with",
        description="Package parameters")
    configs : List[ConfigDef] = dc.Field(
        default_factory=list,
        description="List of package configurations")
    srcinfo : SrcInfo = dc.Field(default=None)

#     @pydantic.model_validator(mode='before')
#     def filter_srcinfo(self, values):
#         print("pkg_def values: %s" % values)
# #        if values.get("srcinfo") is not None:
# #            values["srcinfo"] = values["srcinfo"].replace("\\", "/")
#         return self

    _fragment_l : List['FragmentDef'] = []
    _subpkg_m : Dict[str,'PackageDef'] = {}

#    import_m : Dict['PackageSpec','Package'] = dc.Field(default_factory=dict)

    _basedir : str = None
    _log : ClassVar = logging.getLogger("PackageDef")

    @property
    def fragment_l(self):
        return self._fragment_l
    
    @property
    def subpkg_m(self):
        return self._subpkg_m

    @property
    def basedir(self):
        return self._basedir
    
    @basedir.setter
    def basedir(self, v):
        self._basedir = v

    def __post_init__(self):
        self._fragment_l = []
        self._subpkg_m = {}
        for t in self.tasks:
            t.fullname = self.name + "." + t.name

    def getTask(self, name : str) -> 'TaskDef':
        for t in self.tasks:
            if t.name == name:
                return t
    
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


#     @classmethod
#     def load(cls, path, exp_pkg_name=None):
#         return PackageDef._loadPkgDef(path, exp_pkg_name, [])
#         pass


#     @staticmethod
#     def loads(data, exp_pkg_name=None):
#         return PackageDef._loadPkgDefS(data, exp_pkg_name)
#         pass

#     @staticmethod
#     def _loadPkgDefS(data, exp_pkg_name):
#         ret = None
#         doc = yaml.load(io.StringIO(data), Loader=yaml.FullLoader)
#         if "package" not in doc.keys():
#             raise Exception("Missing 'package' key in %s" % root)
#         pkg = PackageDef(**(doc["package"]))
#         pkg._basedir = None

# #            for t in pkg.tasks:
# #                t._basedir = os.path.dirname(root)

#         if exp_pkg_name is not None:
#             if exp_pkg_name != pkg.name:
#                 raise Exception("Package name mismatch: %s != %s" % (exp_pkg_name, pkg.name))

#         if len(pkg.fragments) > 0:
#             raise Exception("Cannot load a package-def with fragments from a string")

#         return pkg
    

