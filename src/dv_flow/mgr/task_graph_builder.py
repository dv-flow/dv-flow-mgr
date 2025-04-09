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
from .task_node_ctor_compound import TaskNodeCtorCompound
from .task_node_ctor_compound_proxy import TaskNodeCtorCompoundProxy
from .task_node_ctor_proxy import TaskNodeCtorProxy
from .task_node_ctor_task import TaskNodeCtorTask
from .task_node_ctor_wrapper import TaskNodeCtorWrapper
from .task_node_compound import TaskNodeCompound
from .task_node_leaf import TaskNodeLeaf
from .std.task_null import TaskNull
from .exec_callable import ExecCallable
from .null_callable import NullCallable
from .shell_callable import ShellCallable

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
    _pkg_m : Dict[PackageSpec,Package] = dc.field(default_factory=dict)
    _pkg_spec_s : List[PackageDef] = dc.field(default_factory=list)
    _shell_m : Dict[str,Callable] = dc.field(default_factory=dict)
    _task_m : Dict[str,Task] = dc.field(default_factory=dict)
    _task_node_m : Dict['TaskSpec',TaskNode] = dc.field(default_factory=dict)
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
        self._shell_m.update(ExtRgy._inst._shell_m)

        if self.root_pkg is not None:
            # Collect all the tasks
            pkg_s = set()
            self._addPackageTasks(self.root_pkg, pkg_s)

    def _addPackageTasks(self, pkg, pkg_s):
        if pkg not in pkg_s:
            pkg_s.add(pkg)
            for task in pkg.task_m.values():
                self._addTask(task)
            for subpkg in pkg.pkg_m.values():
                self._addPackageTasks(subpkg, pkg_s)

    def _addTask(self, task):
        if task.name not in self._task_m.keys():
            self._task_m[task.name] = task
            for st in task.subtasks:
                self._addTask(st)

    def addOverride(self, key : str, val : str):
        self._override_m[key] = val

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

    def enter_compound_uses(self):
        self._compound_task_ctxt_s[-1].uses_s.append({})

    def leave_compound_uses(self):
        if len(self._compound_task_ctxt_s[-1].uses_s) > 1:
            # Propagate the items up the stack, appending 'super' to 
            # the names
            for k,v in self._compound_task_ctxt_s[-1].uses_s[-1].items():
                self._compound_task_ctxt_s[-1].uses_s[-2]["super.%s" % k] = v
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
            self._task_node_m[name] = task
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
        if task is None and name in self._task_node_m.keys():
            task = self._task_node_m[name]

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
        return self.mkTaskNode(task, rundir=rundir)
        # self._task_node_m.clear()

        # if rundir is not None:
        #     self._rundir_s.append(rundir)

        # ret = self._mkTaskGraph(task)

        # if rundir is not None:
        #     self._rundir_s.pop()

        # return ret
        
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
        
        self._task_node_m[task.name] = task

        return task
    
    def mkTaskNode(self, task_t, name=None, srcdir=None, needs=None, **kwargs):
        self._log.debug("--> mkTaskNode: %s" % task_t)

        pkg = None

        if task_t in self._task_m.keys():
            task = self._task_m[task_t]
        else:
            raise Exception("task_t (%s) not present" % str(task_t))

        # Determine how to build this node
        if task.subtasks is not None and len(task.subtasks):
            ret = self._mkTaskCompoundNode(task)
        else:
            ret = self._mkTaskLeafNode(task, name)

        if needs is not None:
            for need in needs:
                ret.needs.append((need, False))

        for k,v in kwargs.items():
            if hasattr(ret.params, k):
                setattr(ret.params, k, v)
            else:
                raise Exception("Task %s parameters do not include %s" % (task.name, k))

        # if ctor is not None:
        #     if needs is None:
        #         needs = []
        #     for need_def in ctor.getNeeds():
        #         # Resolve the full name of the need
        #         need_fullname = self._resolveNeedRef(need_def)
        #         self._log.debug("Searching for qualifed-name task %s" % need_fullname)
        #         if not need_fullname in self._task_node_m.keys():
        #             rundir_s = self._rundir_s
        #             self._rundir_s = [need_fullname]
        #             need_t = self._mkTaskGraph(need_fullname)
        #             self._rundir_s = rundir_s
        #             self._task_node_m[need_fullname] = need_t
        #         needs.append(self._task_node_m[need_fullname])

        #     self._log.debug("ctor: %s" % ctor.name)
        #     params = ctor.mkTaskParams(kwargs)
        #     ret = ctor.mkTaskNode(
        #         self,
        #         params=params,
        #         name=name, 
        #         srcdir=srcdir, 
        #         needs=needs)
        #     ret.rundir = self.get_rundir(name)
        # else:
        #     raise Exception("Failed to find ctor for task %s" % task_t)
        self._log.debug("<-- mkTaskNode: %s" % task_t)
        return ret
    
    def _findTask(self, pkg, name):
        task = None
        if name in pkg.task_m.keys():
            task = pkg.task_m[name]
        else:
            for subpkg in pkg.pkg_m.values():
                task = self._findTask(subpkg, name)
                if task is not None:
                    break
        return task
    
    def _mkTaskNode(self, name):

        if name in self.root_pkg.task_m.keys():
            task = self.root_pkg.task_m[name]
#            ctor = self._getTaskCtor(self.root_pkg.task_m[task_t])
            pkg = self.root_pkg
        else:
            raise Exception("task_t (%s) not present" % str(name))
            pass

        # Determine how to build this node
        if task.subtasks is not None and len(task.subtasks):
            ret = self._mkTaskCompoundNode(task)
        else:
            ret = self._mkTaskLeafNode(task)

        return ret        
    
    def _getTaskNode(self, name):
        if name in self._task_node_m.keys():
            return self._task_node_m[name]
        else:
            return self.mkTaskNode(name)
    
    def _mkTaskLeafNode(self, task : Task, name=None) -> TaskNode:
        self._log.debug("--> _mkTaskLeafNode %s" % task.name)
        srcdir = os.path.dirname(task.srcinfo.file)

        if task.rundir == RundirE.Unique:
            self.enter_rundir(task.name)

        if name is None:
            name = task.name

        callable = None
        if task.run is not None:
            shell = task.shell if task.shell is not None else "shell"
            if shell in self._shell_m.keys():
                self._log.debug("Use shell implementation")
                callable = self._shell_m[shell]
            else:
                raise Exception("Shell %s not found" % shell)
        else:
            callable = NullCallable

        node = TaskNodeLeaf(
            name=name,
            srcdir=srcdir,
            params=task.paramT(),
            passthrough=task.passthrough,
            consumes=task.consumes,
            task=callable(task.run))
        self._task_node_m[name] = node
        node.rundir = self.get_rundir()

        # Now, link up the needs
        for n in task.needs:
            nn = self._getTaskNode(n.name)
            node.needs.append((nn, False))

        if task.rundir == RundirE.Unique:
            self.leave_rundir()

        self._log.debug("<-- _mkTaskLeafNode %s" % task.name)
        return node
    
    def _mkTaskCompoundNode(self, task : Task, name=None) -> TaskNode:
        self._log.debug("--> _mkTaskCompoundNode %s" % task.name)
        srcdir = os.path.dirname(task.srcinfo.file)

        if name is None:
            name = task.name

        if task.rundir == RundirE.Unique:
            self.enter_rundir(task.name)

        # Node represents the terminal node of the sub-DAG
        node = TaskNodeCompound(
            name=name,
            srcdir=srcdir,
            params=task.paramT()
        )
        self._task_node_m[name] = node
        node.rundir = self.get_rundir()

        node_needs = []
        for need in task.needs:
            nn = self._getTaskNode(need.name)
            node_needs.append(nn)

        # TODO: handle strategy

        # Need a local map of name -> task 
        # For now, build out local tasks and link up the needs
        tasks = []
        for t in task.subtasks:
            tasks.append((t, self._getTaskNode(t.name)))

        # Fill in 'needs'
        for t, tn in tasks:
            need_n = []

            referenced = False
            for tt in task.subtasks:
                if tt in t.needs:
                    referenced = True
                    break

            if len(t.needs):
                for need in t.needs:
                    nn = self._getTaskNode(need.name)
                    need_n.append((nn, False))
                tn.needs = need_n
            else:
                # Any node without dependencies is tied 
                # to the root node
                tn.needs = node_needs

            if not referenced:
                # Add this task as a dependency of the output
                # node (the root one)
                node.needs.append((tn, False))

        if task.rundir == RundirE.Unique:
            self.leave_rundir()

        return node

        
    def getTaskCtor(self, spec : Union[str,'TaskSpec'], pkg : PackageDef = None) -> 'TaskNodeCtor':
        from .task_def import TaskSpec
        if type(spec) == str:
            spec = TaskSpec(spec)

        self._log.debug("--> getTaskCtor %s" % spec.name)
        spec_e = spec.name.split(".")
        task_name = spec_e[-1]

        # if len(spec_e) == 1:
        #     # Just have a task name. Use the current package
        #     if len(self._pkg_s) == 0:
        #         raise Exception("No package context for task %s" % spec.name)
        #     pkg = self._pkg_s[-1]
        # else:
        #     pkg_name = ".".join(spec_e[0:-1])

        #     try:
        #         pkg = self.getPackage(PackageSpec(pkg_name))
        #     except Exception as e:
        #         self._log.critical("Failed to find package %s while looking for task %s" % (pkg_name, spec.name))
        #         raise e

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

        if ctor is None:
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

            base_ctor_t = self._getTaskCtor(task.uses)

            if base_ctor_t is None:
                self._log.error("Failed to load task ctor %s" % task.uses)
#            base_params = base_ctor_t.mkTaskParams()
        else:
            self._log.debug("No 'uses' specified %s" % task.name)

        self._log.debug("%d needs" % len(task.needs))

        # Determine the implementation constructor first
        if task.run is not None:
            shell = task.shell if task.shell is not None else "shell"

            if shell in self._shell_m.keys():
                self._log.debug("Use shell implementation")
                callable = self._shell_m[shell]
            else:
                self._log.debug("Shell %s not found" % shell)
                raise Exception("Shell %s not found" % shell)

            # if taskdef.body.pytask is not None:
            #     # Built-in impl
            #     # Now, lookup the class
            #     self._log.debug("Use PyTask implementation")
            #     last_dot = taskdef.body.pytask.rfind('.')
            #     clsname = taskdef.body.pytask[last_dot+1:]
            #     modname = taskdef.body.pytask[:last_dot]

            #     try:
            #         if modname not in sys.modules:
            #             if srcdir not in sys.path:
            #                 sys.path.append(srcdir)
            #             mod = importlib.import_module(modname)
            #         else:
            #             mod = sys.modules[modname]
            #     except ModuleNotFoundError as e:
            #         raise Exception("Failed to import module %s (_basedir=%s): %s" % (
            #             modname, self._basedir, str(e)))
                
            #     if not hasattr(mod, clsname):
            #         raise Exception("Method %s not found in module %s" % (clsname, modname))
            #     callable = getattr(mod, clsname)
            # elif taskdef.body.run is not None:
            #     callable = self._getRunCallable(taskdef)
        else:
            # TODO: use null task
            pass

        # Determine if we need to use a new 
        if task.paramT is None:
            raise Exception()
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
        self._log.debug("--> _getRunCallable %s" % task.name)
        callable = None
        if task.run is not None and task.shell == "python":
            # Evaluate a Python script
            pass
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
        paramT = task.paramT

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
