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
from typing import Callable, Any, Dict, List, Union
from .package import Package
from .package_def import PackageDef, PackageSpec
from .ext_rgy import ExtRgy
from .task import Task
from .task_def import RundirE
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
from .task_node import TaskNode
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor_compound import TaskNodeCtorCompound
from .task_node_ctor_compound_proxy import TaskNodeCtorCompoundProxy
from .task_node_ctor_proxy import TaskNodeCtorProxy
from .task_node_ctor_task import TaskNodeCtorTask
from .task_node_ctor_wrapper import TaskNodeCtorWrapper
from .std.task_null import TaskNull
from .shell_callable import ShellCallable
from .exec_callable import ExecCallable

@dc.dataclass
class TaskNamespaceScope(object):
    task_m : Dict[str,TaskNode] = dc.field(default_factory=dict)

@dc.dataclass
class CompoundTaskCtxt(object):
    parent : 'TaskGraphBuilder'
    task : 'TaskNode'
    rundir : RundirE
    task_m : Dict[str,TaskNode] = dc.field(default_factory=dict)
    uses_s : List[Dict[str, TaskNode]] = dc.field(default_factory=list)

@dc.dataclass
class TaskGraphBuilder(object):
    """The Task-Graph Builder knows how to discover packages and construct task graphs"""
    root_pkg : Package
    rundir : str
    marker_l : Callable = lambda *args, **kwargs: None
    _pkg_s : List[Package] = dc.field(default_factory=list)
    _pkg_m : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    _pkg_spec_s : List[PackageDef] = dc.field(default_factory=list)
    _shell_m : Dict[str,Callable] = dc.field(default_factory=dict)
    _task_m : Dict['TaskSpec',TaskNode] = dc.field(default_factory=dict)
    _task_ctor_m : Dict[Task,TaskNodeCtor] = dc.field(default_factory=dict)
    _override_m : Dict[str,str] = dc.field(default_factory=dict)
    _ns_scope_s : List[TaskNamespaceScope] = dc.field(default_factory=list)
    _compound_task_ctxt_s : List[CompoundTaskCtxt] = dc.field(default_factory=list)
    _rundir_s : List[str] = dc.field(default_factory=list)
    _uses_count : int = 0

    _log : logging.Logger = None

    def __post_init__(self):
        # Initialize the overrides from the global registry
        self._log = logging.getLogger(type(self).__name__)
        self._shell_m.update(ExtRgy._inst.shell_m)

    def addOverride(self, key : str, val : str):
        self._override_m[key] = val

    def push_package(self, pkg : Package, add=False):
        self._pkg_s.append(pkg)
        if add:
            self._pkg_m[PackageSpec(pkg.name, pkg.params)] = pkg

    def pop_package(self, pkg : Package):
        self._pkg_s.pop()

    def package(self):
        return self._pkg_s[-1]

    def enter_rundir(self, rundir : str):
        self._rundir_s.append(rundir)

    def get_rundir(self, rundir=None):
        ret = self._rundir_s.copy()
        if rundir is not None:
            ret.append(rundir)
        return ret
    
    def leave_rundir(self):
        self._rundir_s.pop()

    def enter_uses(self):
        self._uses_count += 1

    def in_uses(self):
        return (self._uses_count > 0)
    
    def leave_uses(self):
        self._uses_count -= 1

    def enter_compound(self, task : TaskNode, rundir=None):
        self._compound_task_ctxt_s.append(CompoundTaskCtxt(
            parent=self, task=task, rundir=rundir))

        if rundir is None or rundir == RundirE.Unique:
            self._rundir_s.append(task.name)

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
        self._log.debug("--> addTask: %s" % name)

        if len(self._compound_task_ctxt_s) == 0:
            self._task_m[name] = task
        else:
            if len(self._compound_task_ctxt_s[-1].uses_s) > 0:
                self._compound_task_ctxt_s[-1].uses_s[-1][name] = task
            else:
                self._compound_task_ctxt_s[-1].task_m[name] = task
        self._log.debug("<-- addTask: %s" % name)

    def findTask(self, name, create=True):
        task = None

        if len(self._compound_task_ctxt_s) > 0:
            if len(self._compound_task_ctxt_s[-1].uses_s) > 0:
                if name in self._compound_task_ctxt_s[-1].uses_s[-1].keys():
                    task = self._compound_task_ctxt_s[-1].uses_s[-1][name]
            if task is None and name in self._compound_task_ctxt_s[-1].task_m.keys():
                task = self._compound_task_ctxt_s[-1].task_m[name]
        if task is None and name in self._task_m.keys():
            task = self._task_m[name]

        if task is None and create:
            if name in self.root_pkg.task_m.keys():
                task = self.mkTaskGraph(name)
                self._log.debug("Found task %s in root package" % name)
            else:
                raise Exception("Failed to find task %s" % name)
                pass
            # Go search type definitions
            pass

            # Check the current package
#            if len(self._pkg_s) > 0 and name in self._pkg_s[-1].task_m.keys():
#                task = self._pkg_s[-1].task_m[name]
        
        return task

    def leave_compound(self, task : TaskNode):
        ctxt = self._compound_task_ctxt_s.pop()
        if ctxt.rundir is None or ctxt.rundir == RundirE.Unique:
            self._rundir_s.pop()

    def mkTaskGraph(self, task : str, rundir=None) -> TaskNode:
        self._pkg_s.clear()
        self._task_m.clear()

        if rundir is not None:
            self._rundir_s.append(rundir)

        ret = self._mkTaskGraph(task)

        if rundir is not None:
            self._rundir_s.pop()

        return ret
        
    def _mkTaskGraph(self, task : str) -> TaskNode:

        if task in self.root_pkg.task_m.keys():
            task_t = self.root_pkg.task_m[task]
        else:
            pass

        if task_t is None:
            raise Exception("Failed to find task %s" % task)

        ctor = self._getTaskCtor(task_t)

        params = ctor.mkTaskParams()

        needs = []

        for need in task_t.needs:
            need_n = self.findTask(need.name)
            if need_n is None:
                raise Exception("Failed to find need %s" % need.name)
            needs.append(need_n)

        task = ctor.mkTaskNode(
            builder=self,
            params=params,
            name=task,
            needs=needs)
        task.rundir = self.get_rundir(task.name)
#        task.rundir = rundir
        
        self._task_m[task.name] = task

#        self._pkg_s.pop()
#        self._pkg_spec_s.pop()

        return task
    
    def findTaskDef(self, name):
        pass

    def _resolveNeedRef(self, need_def) -> str:
        if need_def.find(".") == -1:
            # Need is a local task. Prefix to avoid ambiguity
            return self._pkg_s[-1].name + "." + need_def
        else:
            return need_def

    def getPackage(self, spec : PackageSpec) -> Package:
        # Obtain the active package definition
        self._log.debug("--> getPackage: %s len: %d" % (spec.name, len(self._pkg_spec_s)))
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

        self._log.debug("pkg_s: %d %s" % (
            len(self._pkg_s), (self._pkg_s[-1].name if len(self._pkg_s) else "<unknown>")))

        # First, check the active pkg_def to see if any aliases
        # Should be considered
        pkg_name = spec.name
        # if pkg_def is not None:
        #     # Look for an import alias
        #     self._log.debug("Search package %s for import alias %s" % (
        #         pkg_def.name, pkg_spec.name))
        #     for imp in pkg_def.imports:
        #         if type(imp) != str:
        #             self._log.debug("imp: %s" % str(imp))
        #             if imp.alias is not None and imp.alias == spec.name:
        #                 # Found the alias name. Just need to get an instance of this package
        #                 self._log.debug("Found alias %s -> %s" % (imp.alias, imp.name))
        #                 pkg_name = imp.name
        #                 break

        # Note: _pkg_m needs to be context specific, such that imports from
        # one package don't end up visible in another
        spec.name = pkg_name

        if spec in self._pkg_m.keys():
            self._log.debug("Found cached package instance")
            pkg = self._pkg_m[spec]
        elif self.pkg_rgy.hasPackage(spec.name):
            self._log.debug("Registry has a definition")
            p_def =  self.pkg_rgy.getPackage(spec.name)

            self._pkg_spec_s.append(p_def)
            pkg = p_def.mkPackage(self)
            self._pkg_spec_s.pop()
            self._pkg_m[spec] = pkg
        else:
            self.error("Failed to find package %s" % spec.name)
            raise Exception("Failed to find definition of package %s" % spec.name)

        self._log.debug("<-- getPackage: %s" % str(pkg))

        return pkg
    
    def mkTaskNode(self, task_t, name=None, srcdir=None, needs=None, **kwargs):
        self._log.debug("--> mkTaskNode: %s" % task_t)

        pkg = None
        if task_t in self.root_pkg.task_m.keys():
            ctor = self._getTaskCtor(self.root_pkg.task_m[task_t])
            pkg = self.root_pkg
        else:
            raise Exception("task_t (%s) not present" % str(task_t))
            pass
        self.push_package(pkg)

        if ctor is not None:
            if needs is None:
                needs = []
            for need_def in ctor.getNeeds():
                # Resolve the full name of the need
                need_fullname = self._resolveNeedRef(need_def)
                self._log.debug("Searching for qualifed-name task %s" % need_fullname)
                if not need_fullname in self._task_m.keys():
                    rundir_s = self._rundir_s
                    self._rundir_s = [need_fullname]
                    need_t = self._mkTaskGraph(need_fullname)
                    self._rundir_s = rundir_s
                    self._task_m[need_fullname] = need_t
                needs.append(self._task_m[need_fullname])

            self._log.debug("ctor: %s" % ctor.name)
            params = ctor.mkTaskParams(kwargs)
            ret = ctor.mkTaskNode(
                self,
                params=params,
                name=name, 
                srcdir=srcdir, 
                needs=needs)
            ret.rundir = self.get_rundir(name)
        else:
            raise Exception("Failed to find ctor for task %s" % task_t)
#        self._pkg_s.pop()
        self.pop_package(pkg)
        self._log.debug("<-- mkTaskNode: %s" % task_t)
        return ret
        
    def getTaskCtor(self, spec : Union[str,'TaskSpec'], pkg : PackageDef = None) -> 'TaskNodeCtor':
        from .task_def import TaskSpec
        if type(spec) == str:
            spec = TaskSpec(spec)

        self._log.debug("--> getTaskCtor %s" % spec.name)
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
                self._log.critical("Failed to find package %s while looking for task %s" % (pkg_name, spec.name))
                raise e

        ctor = pkg.getTaskCtor(task_name)

        self._log.debug("<-- getTaskCtor %s" % spec.name)
        return ctor
    
    def error(self, msg, loc=None):
        if loc is not None:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error, loc=loc)
        else:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error)
        self.marker(marker)

    def marker(self, marker):
        self.marker_l(marker)

    def _getTaskCtor(self, task : Task) -> TaskNodeCtor:
        if task in self._task_ctor_m.keys():
            ctor = self._task_ctor_m[task]
        else:
            ctor = self._mkTaskCtor(task)
            self._task_ctor_m[task] = ctor
        return ctor

    def _mkTaskCtor(self, task):
        srcdir = os.path.dirname(task.srcinfo.file)
        self._log.debug("--> mkTaskCtor %s (srcdir: %s)" % (task.name, srcdir))

        if len(task.subtasks) > 0:
            self._log.debug("Task has a body")
            # Compound task
            self._log.debug("Task specifies sub-task implementation")
            ctor = self._mkCompoundTaskCtor(task)
        else:
            self._log.debug("Task doesn't specify a body")
            # Shell task or 'null'
            ctor = self._mkLeafTaskCtor(task)

        if task.ctor is None:
            raise Exception()

        return ctor

    def _mkLeafTaskCtor(self, task) -> TaskNodeCtor:
        self._log.debug("--> _mkLeafTaskCtor")
        srcdir = os.path.dirname(task.srcinfo.file)
        base_ctor_t : TaskNodeCtor = None
        ctor_t : TaskNodeCtor = None
        base_params = None
        callable = None
#        fullname = self.name + "." + task.name
#        rundir = task.rundir

        # TODO: should we have the ctor look this up itself?
        # Want to confirm that the value can be found.
        # Defer final resolution until actual graph building (post-config)
        if task.uses is not None:
            self._log.debug("Uses: %s" % task.uses.name)

            if task.uses.ctor is None:
                self.uses.ctor = self._getTaskCtor(task.uses)
            base_ctor_t = task.uses.ctor
            base_params = base_ctor_t.mkTaskParams()

            if base_ctor_t is None:
                self._log.error("Failed to load task ctor %s" % task.uses)
        else:
            self._log.debug("No 'uses' specified %s" % task.name)

        self._log.debug("%d needs" % len(task.needs))

        # Determine the implementation constructor first
        if task.run is not None:
            shell = task.shell if task.shell is not None else "shell"

            if taskdef.body.pytask is not None:
                # Built-in impl
                # Now, lookup the class
                self._log.debug("Use PyTask implementation")
                last_dot = taskdef.body.pytask.rfind('.')
                clsname = taskdef.body.pytask[last_dot+1:]
                modname = taskdef.body.pytask[:last_dot]

                try:
                    if modname not in sys.modules:
                        if srcdir not in sys.path:
                            sys.path.append(srcdir)
                        mod = importlib.import_module(modname)
                    else:
                        mod = sys.modules[modname]
                except ModuleNotFoundError as e:
                    raise Exception("Failed to import module %s (_basedir=%s): %s" % (
                        modname, self._basedir, str(e)))
                
                if not hasattr(mod, clsname):
                    raise Exception("Method %s not found in module %s" % (clsname, modname))
                callable = getattr(mod, clsname)
            elif taskdef.body.run is not None:
                callable = self._getRunCallable(taskdef)

        # Determine if we need to use a new 
        paramT = task.paramT
        needs = []

        # TODO:
        rundir : RundirE = task.rundir
        
        if callable is not None:
            ctor_t = TaskNodeCtorTask(
                name=task.name,
                srcdir=srcdir,
                paramT=task.paramT, # TODO: need to determine the parameter type
                passthrough=task.passthrough,
                consumes=task.consumes,
                needs=needs, # TODO: need to determine the needs
                rundir=rundir,
                task=callable)
        elif base_ctor_t is not None:
            # Use the existing (base) to create the implementation
            ctor_t = TaskNodeCtorProxy(
                name=task.name,
                srcdir=srcdir,
                paramT=task.paramT, # TODO: need to determine the parameter type
                passthrough=task.passthrough,
                consumes=task.consumes,
                needs=needs,
                rundir=rundir,
                uses=base_ctor_t)
        else:
            self._log.debug("Use 'Null' as the class implementation")
            ctor_t = TaskNodeCtorTask(
                name=task.name,
                srcdir=srcdir,
                paramT=paramT,
                passthrough=task.passthrough,
                consumes=task.consumes,
                needs=needs,
                rundir=rundir,
                task=TaskNull)

        self._log.debug("<-- mkTaskCtor %s" % task.name)
        return ctor_t
    
    def _getRunCallable(self, task):
        self._log.debug("--> _getRunCallable %s" % taskdef.name)
        callable = None
        if task.run is not None and task.body.shell == "python":
            # Evaluate a Python script
            text = taskdef.body.run.strip()
            text_lines = text.splitlines()
            least_whitespace = 2^32
            have_content = False
            for line in text_lines:
                line_no_leading_ws = line.lstrip()
                if line_no_leading_ws != "":
                    have_content = True
                    leading_ws = len(line) - len(line_no_leading_ws)
                    if leading_ws < least_whitespace:
                        least_whitespace = leading_ws
            # Remove leading whitespace
            if have_content:
                for i,line in enumerate(text_lines):
                    if len(line) >= least_whitespace:
                        text_lines[i] = line[least_whitespace:]

            callable = ExecCallable(text_lines)
        else:
            # run a shell script
            shell = None
            body = task.run.strip()

            callable = ShellCallable(body=body, shell=shell)
            pass
        return callable

    def _mkCompoundTaskCtor(self, task) -> TaskNodeCtor:
        self._log.debug("--> _mkCompoundTaskCtor %s" % task.name)
        srcdir = os.path.dirname(task.srcinfo.file)
        base_ctor_t : TaskNodeCtor = None
        ctor_t : TaskNodeCtor = None
        base_params = None
        callable = None

#        fullname = self._getScopeFullname()
        fullname = task.name

        if task.uses is not None:
            self._log.debug("Uses: %s" % task.uses)
            base_ctor_t = task.uses.ctor
            base_params = base_ctor_t.mkTaskParams()

            if base_ctor_t is None:
                self._log.error("Failed to load task ctor %s" % task.uses)

        # TODO: should build during loading
#        passthrough, consumes, needs = self._getPTConsumesNeeds(taskdef, base_ctor_t)
        passthrough = []
        consumes = []
        needs = []

        # Determine if we need to use a new 
#        paramT = self._getParamT(taskdef, base_params)
        paramT = None

        if base_ctor_t is not None:
            ctor_t = TaskNodeCtorCompoundProxy(
                name=fullname,
                srcdir=srcdir,
                paramT=paramT,
                passthrough=passthrough,
                consumes=consumes,
                needs=needs,
                task=task,
                uses=base_ctor_t)
        else:
            self._log.debug("No 'uses' specified")
            ctor_t = TaskNodeCtorCompound(
                name=fullname,
                srcdir=srcdir,
                paramT=paramT,
                passthrough=passthrough,
                consumes=consumes,
                needs=needs,
                task=task)
            
        for st in task.subtasks:
            ctor = self._getTaskCtor(st)
            if ctor is None:
                raise Exception("ctor for %s is None" % st.name)
            ctor_t.tasks.append(st)

#        for t in task.subtasks:
#            ctor_t.tasks.append(self._mkTaskCtor(t, srcdir))

        
        self._log.debug("<-- mkCompoundTaskCtor %s (%d)" % (task.name, len(ctor_t.tasks)))
        return ctor_t    

