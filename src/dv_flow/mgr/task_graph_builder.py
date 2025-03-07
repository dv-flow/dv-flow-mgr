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
import logging
from .package import Package
from .package_def import PackageDef, PackageSpec
from .pkg_rgy import PkgRgy
from .task import Task
from .task_node import TaskNodeCtor
from typing import Dict, List, Union

@dc.dataclass
class TaskGraphBuilder(object):
    """The Task-Graph Builder knows how to discover packages and construct task graphs"""
    root_pkg : PackageDef
    rundir : str
    pkg_rgy : PkgRgy = None
    _pkg_s : List[Package] = dc.field(default_factory=list)
    _pkg_m : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    _pkg_spec_s : List[PackageDef] = dc.field(default_factory=list)
    _task_m : Dict['TaskSpec',Task] = dc.field(default_factory=dict)
    _logger : logging.Logger = None

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = PkgRgy.inst()

        self._logger = logging.getLogger(type(self).__name__)
        self._logger.debug("TaskGraphBuilder: root_pkg: %s" % str(self.root_pkg))

        if self.root_pkg is not None:

            # Register package definitions found during loading
            for subpkg in self.root_pkg.subpkg_m.values():
                self._logger.debug("Registering package %s" % subpkg.name)
                self.pkg_rgy.registerPackage(subpkg)

            self._pkg_spec_s.append(self.root_pkg)
            pkg = self.root_pkg.mkPackage(self)
            self._pkg_spec_s.pop()

            # Allows us to find ourselves
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

        self._logger.debug("pkg_spec: %s" % str(pkg_spec))
        self._pkg_spec_s.append(pkg_spec)
        pkg = self.getPackage(pkg_spec)
        
        self._pkg_s.append(pkg)

        ctor_t : TaskNodeCtor = pkg.getTaskCtor(task_name)

        self._logger.debug("ctor_t: %s" % ctor_t.name)

        needs = []

        for need_def in ctor_t.getNeeds():
            if not need_def in self._task_m.keys():
                need_t = self._mkTaskGraph(need_def, rundir)
                self._task_m[need_def] = need_t
            needs.append(self._task_m[need_def])

        # The returned task should have all param references resolved
        params = ctor_t.mkTaskParams()

        if params is None:
            raise Exception("ctor %s returned None for params" % str(ctor_t))

        task = ctor_t.mkTaskNode(
            params=params,
            name=task,
            needs=needs)
        task.rundir = rundir
        
        self._task_m[task.name] = task

        self._pkg_s.pop()
        self._pkg_spec_s.pop()

        return task

    def getPackage(self, spec : PackageSpec) -> Package:
        # Obtain the active package definition
        self._logger.debug("--> getPackage: %s len: %d" % (spec.name, len(self._pkg_spec_s)))
        if len(self._pkg_spec_s) > 0:
            pkg_spec = self._pkg_spec_s[-1]
            if self.root_pkg is not None and self.root_pkg.name == pkg_spec.name:
                pkg_def = self.root_pkg
            else:
                pkg_def = self.pkg_rgy.getPackage(pkg_spec.name)
        else:
            pkg_def = None

        # Need a stack to track which package we are currently in
        # Need a map to get a concrete package from a name with parameterization

        self._logger.debug("pkg_s: %d %s" % (
            len(self._pkg_s), (self._pkg_s[-1].name if len(self._pkg_s) else "<unknown>")))

        # First, check the active pkg_def to see if any aliases
        # Should be considered
        pkg_name = spec.name
        if pkg_def is not None:
            # Look for an import alias
            self._logger.debug("Search package %s for import alias %s" % (
                pkg_def.name, pkg_spec.name))
            for imp in pkg_def.imports:
                if type(imp) != str:
                    self._logger.debug("imp: %s" % str(imp))
                    if imp.alias is not None and imp.alias == spec.name:
                        # Found the alias name. Just need to get an instance of this package
                        self._logger.debug("Found alias %s -> %s" % (imp.alias, imp.name))
                        pkg_name = imp.name
                        break

        # Note: _pkg_m needs to be context specific, such that imports from
        # one package don't end up visible in another
        spec.name = pkg_name

        if spec in self._pkg_m.keys():
            self._logger.debug("Found cached package instance")
            pkg = self._pkg_m[spec]
        elif self.pkg_rgy.hasPackage(spec.name):
            self._logger.debug("Registry has a definition")
            p_def =  self.pkg_rgy.getPackage(spec.name)

            self._pkg_spec_s.append(p_def)
            pkg = p_def.mkPackage(self)
            self._pkg_spec_s.pop()
            self._pkg_m[spec] = pkg
        else:
            raise Exception("Failed to find definition of package %s" % spec.name)

        self._logger.debug("<-- getPackage: %s" % str(pkg))

        return pkg
    
    def mkTaskNode(self, task_t, name=None, srcdir=None, needs=None, **kwargs):
        self._logger.debug("--> mkTaskNode: %s" % task_t)
        ctor = self.getTaskCtor(task_t)
        self._logger.debug("ctor: %s" % ctor.name)
        params = ctor.mkTaskParams(kwargs)
        ret = ctor.mkTaskNode(
            params=params,
            name=name, 
            srcdir=srcdir, 
            needs=needs)
        self._logger.debug("<-- mkTaskNode: %s" % task_t)
        return ret
        
    def getTaskCtor(self, spec : Union[str,'TaskSpec'], pkg : PackageDef = None) -> 'TaskCtor':
        from .task_def import TaskSpec
        if type(spec) == str:
            spec = TaskSpec(spec)

        self._logger.debug("--> getTaskCtor %s" % spec.name)
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
                self._logger.critical("Failed to find package %s while looking for task %s" % (pkg_name, spec.name))
                raise e

        ctor = pkg.getTaskCtor(task_name)

        self._logger.debug("--> getTaskCtor %s" % spec.name)
        return ctor
