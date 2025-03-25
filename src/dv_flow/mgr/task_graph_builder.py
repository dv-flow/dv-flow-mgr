#****************************************************************************
#* task_graph_builder.py
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
import os
import dataclasses as dc
import logging
from .package import Package
from .package_def import PackageDef, PackageSpec
from .pkg_rgy import PkgRgy
from .task_node import TaskNode
from .task_node_ctor import TaskNodeCtor
from typing import Dict, List, Union

@dc.dataclass
class TaskNamespaceScope(object):
    task_m : Dict[str,TaskNode] = dc.field(default_factory=dict)

@dc.dataclass
class CompoundTaskCtxt(object):
    parent : 'TaskGraphBuilder'
    task : 'TaskNode'
    task_m : Dict[str,TaskNode] = dc.field(default_factory=dict)
    uses_s : List[Dict[str, TaskNode]] = dc.field(default_factory=list)

@dc.dataclass
class TaskGraphBuilder(object):
    """The Task-Graph Builder knows how to discover packages and construct task graphs"""
    root_pkg : PackageDef
    rundir : str
    pkg_rgy : PkgRgy = None
    _pkg_s : List[Package] = dc.field(default_factory=list)
    _pkg_m : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    _pkg_spec_s : List[PackageDef] = dc.field(default_factory=list)
    _task_m : Dict['TaskSpec',TaskNode] = dc.field(default_factory=dict)
    _override_m : Dict[str,str] = dc.field(default_factory=dict)
    _ns_scope_s : List[TaskNamespaceScope] = dc.field(default_factory=list)
    _compound_task_ctxt_s : List[CompoundTaskCtxt] = dc.field(default_factory=list)
    _uses_count : int = 0

    _logger : logging.Logger = None

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = PkgRgy.inst().copy()

        # Initialize the overrides from the global registry
        self._override_m.update(self.pkg_rgy.getOverrides())

        self._logger = logging.getLogger(type(self).__name__)

        if self.root_pkg is not None:
            self._logger.debug("TaskGraphBuilder: root_pkg: %s" % str(self.root_pkg))

            # Register package definitions found during loading
            visited = set()
            self._registerPackages(self.root_pkg, visited)

            self._pkg_spec_s.append(self.root_pkg)
            pkg = self.root_pkg.mkPackage(self)
            self._pkg_spec_s.pop()

            # Allows us to find ourselves
            self._pkg_m[PackageSpec(self.root_pkg.name)] = pkg

    def loadPkg(self, pkgfile : str):
        pkg = PackageDef.load(pkgfile)
        visited = set()
        self._registerPackages(pkg, visited)

    def addOverride(self, key : str, val : str):
        self._override_m[key] = val

    def _registerPackages(self, pkg : PackageDef, visited):
        self._logger.debug("Packages: %s" % str(pkg))
        if pkg.name not in visited:
            visited.add(pkg.name)
            self._logger.debug("Registering package %s" % pkg.name)
            self.pkg_rgy.registerPackage(pkg)
            for subpkg in pkg.subpkg_m.values():
                self._registerPackages(subpkg, visited)


    def push_package(self, pkg : Package, add=False):
        self._pkg_s.append(pkg)
        if add:
            self._pkg_m[PackageSpec(pkg.name, pkg.params)] = pkg

    def pop_package(self, pkg : Package):
        self._pkg_s.pop()

    def package(self):
        return self._pkg_s[-1]

    def enter_uses(self):
        self._uses_count += 1

    def in_uses(self):
        return (self._uses_count > 0)
    
    def leave_uses(self):
        self._uses_count -= 1
    
    def enter_compound(self, task : TaskNode):
        self._compound_task_ctxt_s.append(CompoundTaskCtxt(parent=self, task=task))

    def get_name_prefix(self):
        if len(self._compound_task_ctxt_s) > 0:
            # Use the compound scope name
            name = ".".join(c.task.name for c in self._compound_task_ctxt_s)
        else:
            name = self._pkg_s[-1].name

        return name

    def enter_compound_uses(self):
        self._compound_task_ctxt_s[-1].uses_s.append({})

    def leave_compound_uses(self):
        if len(self._compound_task_ctxt_s[-1].uses_s) > 1:
            # Propagate the items up the stack, appending 'super' to 
            # the names
            for k,v in self._compound_task_ctxt_s[-1].uses_s[-1].items():
                self._compound_task_ctxt_s[-1].uses[-2]["super.%s" % k] = v
        else:
            # Propagate the items to the compound namespace, appending
            # 'super' to the names
            for k,v in self._compound_task_ctxt_s[-1].uses_s[-1].items():
                self._compound_task_ctxt_s[-1].task_m["super.%s" % k] = v
        self._compound_task_ctxt_s[-1].uses_s.pop()

    def is_compound_uses(self):
        return len(self._compound_task_ctxt_s) > 0 and len(self._compound_task_ctxt_s[-1].uses_s) != 0

    def addTask(self, name, task : TaskNode):
        self._logger.debug("--> addTask: %s" % name)
        if len(self._compound_task_ctxt_s) == 0:
            self._task_m[name] = task
        else:
            if len(self._compound_task_ctxt_s[-1].uses_s) > 0:
                self._compound_task_ctxt_s[-1].uses_s[-1][name] = task
            else:
                self._compound_task_ctxt_s[-1].task_m[name] = task
        self._logger.debug("<-- addTask: %s" % name)

    def findTask(self, name):
        task = None

        if len(self._compound_task_ctxt_s) > 0:
            if len(self._compound_task_ctxt_s[-1].uses_s) > 0:
                if name in self._compound_task_ctxt_s[-1].uses_s[-1].keys():
                    task = self._compound_task_ctxt_s[-1].uses_s[-1][name]
            if task is None and name in self._compound_task_ctxt_s[-1].task_m.keys():
                task = self._compound_task_ctxt_s[-1].task_m[name]
        if task is None and name in self._task_m.keys():
            task = self._task_m[name]
        
        # if task is None:
        #     # TODO: Look for a def that hasn't yet been constructed
        #     task = self._mkTaskGraph(name, self.rundir)

        return task

    def leave_compound(self, task : TaskNode):
        self._compound_task_ctxt_s.pop()

    def mkTaskGraph(self, task : str) -> TaskNode:
        self._pkg_s.clear()
        self._task_m.clear()

        return self._mkTaskGraph(task, self.rundir)
        
    def _mkTaskGraph(self, task : str, parent_rundir : str) -> TaskNode:

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
            # Resolve the full name of the need
            need_fullname = self._resolveNeedRef(need_def)
            self._logger.debug("Searching for qualifed-name task %s" % need_fullname)
            if not need_fullname in self._task_m.keys():
                need_t = self._mkTaskGraph(need_fullname, rundir)
                self._task_m[need_fullname] = need_t
            needs.append(self._task_m[need_fullname])

        # The returned task should have all param references resolved
        params = ctor_t.mkTaskParams()

        if params is None:
            raise Exception("ctor %s returned None for params" % str(ctor_t))

        task = ctor_t.mkTaskNode(
            builder=self,
            params=params,
            name=task,
            needs=needs)
        task.rundir = rundir
        
        self._task_m[task.name] = task

        self._pkg_s.pop()
        self._pkg_spec_s.pop()

        return task

    def _resolveNeedRef(self, need_def) -> str:
        if need_def.find(".") == -1:
            # Need is a local task. Prefix to avoid ambiguity
            return self._pkg_s[-1].name + "." + need_def
        else:
            return need_def

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

        if task_t in self._override_m.keys():
            self._logger.debug("Overriding task %s with %s" % (task_t, self._override_m[task_t]))
            task_t = self._override_m[task_t]
        else:
            dot_idx = task_t.rfind(".")
            if dot_idx != -1:
                pkg = task_t[0:dot_idx]
                tname = task_t[dot_idx+1:]

                if pkg in self._override_m.keys():
                    self._logger.debug("Overriding package %s with %s" % (pkg, self._override_m[pkg]))
                    task_t = self._override_m[pkg] + "." + tname

        dot_idx = task_t.rfind(".")
        pkg = task_t[0:dot_idx]
        self._pkg_s.append(self.getPackage(PackageSpec(pkg)))

        ctor = self.getTaskCtor(task_t)
        if ctor is not None:
            if needs is None:
                needs = []
            for need_def in ctor.getNeeds():
                # Resolve the full name of the need
                need_fullname = self._resolveNeedRef(need_def)
                self._logger.debug("Searching for qualifed-name task %s" % need_fullname)
                if not need_fullname in self._task_m.keys():
                    need_t = self._mkTaskGraph(need_fullname, self.rundir)
                    self._task_m[need_fullname] = need_t
                needs.append(self._task_m[need_fullname])

            self._logger.debug("ctor: %s" % ctor.name)
            params = ctor.mkTaskParams(kwargs)
            ret = ctor.mkTaskNode(
                self,
                params=params,
                name=name, 
                srcdir=srcdir, 
                needs=needs)
        else:
            raise Exception("Failed to find ctor for task %s" % task_t)
        self._pkg_s.pop()
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
    

