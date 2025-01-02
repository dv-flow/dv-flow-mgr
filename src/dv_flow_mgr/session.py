#****************************************************************************
#* session.py
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
import os
import copy
import yaml
import dataclasses as dc
from typing import Any, Dict, List
from .package import Package, PackageSpec
from .task_impl import TaskImpl

@dc.dataclass
class Session(object):
    """Manages the running of a flow"""

    # Search path for .dfs files
    package_path : List[str] = dc.field(default_factory=list)
    package_map : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    package : Package = None
    task_impl_m : Dict[str,TaskImpl] = dc.field(default_factory=dict)
    _root_dir : str = None
    _pkg_s : List[Package] = dc.field(default_factory=list)
    _task_id : int = 0

    def addImpl(self, name : str, impl : TaskImpl):
        self.task_impl_m[name] = impl

    def load(self, root : str):
        if os.path.isdir(root):
            root_f = []
            for f in os.listdir(root):
                if f.endswith(".dfs"):
                    root_f.append(os.path.join(root, f))
            if len(root_f) == 0:
                raise Exception("No .dfs files found in " + root)
            elif len(root_f) > 1:
                raise Exception("Multiple .dfs files found in " + root + "(" + ",".join(root_f) + ")")
            else:
                root = root_f[0]

        self._root_dir = os.path.dirname(root)

        self.package = self._load_package(root, [])

    def mkTaskGraph(self, task : str, tasks : Dict[str,TaskImpl]=None) -> TaskImpl:

        if tasks is None:
            self._pkg_s.clear()
            tasks = {}

        elems = task.split(".")

        pkg_name = ".".join(elems[0:-1])
        task_name = elems[-1]

        if pkg_name == "":
            if len(self._pkg_s) == 0:
                raise Exception("No package context for %s" % task)
            pkg = self._pkg_s[-1]
        else:
            pkg = self.getPackage(PackageSpec(pkg_name))
        task = pkg.getTask(task_name)

        print("Append package %s" % pkg.name)
        self._pkg_s.append(pkg)

        if task.impl is None:
            raise Exception("Task %s does not have an implementation" % task_name)
        
        if task.impl not in self.task_impl_m.keys():
            raise Exception("Task implementation %s not found" % task.impl)
        
        impl = self.task_impl_m[task.impl]
        impl_o = impl(task, self)

        for d in task.depends:
            if d in tasks.keys():
                impl_o.addDep(tasks[d])
            else:
                impl_o.addDep(self.mkTaskGraph(d, tasks))
        
        tasks[task.name] = impl_o

        self._pkg_s.pop()

        return impl_o
    
    def mkTaskId(self, task : 'Task') -> int:
        self._task_id += 1
        # TODO: save task <-> id map for later?
        return self._task_id

    async def run(self, task : str):
        impl = self.mkTaskGraph(task)

        return await impl.do_run()

    def _load_package(self, root : str, file_s : List[str]) -> Package:
        if root in file_s:
            raise Exception("Recursive file processing @ %s: %s" % (root, ",".join(self._file_s)))
        file_s.append(root)
        ret = None
        with open(root, "r") as fp:
            doc = yaml.load(fp, Loader=yaml.FullLoader)
            if "package" not in doc.keys():
                raise Exception("Missing 'package' key in %s" % root)
            pkg = Package(**(doc["package"]))

            for t in pkg.tasks:
                t.basedir = os.path.dirname(root)

        if not len(self._pkg_s):
            self._pkg_s.append(pkg)
            self.package_map[PackageSpec(pkg.name)] = pkg
        else:
            if self._pkg_s[0].name != pkg.name:
                raise Exception("Package name mismatch: %s != %s" % (self._pkg_s[0].name, pkg.name))
            else:
                # TODO: merge content
                self._pkg_s.append(pkg)

        print("pkg: %s" % str(pkg))
        
        # TODO: read in sub-files

        self._pkg_s.pop()
        file_s.pop()

    def getPackage(self, spec : PackageSpec) -> Package:
        if spec in self.package_map.keys():
            return self.package_map[spec]
        else:
            base_spec = PackageSpec(spec.name)
            if not base_spec in self.package_map.keys():
                # Template is not present. Go find it...

                # If not found...
                raise Exception("Package %s not found" % spec.name)

            base = self.package_map[PackageSpec(spec.name)]
            base_c = copy.deepcopy(base)
            base_c.params.update(spec.params)
            base_c.elab(self)
            self.package_map[spec] = base_c
            return base_c

