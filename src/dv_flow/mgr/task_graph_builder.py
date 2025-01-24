#****************************************************************************
#* task_graph_builder.py
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
import dataclasses as dc
from .package import Package
from .package_def import PackageDef, PackageSpec
from .pkg_rgy import PkgRgy
from .task import Task, TaskCtor, TaskSpec
from typing import Dict, List

@dc.dataclass
class TaskGraphBuilder(object):
    """The Task-Graph Builder knows how to discover packages and construct task graphs"""
    root_pkg : PackageDef
    rundir : str
    pkg_rgy : PkgRgy = None
    _pkg_s : List[Package] = dc.field(default_factory=list)
    _pkg_m : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    _pkg_spec_s : List[PackageDef] = dc.field(default_factory=list)
    _task_m : Dict[TaskSpec,Task] = dc.field(default_factory=dict)

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = PkgRgy.inst()

        if self.root_pkg is not None:
            self._pkg_spec_s.append(self.root_pkg)
            pkg = self.root_pkg.mkPackage(self)
            self._pkg_spec_s.pop()
            self._pkg_m[PackageSpec(self.root_pkg.name)] = pkg

    def push_package(self, pkg : Package, add=False):
        self._pkg_s.append(pkg)
        if add:
            self._pkg_m[PackageSpec(pkg.name, pkg.params)] = pkg

    def pop_package(self, pkg : Package):
        self._pkg_s.pop()

    def package(self):
        return self._pkg_s[-1]

    def mkTaskGraph(self, task : str) -> Task:
        self._pkg_s.clear()
        self._task_m.clear()

        return self._mkTaskGraph(task, self.rundir)
        
    def _mkTaskGraph(self, task : str, parent_rundir : str) -> Task:

        elems = task.split(".")

        pkg_name = ".".join(elems[0:-1])
        task_name = elems[-1]

        if pkg_name == "":
            if len(self._pkg_spec_s) == 0:
                raise Exception("No package context for %s" % task)
            pkg_spec = self._pkg_spec_s[-1]
            pkg_name = pkg_spec.name
        else:
            pkg_spec = PackageSpec(pkg_name)

        rundir = os.path.join(parent_rundir, pkg_name, task_name)

        print("pkg_spec: %s" % str(pkg_spec))
        self._pkg_spec_s.append(pkg_spec)
        pkg = self.getPackage(pkg_spec)
        
        self._pkg_s.append(pkg)

        ctor_t : TaskCtor = pkg.getTaskCtor(task_name)

        depends = []

        for dep in ctor_t.depends:
            if not dep in self._task_m.keys():
                task = self._mkTaskGraph(dep, rundir)
                self._task_m[dep] = task
                pass
            depends.append(self._task_m[dep])

        # The returned task should have all param references resolved
        print("task_ctor=%s" % str(ctor_t.task_ctor), flush=True)
        task = ctor_t.task_ctor(
            name=task_name,
            params=ctor_t.mkParams(),
            depends=depends,
            rundir=rundir,
            srcdir=ctor_t.srcdir)
        
        self._task_m[task.name] = task

        self._pkg_s.pop()
        self._pkg_spec_s.pop()

        return task

    def getPackage(self, spec : PackageSpec) -> Package:
        # Obtain the active package definition
        print("getPackage: %s len: %d" % (spec.name, len(self._pkg_spec_s)))
        if len(self._pkg_spec_s) > 0:
            pkg_spec = self._pkg_spec_s[-1]
            if self.root_pkg.name == pkg_spec.name:
                pkg_def = self.root_pkg
            else:
                pkg_def = self.pkg_rgy.getPackage(pkg_spec.name)
        else:
            pkg_def = None

        # Need a stack to track which package we are currently in
        # Need a map to get a concrete package from a name with parameterization

        print("pkg_s: %d %s" % (len(self._pkg_s), (self._pkg_s[-1].name if len(self._pkg_s) else "<unknown>")))

        # Note: _pkg_m needs to be context specific, such that imports from
        # one package don't end up visible in another
        if len(self._pkg_s) and spec.name == self._pkg_s[-1].name:
            pkg = self._pkg_s[-1]
        if spec in self._pkg_m.keys():
            pkg = self._pkg_m[spec]
        else:
            pkg = None

            if pkg_def is not None:
                # Look for an import alias
                print("imports: %s" % str(pkg_def.imports))
                for imp in pkg_def.imports:
                    print("imp: %s" % str(imp))
                    if imp.alias is not None and imp.alias == spec.name:
                        # Found the alias name. Just need to get an instance of this package
                        tgt_pkg_spec = PackageSpec(imp.name)
                        if tgt_pkg_spec in self._pkg_m.keys():
                            pkg = self._pkg_m[tgt_pkg_spec]
                        elif self.pkg_rgy.hasPackage(tgt_pkg_spec.name):
                            base = self.pkg_rgy.getPackage(tgt_pkg_spec.name)
                            pkg = base.mkPackage(self, spec.params)
                            self._pkg_m[spec] = pkg
                        elif imp.path is not None:
                            # See if we can load the package
                            print("TODO: load referenced package")
                        else:
                            raise Exception("Failed to resolve target (%s) of import alias %s" % (
                                imp.name,
                                imp.alias))
                        break
                    else:
                        # Need to compare the spec with the full import spec
                        imp_spec = PackageSpec(imp.name)
                        # TODO: set parameters
                        if imp_spec == spec:
                            base = self.pkg_rgy.getPackage(spec.name)
                            if base is None:
                                raise Exception("Failed to find imported package %s" % spec.name)
                            pkg = base.mkPackage(self, spec.params)
                            self._pkg_m[spec] = pkg
                            break
            
            if pkg is None:
                print("Checking registry")
                p_def =  self.pkg_rgy.getPackage(spec.name)

                if p_def is not None:
                    pkg = p_def.mkPackage(self)

            if pkg is None:
                raise Exception("Failed to find package %s from package %s" % (
                    spec.name, (pkg_def.name if pkg_def is not None else "<null>")))

        return pkg
        
    def getTaskCtor(self, spec : TaskSpec, pkg : PackageDef = None) -> 'TaskCtor':
        spec_e = spec.name.split(".")
        task_name = spec_e[-1]

        if len(spec_e) == 1:
            # Just have a task name. Use the current package
            if len(self._pkg_s) == 0:
                raise Exception("No package context for task %s" % spec.name)
            pkg = self._pkg_s[-1]
        else:
            pkg_name = ".".join(spec_e[0:-1])

            try:
                pkg = self.getPackage(PackageSpec(pkg_name))
            except Exception as e:
                print("Failed to find package %s while looking for task %s" % (pkg_name, spec.name))
                raise e

        return pkg.getTaskCtor(task_name)
