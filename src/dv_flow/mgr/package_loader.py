import os
import dataclasses as dc
import importlib
import logging
import pydantic
import sys
import yaml
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .fragment_def import FragmentDef
from .package_def import PackageDef
from .package import Package
from .pkg_rgy import PkgRgy
from .task import Task
from .task_def import TaskDef, PassthroughE, ConsumesE, RundirE
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor_compound import TaskNodeCtorCompound
from .task_node_ctor_compound_proxy import TaskNodeCtorCompoundProxy
from .task_node_ctor_proxy import TaskNodeCtorProxy
from .task_node_ctor_task import TaskNodeCtorTask
from .task_node_ctor_wrapper import TaskNodeCtorWrapper
from .std.task_null import TaskNull
from .yaml_srcinfo_loader import YamlSrcInfoLoader

@dc.dataclass
class SymbolScope(object):
    name : str
    task_m : Dict[str,Task] = dc.field(default_factory=dict)

    def add(self, task, name):
        self.task_m[name] = task

    def find(self, name) -> Task:
        if name in self.task_m.keys():
            return self.task_m[name]
        else:
            return None

    def findType(self, name) -> Task:
        pass


@dc.dataclass
class TaskScope(SymbolScope):
    pass

@dc.dataclass
class LoaderScope(SymbolScope):
    loader : 'PackageLoader' = None

    def add(self, task, name):
        raise NotImplementedError("LoaderScope.add() not implemented")
    
    def find(self, name) -> Task:
        return self.findType(name)

    def findType(self, name) -> Task:
        last_dot = name.rfind('.')
        if last_dot != -1:
            pkg_name = name[:last_dot]
            task_name = name[last_dot+1:]

            if pkg_name in self.loader._pkg_m.keys():
                pkg = self.loader._pkg_m[pkg_name]
            else:
                path = self.loader.pkg_rgy.findPackagePath(pkg_name)
                if path is not None:
                    pkg = self.loader._loadPackage(path)
                    self.loader._pkg_m[pkg_name] = pkg
            if pkg is not None and name in pkg.task_m.keys():
                return pkg.task_m[name]
            else:
                return None

@dc.dataclass
class PackageScope(SymbolScope):
    pkg : Package = None
    loader : LoaderScope = None
    _scope_s : List[SymbolScope] = dc.field(default_factory=list)

    def add(self, task, name):
        if len(self._scope_s):
            self._scope_s[-1].add(task, name)
        else:
            super().add(task, name)
        
    def push_scope(self, scope):
        self._scope_s.append(scope)

    def pop_scope(self):
        self._scope_s.pop()

    def find(self, name) -> Task:
        ret = None
        for i in range(len(self._scope_s)-1, -1, -1):
            scope = self._scope_s[i]
            ret = scope.find(name)
            if ret is not None:
                break

        if ret is None:
            ret = super().find(name)

        if ret is None and name in self.pkg.task_m.keys():
            ret = self.pkg.task_m[name]

        if ret is None:
            raise Exception("Failed to find Task %s" % name)

        return ret

    def findType(self, name) -> Task:
        ret = None

        if name in self.task_m.keys():
            ret = self.task_m[name]

        if ret is None:
            for i in range(len(self._scope_s)-1, -1, -1):
                scope = self._scope_s[i]
                ret = scope.findType(name)
                if ret is not None:
                    break
        
        if ret is None:
            ret = super().findType(name)

        if ret is None and name in self.pkg.task_m.keys():
            ret = self.pkg.task_m[name]

        if ret is None:
            ret = self.loader.findType(name)
        
        if ret is None:
            raise Exception("Failed to find TaskType %s" % name)
        return ret

    def getScopeFullname(self, leaf=None) -> str:
        path = self.name
        if len(self._scope_s):
            path +=  "."
            path += ".".join([s.name for s in self._scope_s])

        if leaf is not None:
            path += "." + leaf
        return path
    

@dc.dataclass
class PackageLoader(object):
    pkg_rgy : PkgRgy = dc.field(default=None)
    marker_listeners : List[Callable] = dc.field(default_factory=list)
    _log : ClassVar = logging.getLogger("PackageLoader")
    _file_s : List[str] = dc.field(default_factory=list)
    _pkg_s : List[PackageScope] = dc.field(default_factory=list)
    _pkg_m : Dict[str, Package] = dc.field(default_factory=dict)
    _loader_scope : LoaderScope = None

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = PkgRgy.inst()

        self._loader_scope = LoaderScope(name=None, loader=self)

    def load(self, root) -> Package:
        self._log.debug("--> load %s" % root)
        ret = self._loadPackage(root, None)
        self._log.debug("<-- load %s" % root)
        return ret

    def _error(self, msg, elem):
        pass

    def _getLoc(self, elem):
        pass

    def _loadPackage(self, root, exp_pkg_name=None) -> Package:
        if root in self._file_s:
            raise Exception("recursive reference")

        if root in self._file_s:
            # TODO: should be able to unwind stack here
            raise Exception("Recursive file processing @ %s: %s" % (root, ",".join(self._file_s)))
        self._file_s.append(root)
        pkg : Package = None

        with open(root, "r") as fp:
            self._log.debug("open %s" % root)
            doc = yaml.load(fp, Loader=YamlSrcInfoLoader(root))

            if "package" not in doc.keys():
                raise Exception("Missing 'package' key in %s" % root)
            try:
                pkg_def = PackageDef(**(doc["package"]))

#                for t in pkg.tasks:
#                    t.fullname = pkg.name + "." + t.name

            except pydantic.ValidationError as e:
                e.errors()
                self._log.error("Failed to load package from %s" % root)
                raise e
            
            pkg = self._mkPackage(pkg_def, root)

        self._file_s.pop()

#        if exp_pkg_name is not None:
#            if exp_pkg_name != pkg.name:
#                raise Exception("Package name mismatch: %s != %s" % (exp_pkg_name, pkg.name))  
        return pkg

    def _mkPackage(self, pkg_def : PackageDef, root : str) -> Package:
        self._log.debug("--> _mkPackage %s" % pkg_def.name)
        pkg = Package(pkg_def, os.path.dirname(root))

        self._pkg_m[pkg.name] = pkg
        self._pkg_s.append(PackageScope(name=pkg.name, pkg=pkg, loader=self._loader_scope))
        self._loadPackageImports(pkg, pkg_def.imports, pkg.basedir)
        self._loadFragments(pkg, pkg_def.fragments, pkg.basedir)
        self._loadTasks(pkg, pkg_def.tasks, pkg.basedir)
        self._pkg_s.pop()

        self._log.debug("<-- _mkPackage %s (%s)" % (pkg_def.name, pkg.name))
        return pkg
    
    def _loadPackageImports(self, pkg, imports, basedir):
        if len(imports) > 0:
            self._log.info("Loading imported packages (basedir=%s)" % basedir)
        for imp in imports:
            self._loadPackageImport(pkg, imp)
    
    def _loadPackageImport(self, pkg, imp, basedir):
        self._log.debug("--> _loadPackageImport %s" % str(imp))
        # TODO: need to locate and load these external packages (?)
        if type(imp) == str:
            imp_path = imp
        elif imp.path is not None:
            imp_path = imp.path
        else:
            raise Exception("imp.path is none: %s" % str(imp))
        
        self._log.info("Loading imported package %s" % imp_path)

        if not os.path.isabs(imp_path):
            self._log.debug("_basedir: %s ; imp_path: %s" % (basedir, imp_path))
            imp_path = os.path.join(basedir, imp_path)
        
        # Search down the tree looking for a flow.dv file
        if os.path.isdir(imp_path):
            path = imp_path

            while path is not None and os.path.isdir(path) and not os.path.isfile(os.path.join(path, "flow.dv")):
                # Look one directory down
                next_dir = None
                for dir in os.listdir(path):
                    if os.path.isdir(os.path.join(path, dir)):
                        if next_dir is None:
                            next_dir = dir
                        else:
                            path = None
                            break
                if path is not None:
                    path = next_dir

            if path is not None and os.path.isfile(os.path.join(path, "flow.dv")):
                imp_path = os.path.join(path, "flow.dv")

        if not os.path.isfile(imp_path):
            raise Exception("Import file %s not found" % imp_path)

        self._log.info("Loading file %s" % imp_path)
            
        sub_pkg = self._loadPackage(imp_path)
        self._log.info("Loaded imported package %s" % sub_pkg.name)
        if sub_pkg.name in self._pkg_m.keys():
            raise Exception("Duplicate package %s" % sub_pkg.name)
        pkg.pkg_m[sub_pkg.name] = sub_pkg
        self._log.debug("<-- _loadPackageImport %s" % str(imp))
        pass

    def _loadFragments(self, pkg, fragments, basedir):
        for spec in fragments:
            self._loadFragmentSpec(pkg, spec, basedir)

    def _loadFragmentSpec(self, pkg, spec, basedir):
        # We're either going to have:
        # - File path
        # - Directory path

        if os.path.isfile(os.path.join(basedir, spec)):
            self._loadFragmentFile(
                pkg, 
                os.path.join(basedir, spec))
        elif os.path.isdir(os.path.join(basedir, spec)):
            self._loadFragmentDir(pkg, os.path.join(basedir, spec))
        else:
            raise Exception("Fragment spec %s not found" % spec)

    def _loadFragmentDir(self, pkg, dir):
        for file in os.listdir(dir):
            if os.path.isdir(os.path.join(dir, file)):
                self._loadFragmentDir(pkg, os.path.join(dir, file))
            elif os.path.isfile(os.path.join(dir, file)) and file == "flow.dv":
                self._loadFragmentFile(pkg, os.path.join(dir, file))

    def _loadFragmentFile(self, pkg, file):
        if file in self._file_s:
            raise Exception("Recursive file processing @ %s: %s" % (file, ", ".join(self._file_s)))
        self._file_s.append(file)

        with open(file, "r") as fp:
            doc = yaml.load(fp, Loader=YamlSrcInfoLoader)
            self._log.debug("doc: %s" % str(doc))
            if doc is not None and "fragment" in doc.keys():
                frag = FragmentDef(**(doc["fragment"]))
                basedir = os.path.dirname(file)
                pkg.fragment_def_l.append(frag)

                self._loadPackageImports(pkg, frag.imports, basedir)
                self._loadFragments(pkg, frag.fragments, basedir)
                self._loadTasks(pkg, frag.tasks, basedir)
            else:
                print("Warning: file %s is not a fragment" % file)

    def _loadTasks(self, pkg, taskdefs : List[TaskDef], basedir : str):
        # Declare first
        tasks = []
        for taskdef in taskdefs:
            if taskdef.name in pkg.task_m.keys():
                raise Exception("Duplicate task %s" % taskdef.name)
            
            # TODO: resolve 'needs'
            needs = []

            task = Task(
                name=self._getScopeFullname(taskdef.name),
                srcinfo=taskdef.srcinfo)
            tasks.append((taskdef, task))
            pkg.task_m[task.name] = task
            self._pkg_s[-1].add(task, taskdef.name)

        # Now, build out tasks
        for taskdef, task in tasks:

            if taskdef.uses is not None:
                task.uses = self._findTaskType(taskdef.uses)

            for need in taskdef.needs:
                if isinstance(need, str):
                    task.needs.append(self._findTask(need))
                elif isinstance(need, TaskDef):
                    task.needs.append(self._findTask(need.name))
                else:
                    raise Exception("Unknown need type %s" % str(type(need)))

            if taskdef.body is not None and taskdef.body.tasks is not None:
                self._pkg_s[-1].push_scope(TaskScope(name=taskdef.name))

                # Need to add subtasks from 'uses' scope?
                if task.uses is not None:
                    for st in task.uses.subtasks:
                        self._pkg_s[-1].add(st, st.leafname)

                # Build out first
                subtasks = []
                for td in taskdef.body.tasks:
                    st = Task(
                        name=self._getScopeFullname(td.name),
                        ctor=None,
                        srcinfo=td.srcinfo)
                    subtasks.append((td, st))
                    task.subtasks.append(st)
                    self._pkg_s[-1].add(st, td.name)

                # Now, resolve
                for td, st in subtasks:
                    if td.uses is not None:
                        if st.uses is None:
                            st.uses = self._findTaskType(td.uses)
                    for need in td.needs:
                        if isinstance(need, str):
                            st.needs.append(self._findTask(need))
                        elif isinstance(need, TaskDef):
                            st.needs.append(self._findTask(need.name))
                        else:
                            raise Exception("Unknown need type %s" % str(type(need)))
                task.body = taskdef.body
                self._pkg_s[-1].pop_scope()

            if task.ctor is None:
                self._mkTaskCtor(taskdef, task)

        # TODO: 

    def _findTaskType(self, name):
        return self._pkg_s[-1].findType(name)

    def _findTask(self, name):
        return self._pkg_s[-1].find(name)

    
    def _getScopeFullname(self, leaf=None):
        return self._pkg_s[-1].getScopeFullname(leaf)

    def _resolveTaskRefs(self, pkg, task):
        # Determine 
        pass

    # def _mkPackage(self, pkg : PackageDef, params : Dict[str,Any] = None) -> 'Package':
    #     self._log.debug("--> mkPackage %s" % pkg.name)
    #     ret = Package(pkg.name)

    #     self.push_package(ret, add=True)

    #     tasks_m : Dict[str,str,TaskNodeCtor]= {}

    #     for task in ret.tasks:
    #         if task.name in tasks_m.keys():
    #             raise Exception("Duplicate task %s" % task.name)
    #         tasks_m[task.name] = (task, self._basedir, ) # We'll add a TaskNodeCtor later

    #     for frag in pkg._fragment_l:
    #         for task in frag.tasks:
    #             if task.name in tasks_m.keys():
    #                 raise Exception("Duplicate task %s" % task.name)
    #             tasks_m[task.name] = (task, frag._basedir, ) # We'll add a TaskNodeCtor later

    #     # Now we have a unified map of the tasks declared in this package
    #     for name in list(tasks_m.keys()):
    #         task_i = tasks_m[name]
    #         fullname = pkg.name + "." + name
    #         if len(task_i) < 3:
    #             # Need to create the task ctor
    #             # TODO:
    #             ctor_t = self.mkTaskCtor(task_i[0], task_i[1], tasks_m)
    #             tasks_m[name] = (task_i[0], task_i[1], ctor_t)
    #         ret.tasks[name] = tasks_m[name][2]
    #         ret.tasks[fullname] = tasks_m[name][2]

    #     self.pop_package(ret)

    #     self._log.debug("<-- mkPackage %s" % pkg.name)
    #     return ret
    
    def _mkTaskCtor(self, taskdef, task):
        srcdir = os.path.dirname(task.srcinfo.file)
        self._log.debug("--> mkTaskCtor %s (srcdir: %s)" % (task.name, srcdir))

        if task.ctor is not None:
            return

        if taskdef.body is not None:
            if taskdef.body.tasks is not None:
                # Compound task
                ctor = self._mkCompoundTaskCtor(task, taskdef)
            else:
                ctor = self._mkLeafTaskCtor(task, taskdef)
        else:
            # Null task
            ctor = self._mkLeafTaskCtor(task, taskdef)
        
        task.ctor = ctor
    

    def _mkLeafTaskCtor(self, task, taskdef) -> TaskNodeCtor:
        self._log.debug("--> _mkLeafTaskCtor")
        srcdir = os.path.dirname(taskdef.srcinfo.file)
        base_ctor_t : TaskNodeCtor = None
        ctor_t : TaskNodeCtor = None
        base_params : BaseModel = None
        callable = None
#        fullname = self.name + "." + task.name
#        rundir = task.rundir

        # TODO: should we have the ctor look this up itself?
        # Want to confirm that the value can be found.
        # Defer final resolution until actual graph building (post-config)
        if taskdef.uses is not None:
            self._log.debug("Uses: %s" % taskdef.uses)
            # Find the target task
            base_task = self._findTaskType(taskdef.uses)
            if base_task.ctor is None:
                self._log.error("base-task ctor is None")

            base_ctor_t = base_task.ctor
            base_params = base_ctor_t.mkTaskParams()

            if base_ctor_t is None:
                self._log.error("Failed to load task ctor %s" % task.uses)
        else:
            self._log.debug("No 'uses' specified")

        passthrough, consumes, needs = self._getPTConsumesNeeds(taskdef, base_ctor_t)

        # Determine the implementation constructor first
        if taskdef.body is not None and taskdef.body.pytask is not None:
            # Built-in impl
            # Now, lookup the class
            self._log.debug("Use PyTask implementation")
            last_dot = taskdef.body.pytask.rfind('.')
            clsname = taskdef.body.pytask[last_dot+1:]
            modname = taskdef.body.pytask[:last_dot]

            try:
                if modname not in sys.modules:
                    if self._basedir not in sys.path:
                        sys.path.append(self._basedir)
                    mod = importlib.import_module(modname)
                else:
                    mod = sys.modules[modname]
            except ModuleNotFoundError as e:
                raise Exception("Failed to import module %s (_basedir=%s): %s" % (
                    modname, self._basedir, str(e)))
                
            if not hasattr(mod, clsname):
                raise Exception("Method %s not found in module %s" % (clsname, modname))
            callable = getattr(mod, clsname)

        # Determine if we need to use a new 
        paramT = self._getParamT(taskdef, base_params)

        # TODO:
        rundir : RundirE = RundirE.Unique
        
        if callable is not None:
            ctor_t = TaskNodeCtorTask(
                name=task.name,
                srcdir=srcdir,
                paramT=paramT, # TODO: need to determine the parameter type
                passthrough=passthrough,
                consumes=consumes,
                needs=needs, # TODO: need to determine the needs
                rundir=rundir,
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
                rundir=rundir,
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
                rundir=rundir,
                task=TaskNull)

        self._log.debug("<-- mkTaskCtor %s" % task.name)
        return ctor_t

    def _mkCompoundTaskCtor(self, task, taskdef) -> TaskNodeCtor:
        self._log.debug("--> _mkCompoundTaskCtor")
        srcdir = os.path.dirname(taskdef.srcinfo.file)
        base_ctor_t : TaskNodeCtor = None
        ctor_t : TaskNodeCtor = None
        base_params : BaseModel = None
        callable = None

        fullname = self._getScopeFullname()

        if task.uses is not None:
            self._log.debug("Uses: %s" % task.uses)
            base_ctor_t = task.uses.ctor
            base_params = base_ctor_t.mkTaskParams()

            if base_ctor_t is None:
                self._log.error("Failed to load task ctor %s" % task.uses)

        passthrough, consumes, needs = self._getPTConsumesNeeds(taskdef, base_ctor_t)

        # Determine if we need to use a new 
        paramT = self._getParamT(taskdef, base_params)

        if base_ctor_t is not None:
            ctor_t = TaskNodeCtorCompoundProxy(
                name=fullname,
                srcdir=srcdir,
                paramT=paramT,
                passthrough=passthrough,
                consumes=consumes,
                needs=needs,
                task_def=task,
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
                task_def=task)

#        for t in task.subtasks:
#            ctor_t.tasks.append(self._mkTaskCtor(t, srcdir))

        
        self._log.debug("<-- mkTaskCtor %s (%d)" % (task.name, len(ctor_t.tasks)))
        return ctor_t
    
    def _getPTConsumesNeeds(self, task : TaskDef, base_ctor_t):
        passthrough = task.passthrough
        consumes = task.consumes.copy() if isinstance(task.consumes, list) else task.consumes
        needs = [] if task.needs is None else task.needs.copy()

        if base_ctor_t is not None:
            if passthrough is None:
                passthrough = base_ctor_t.passthrough
            if consumes is None:
                consumes = base_ctor_t.consumes

        if passthrough is None:
            passthrough = PassthroughE.No
        if consumes is None:
            consumes = ConsumesE.All

        return (passthrough, consumes, needs)

    def _getParamT(self, task, base_t : BaseModel):
        self._log.debug("--> _getParamT %s" % task.name)
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

#        pkg = self.package()

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
