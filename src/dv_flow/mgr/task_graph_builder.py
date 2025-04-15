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
import pydantic
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
from .type import Type
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
    _type_m : Dict[str,Type] = dc.field(default_factory=dict)
    _task_node_m : Dict['TaskSpec',TaskNode] = dc.field(default_factory=dict)
    _type_node_m : Dict[str,Any] = dc.field(default_factory=dict)
    _task_ctor_m : Dict[Task,TaskNodeCtor] = dc.field(default_factory=dict)
    _override_m : Dict[str,str] = dc.field(default_factory=dict)
    _ns_scope_s : List[TaskNamespaceScope] = dc.field(default_factory=list)
    _compound_task_ctxt_s : List[CompoundTaskCtxt] = dc.field(default_factory=list)
    _task_rundir_s : List[List[str]] = dc.field(default_factory=list)
    _task_node_s : List[TaskNode] = dc.field(default_factory=list)
    _uses_count : int = 0

    _log : logging.Logger = None

    def __post_init__(self):
        # Initialize the overrides from the global registry
        self._log = logging.getLogger(type(self).__name__)
        self._shell_m.update(ExtRgy._inst._shell_m)
        self._task_rundir_s.append([])

        if self.root_pkg is not None:
            # Collect all the tasks
            pkg_s = set()
            self._addPackageDecl(self.root_pkg, pkg_s)

    def _addPackageDecl(self, pkg, pkg_s):
        if pkg not in pkg_s:
            pkg_s.add(pkg)
            for task in pkg.task_m.values():
                self._addTask(task)
            for tt in pkg.type_m.values():
                self._addType(tt)
            for subpkg in pkg.pkg_m.values():
                self._addPackageTasks(subpkg, pkg_s)

    def _addTask(self, task):
        if task.name not in self._task_m.keys():
            self._task_m[task.name] = task
            for st in task.subtasks:
                self._addTask(st)

    def _addType(self, tt):
        if tt.name not in self._type_m.keys():
            self._type_m[tt.name] = tt

    def addOverride(self, key : str, val : str):
        self._override_m[key] = val

    def enter_package(self, pkg : PackageDef):
        pass

    def enter_rundir(self, rundir : str):
        self._log.debug("enter_rundir: %s (%d)" % (rundir, len(self._task_rundir_s[-1])))
        self._task_rundir_s[-1].append(rundir)

    def get_rundir(self, rundir=None):
        ret = self._task_rundir_s[-1].copy()
        if rundir is not None:
            ret.append(rundir)
        self._log.debug("get_rundir: %s" % str(ret))
        return ret
    
    def leave_rundir(self):
        self._log.debug("leave_rundir")
        self._task_rundir_s[-1].pop()

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
        
    def mkTaskNode(self, task_t, name=None, srcdir=None, needs=None, **kwargs):
        self._log.debug("--> mkTaskNode: %s" % task_t)

        if task_t in self._task_m.keys():
            task = self._task_m[task_t]
        else:
            raise Exception("task_t (%s) not present" % str(task_t))
        
        ret = self._mkTaskNode(task)

        if needs is not None:
            for need in needs:
                ret.needs.append((need, False))

        for k,v in kwargs.items():
            if hasattr(ret.params, k):
                setattr(ret.params, k, v)
            else:
                raise Exception("Task %s parameters do not include %s" % (task.name, k))

        self._log.debug("<-- mkTaskNode: %s" % task_t)
        return ret
    
    def mkDataItem(self, name, **kwargs):
        self._log.debug("--> mkDataItem: %s" % name)

        if name in self._type_m.keys():
            tt = self._type_m[name]
        else:
            raise Exception("Type %s does not exist" % name)
        
        if tt in self._type_node_m.keys():
            tn = self._type_node_m[tt]
        else:
            tn = self._mkDataItem(tt)
            self._type_node_m[tt] = tn

        ret = tn()

        self._log.debug("<-- mkDataItem: %s" % name)
        return ret
    
    def _findType(self, pkg, name):
        tt = None
        if name in pkg.type_m.keys():
            tt = pkg.type_m[name]
        else:
            for subpkg in pkg.pkg_m.values():
                tt = self._findType(subpkg, name)
                if tt is not None:
                    break
        return tt
    
    def _mkDataItem(self, tt : Type):
        field_m = {}

        # Save the type name in each instance 
        field_m["type"] = (str, tt.name)
        exclude_s = set()
        exclude_s.add("type")

        self._mkDataItemI(tt, field_m, exclude_s)

        ret = pydantic.create_model(tt.name, **field_m)

        return ret
    
    def _mkDataItemI(self, tt : Type, field_m, exclude_s):
        # First, identify cases where the value is set
        for pt in tt.params.values():
            if pt.name not in exclude_s:
                if pt.type is not None:
                    # Defining a new attribute
                    field_m[pt.name] = (str, pt.value)
                else:
                    # TODO: determine whether 
                    field_m[pt.name] = (str, None)
        if tt.uses is not None:
            self._mkDataItemI(tt.uses, field_m, exclude_s)
    
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
    
    def _mkTaskNode(self, task : Task, name=None, srcdir=None, params=None, hierarchical=False):

        if not hierarchical:
            self._task_rundir_s.append([])

        # Determine how to build this node
        if self._isCompound(task):
            ret = self._mkTaskCompoundNode(
                task, 
                name=name,
                srcdir=srcdir,
                params=params,
                hierarchical=hierarchical)
        else:
            ret = self._mkTaskLeafNode(
                task, 
                name=name,
                srcdir=srcdir,
                params=params,
                hierarchical=hierarchical)

        if not hierarchical:
            self._task_rundir_s.pop()

        return ret        
    
    def _isCompound(self, task):
        if task.subtasks is not None and len(task.subtasks):
            return True
        elif task.uses is not None:
            return self._isCompound(task.uses)
    
    def _getTaskNode(self, name):
        if name in self._task_node_m.keys():
            return self._task_node_m[name]
        else:
            return self.mkTaskNode(name)
    
    def _mkTaskLeafNode(self, task : Task, name=None, srcdir=None, params=None, hierarchical=False) -> TaskNode:
        self._log.debug("--> _mkTaskLeafNode %s" % task.name)

        if name is None:
            name = task.name

        if srcdir is None:
            srcdir = os.path.dirname(task.srcinfo.file)
        
        if params is None:
            params = task.paramT()

        if task.rundir == RundirE.Unique:
            self.enter_rundir(task.name)


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
            params=params,
            passthrough=task.passthrough,
            consumes=task.consumes,
            task=callable(task.run))
        self._task_node_m[name] = node
        node.rundir = self.get_rundir()

        if len(self._task_node_s):
            node.parent = self._task_node_s[-1]

        # Now, link up the needs
        self._log.debug("--> processing needs")
        self._gatherNeeds(task, node)
        self._log.debug("<-- processing needs")

        if task.rundir == RundirE.Unique:
            self.leave_rundir()

        self._log.debug("<-- _mkTaskLeafNode %s" % task.name)
        return node
    
    def _mkTaskCompoundNode(self, task : Task, name=None, srcdir=None, params=None, hierarchical=False) -> TaskNode:
        self._log.debug("--> _mkTaskCompoundNode %s" % task.name)

        if name is None:
            name = task.name

        if srcdir is None:
            srcdir = os.path.dirname(task.srcinfo.file)

        if params is None:
            params = task.paramT()

        if task.rundir == RundirE.Unique:
            self.enter_rundir(task.name)

        if task.uses is not None:
            # This is a compound task that is based on
            # another. Create the base implementation
            node = self._mkTaskNode(
                task.uses,
                name=name, 
                srcdir=srcdir,
                params=params,
                hierarchical=True)
            
            if not isinstance(node, TaskNodeCompound):
                # TODO: need to enclose the leaf node in a compound wrapper
                raise Exception("Task %s is not compound" % task.uses)
        else:
            # Node represents the terminal node of the sub-DAG
            node = TaskNodeCompound(
                name=name,
                srcdir=srcdir,
                params=params)

        if len(self._task_node_s):
            node.parent = self._task_node_s[-1]

        self._task_node_m[name] = node
        self._task_node_s.append(node)

        node.rundir = self.get_rundir()

        # Put the input node inside the compound task's rundir
        self.enter_rundir(task.name + ".in")
        node.input.rundir = self.get_rundir()
        self.leave_rundir()

        self._log.debug("--> processing needs (%s)" % task.name)
        for need in task.needs:
            need_n = self._getTaskNode(need.name)
            self._log.debug("Add need %s" % need_n.name)
            if need_n is None:
                raise Exception("Failed to find need %s" % need.name)
            node.input.needs.append((need_n, False))
        self._log.debug("<-- processing needs")

        # TODO: handle strategy

        # Need a local map of name -> task 
        # For now, build out local tasks and link up the needs
        tasks = []
        for t in task.subtasks:
            nn = self._mkTaskNode(t, hierarchical=True)
            node.tasks.append(nn)
#            tasks.append((t, self._getTaskNode(t.name)))
            tasks.append((t, nn))

        # Pop the node stack, since we're done constructing the body
        self._task_node_s.pop()

        # Fill in 'needs'
        for t, tn in tasks:
            self._log.debug("Process node %s" % t.name)

            referenced = None
            for tt in task.subtasks:
                if tt in t.needs:
                    referenced = tt
                    break

            refs_internal = None
            # Assess how this task is connected to others in the compound node
            for nn,_ in tn.first.needs:
                self._log.debug("Need: %s" % nn.name)
                for _,tnn in tasks:
                    if nn == tnn:
                        refs_internal = tnn
                        break
                if refs_internal is not None:
                    break
            
            if not refs_internal:
                # Any node that doesn't depend on an internal
                # task is a top-level task
                self._log.debug("Node %s doesn't reference any internal node" % t.name)
                tn.needs.append((node.input, False))
            else:
                self._log.debug("Node %s references internal node %s" % (t.name, refs_internal.name))

            if referenced is not None:
                # Add this task as a dependency of the output
                # node (the root one)
                self._log.debug("Add node %s as a top-level dependency" % tn.name)
                node.needs.append((tn, False))
            else:
                self._log.debug("Node %s has internal needs" % tn.name)

        if task.rundir == RundirE.Unique:
            self.leave_rundir()

        return node

    def _gatherNeeds(self, task_t, node):
        self._log.debug("--> _gatherNeeds %s" % task_t.name)
        if task_t.uses is not None:
            self._gatherNeeds(task_t.uses, node)

        for need in task_t.needs:
            need_n = self._getTaskNode(need.name)
            if need_n is None:
                raise Exception("Failed to find need %s" % need.name)
            node.needs.append((need_n, False))
        self._log.debug("<-- _gatherNeeds %s" % task_t.name)
        
    def error(self, msg, loc=None):
        if loc is not None:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error, loc=loc)
        else:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error)
        self.marker(marker)

    def marker(self, marker):
        self.marker_l(marker)

