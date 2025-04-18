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
from .ext_rgy import ExtRgy
from .srcinfo import SrcInfo
from .task import Task
from .task_def import TaskDef, PassthroughE, ConsumesE, RundirE
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
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
        pkg = None
        if last_dot != -1:
            pkg_name = name[:last_dot]
            task_name = name[last_dot+1:]

            if pkg_name in self.loader._pkg_m.keys():
                pkg = self.loader._pkg_m[pkg_name]
            else:
                path = self.loader.pkg_rgy.findPackagePath(pkg_name)
                if path is not None:
                    path = os.path.normpath(path)
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
    _log : ClassVar = logging.getLogger("PackageScope")

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
        self._log.debug("--> %s::find %s" % (self.pkg.name, name))
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
            for pkg in self.pkg.pkg_m.values():
                self._log.debug("Searching pkg %s for %s" % (pkg.name, name))
                if name in pkg.task_m.keys():
                    ret = pkg.task_m[name]
                    break

        if ret is None:
            self._log.debug("Searching loader for %s" % name)
            ret = self.loader.findType(name)

        self._log.debug("<-- %s::find %s (%s)" % (self.pkg.name, name, ("found" if ret is not None else "not found")))
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
    pkg_rgy : ExtRgy = dc.field(default=None)
    marker_listeners : List[Callable] = dc.field(default_factory=list)
    _log : ClassVar = logging.getLogger("PackageLoader")
    _file_s : List[str] = dc.field(default_factory=list)
    _pkg_s : List[PackageScope] = dc.field(default_factory=list)
    _pkg_m : Dict[str, Package] = dc.field(default_factory=dict)
    _pkg_path_m : Dict[str, Package] = dc.field(default_factory=dict)
    _loader_scope : LoaderScope = None

    def __post_init__(self):
        if self.pkg_rgy is None:
            self.pkg_rgy = ExtRgy.inst()

        self._loader_scope = LoaderScope(name=None, loader=self)

    def load(self, root) -> Package:
        self._log.debug("--> load %s" % root)
        root = os.path.normpath(root)
        ret = self._loadPackage(root, None)
        self._log.debug("<-- load %s" % root)
        return ret
    
    def load_rgy(self, name) -> Package:
        self._log.debug("--> load_rgy %s" % name)
        pkg = Package(None)

        name = name if isinstance(name, list) else [name]

        for nn in name:
            pp = self.pkg_rgy.findPackagePath(nn)
            if pp is None:
                raise Exception("Package %s not found" % nn)
            root = os.path.normpath(pp)
            pp_n = self._loadPackage(pp)
            pkg.pkg_m[pp_n.name] = pp_n
        self._log.debug("<-- load_rgy %s" % name)
        return pkg

    def _error(self, msg, elem):
        pass

    def _getLoc(self, elem):
        pass

    def package_scope(self):
        ret = None
        for i in range(len(self._pkg_s)-1, -1, -1):
            scope = self._pkg_s[i]
            if isinstance(scope, PackageScope):
                ret = scope
                break
        return ret

    def _loadPackage(self, root, exp_pkg_name=None) -> Package:
        if root in self._file_s:
            raise Exception("recursive reference")

        if root in self._file_s:
            # TODO: should be able to unwind stack here
            raise Exception("Recursive file processing @ %s: %s" % (root, ",".join(self._file_s)))
        self._file_s.append(root)
        pkg : Package = None
        pkg_def : PackageDef = None

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
#                print("Errors: %s" % root)
                error_paths = []
                loc = None
                loc_s = ""
                for ee in e.errors():
#                    print("  Error: %s" % str(ee))
                    obj = doc["package"]
                    loc = None
                    print("Errors: %s" % str(ee))
                    for el in ee['loc']:
#                        print("el: %s" % str(el))
                        if loc_s != "":
                            loc_s += "." + str(el)
                        else:
                            loc_s = str(el)
                        obj = obj[el]
                        if type(obj) == dict and 'srcinfo' in obj.keys():
                            loc = obj['srcinfo']
                    if loc is not None:
                        marker_loc = TaskMarkerLoc(path=loc['file'])
                        if 'lineno' in loc.keys():
                            marker_loc.line = loc['lineno']
                        if 'linepos' in loc.keys():
                            marker_loc.pos = loc['linepos']

                        marker = TaskMarker(
                            msg=("%s (in %s)" % (ee['msg'], str(ee['loc'][-1]))),
                            severity=SeverityE.Error,
                            loc=marker_loc)
                    else:
                        marker_loc = TaskMarkerLoc(path=root)   
                        marker = TaskMarker(
                            msg=("%s (at '%s')" % (ee['msg'], loc_s)),
                            severity=SeverityE.Error,
                            loc=marker_loc)
                    self.marker(marker)

            if pkg_def is not None:
                pkg = self._mkPackage(pkg_def, root)

        self._file_s.pop()

        self._pkg_path_m[root] = pkg

        return pkg

    def _mkPackage(self, pkg_def : PackageDef, root : str) -> Package:
        self._log.debug("--> _mkPackage %s" % pkg_def.name)
        pkg = Package(
            pkg_def, 
            os.path.dirname(root),
            srcinfo=SrcInfo(file=root))

        if pkg.name in self._pkg_m.keys():
            epkg = self._pkg_m[pkg.name]
            if epkg.srcinfo.file != pkg.srcinfo.file:
                self.error("Package %s already loaded from %s. Duplicate defined in %s" % (
                    pkg.name, epkg.srcinfo.file, pkg.srcinfo.file))
        else:
            pkg_scope = self.package_scope()
            if pkg_scope is not None:
                self._log.debug("Add self (%s) as a subpkg of %s" % (pkg.name, pkg_scope.pkg.name))
                pkg_scope.pkg.pkg_m[pkg.name] = pkg

            self._pkg_m[pkg.name] = pkg
            self._pkg_s.append(PackageScope(name=pkg.name, pkg=pkg, loader=self._loader_scope))
            # Imports are loaded first
            self._loadPackageImports(pkg, pkg_def.imports, pkg.basedir)

            taskdefs = pkg_def.tasks.copy()

            self._loadFragments(pkg, pkg_def.fragments, pkg.basedir, taskdefs)

            self._loadTasks(pkg, taskdefs, pkg.basedir)

            self._pkg_s.pop()

        self._log.debug("<-- _mkPackage %s (%s)" % (pkg_def.name, pkg.name))
        return pkg
    
    def _loadPackageImports(self, pkg, imports, basedir):
        self._log.debug("--> _loadPackageImports %s" % str(imports))
        if len(imports) > 0:
            self._log.info("Loading imported packages (basedir=%s)" % basedir)
        for imp in imports:
            self._log.debug("Loading import %s" % imp)
            self._loadPackageImport(pkg, imp, basedir)
        self._log.debug("<-- _loadPackageImports %s" % str(imports))
    
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

        if imp_path in self._pkg_path_m.keys():
            sub_pkg = self._pkg_path_m[imp_path]
        else:
            self._log.info("Loading imported file %s" % imp_path)
            imp_path = os.path.normpath(imp_path)
            sub_pkg = self._loadPackage(imp_path)
            self._log.info("Loaded imported package %s" % sub_pkg.name)

        pkg.pkg_m[sub_pkg.name] = sub_pkg
        self._log.debug("<-- _loadPackageImport %s" % str(imp))
        pass

    def _loadFragments(self, pkg, fragments, basedir, taskdefs):
        for spec in fragments:
            self._loadFragmentSpec(pkg, spec, basedir, taskdefs)

    def _loadFragmentSpec(self, pkg, spec, basedir, taskdefs):
        # We're either going to have:
        # - File path
        # - Directory path

        if os.path.isfile(os.path.join(basedir, spec)):
            self._loadFragmentFile(
                pkg, 
                os.path.join(basedir, spec),
                taskdefs)
        elif os.path.isdir(os.path.join(basedir, spec)):
            self._loadFragmentDir(pkg, os.path.join(basedir, spec), taskdefs)
        else:
            raise Exception("Fragment spec %s not found" % spec)

    def _loadFragmentDir(self, pkg, dir, taskdefs):
        for file in os.listdir(dir):
            if os.path.isdir(os.path.join(dir, file)):
                self._loadFragmentDir(pkg, os.path.join(dir, file), taskdefs)
            elif os.path.isfile(os.path.join(dir, file)) and file == "flow.dv":
                self._loadFragmentFile(pkg, os.path.join(dir, file), taskdefs)

    def _loadFragmentFile(self, pkg, file, taskdefs):
        if file in self._file_s:
            raise Exception("Recursive file processing @ %s: %s" % (file, ", ".join(self._file_s)))
        self._file_s.append(file)

        with open(file, "r") as fp:
            doc = yaml.load(fp, Loader=YamlSrcInfoLoader(file))
            self._log.debug("doc: %s" % str(doc))
            if doc is not None and "fragment" in doc.keys():
                frag = FragmentDef(**(doc["fragment"]))
                basedir = os.path.dirname(file)
                pkg.fragment_def_l.append(frag)

                self._loadPackageImports(pkg, frag.imports, basedir)
                self._loadFragments(pkg, frag.fragments, basedir, taskdefs)
                taskdefs.extend(frag.tasks)
            else:
                print("Warning: file %s is not a fragment" % file)

    def getTask(self, name) -> Task:
        task = self._findTask(name)
        return task

    def _loadTasks(self, pkg, taskdefs : List[TaskDef], basedir : str):
        self._log.debug("--> _loadTasks %s" % pkg.name)
        # Declare first
        tasks = []
        for taskdef in taskdefs:
            if taskdef.name in pkg.task_m.keys():
                raise Exception("Duplicate task %s" % taskdef.name)
            
            # TODO: resolve 'needs'
            needs = []

            if taskdef.srcinfo is None:
                raise Exception("null srcinfo")
            self._log.debug("Create task %s in pkg %s" % (self._getScopeFullname(taskdef.name), pkg.name))
            desc = taskdef.desc if taskdef.desc is not None else ""
            doc = taskdef.doc if taskdef.doc is not None else ""
            task = Task(
                name=self._getScopeFullname(taskdef.name),
                desc=desc,
                doc=doc,
                srcinfo=taskdef.srcinfo)
            tasks.append((taskdef, task))
            pkg.task_m[task.name] = task
            self._pkg_s[-1].add(task, taskdef.name)

        # Now, build out tasks
        for taskdef, task in tasks:

            if taskdef.uses is not None:
                task.uses = self._findTaskType(taskdef.uses)

                if task.uses is None:
                    raise Exception("Failed to link task %s" % taskdef.uses)
            
            passthrough, consumes, rundir = self._getPTConsumesRundir(taskdef, task.uses)

            task.passthrough = passthrough
            task.consumes = consumes
            task.rundir = rundir

            task.paramT = self._getParamT(
                taskdef, 
                task.uses.paramT if task.uses is not None else None)

            for need in taskdef.needs:
                nt = None
                if isinstance(need, str):
                    nt = self._findTask(need)
                elif isinstance(need, TaskDef):
                    nt = self._findTask(need.name)
                else:
                    raise Exception("Unknown need type %s" % str(type(need)))
                
                if nt is None:
                    raise Exception("Failed to find task %s" % need)
                task.needs.append(nt)

            if taskdef.body is not None and len(taskdef.body) > 0:
                self._mkTaskBody(task, taskdef)
            elif taskdef.run is not None:
                task.run = taskdef.run
                if taskdef.shell is not None:
                    task.shell = taskdef.shell
            elif taskdef.pytask is not None: # Deprecated case
                task.run = taskdef.pytask
                task.shell = "pytask"
            elif task.uses is not None and task.uses.run is not None:
                task.run = task.uses.run
                task.shell = task.uses.shell

        self._log.debug("<-- _loadTasks %s" % pkg.name)

    def _mkTaskBody(self, task, taskdef):
        self._pkg_s[-1].push_scope(TaskScope(name=taskdef.name))

        # Need to add subtasks from 'uses' scope?
        if task.uses is not None:
            for st in task.uses.subtasks:
                self._pkg_s[-1].add(st, st.leafname)

        # Build out first
        subtasks = []
        for td in taskdef.body:
            if td.srcinfo is None:
                raise Exception("null srcinfo")

            
            doc = td.doc if td.doc is not None else ""
            desc = td.desc if td.desc is not None else ""
            st = Task(
                name=self._getScopeFullname(td.name),
                desc=desc,
                doc=doc,
                srcinfo=td.srcinfo)
            subtasks.append((td, st))
            task.subtasks.append(st)
            self._pkg_s[-1].add(st, td.name)

        # Now, resolve references
        for td, st in subtasks:
            if td.uses is not None:
                if st.uses is None:
                    st.uses = self._findTaskType(td.uses)
                    if st.uses is None:
                        raise Exception("Failed to find task %s" % td.uses)

            passthrough, consumes, rundir = self._getPTConsumesRundir(td, st.uses)

            st.passthrough = passthrough
            st.consumes = consumes
            st.rundir = rundir

            for need in td.needs:
                if isinstance(need, str):
                    st.needs.append(self._findTask(need))
                elif isinstance(need, TaskDef):
                    st.needs.append(self._findTask(need.name))
                else:
                    raise Exception("Unknown need type %s" % str(type(need)))

            if td.body is not None and len(td.body) > 0:
                self._mkTaskBody(st, td)
            elif td.run is not None:
                st.run = td.run
                st.shell = getattr(td, "shell", None)
            elif td.pytask is not None:
                st.run = td.pytask
                st.shell = "pytask"
            elif st.uses is not None and st.uses.run is not None:
                st.run = st.uses.run
                st.shell = st.uses.shell

            st.paramT = self._getParamT(
                td, 
                st.uses.paramT if st.uses is not None else None)

        for td, st in subtasks:
            # TODO: assess passthrough, consumes, needs, and rundir
            # with respect to 'uses'
            pass

        self._pkg_s[-1].pop_scope()

    def _findTaskType(self, name):
        if len(self._pkg_s):
            return self._pkg_s[-1].find(name)
        else:
            return self._loader_scope.find(name)

    def _findTask(self, name):
        if len(self._pkg_s):
            return self._pkg_s[-1].find(name)
        else:
            return self._loader_scope.find(name)

    
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
    

    
    def _getPTConsumesRundir(self, taskdef : TaskDef, base_t : Task):
        self._log.debug("_getPTConsumesRundir %s" % taskdef.name)
        passthrough = taskdef.passthrough
        consumes = taskdef.consumes.copy() if isinstance(taskdef.consumes, list) else taskdef.consumes
        rundir = taskdef.rundir
#        needs = [] if task.needs is None else task.needs.copy()

        if base_t is not None:
            if passthrough is None:
                passthrough = base_t.passthrough
            if consumes is None:
                consumes = base_t.consumes
            if rundir is None:
                rundir = base_t.rundir

        if passthrough is None:
            passthrough = PassthroughE.Unused
        if consumes is None:
            consumes = ConsumesE.All


        return (passthrough, consumes, rundir)

    def _getParamT(self, taskdef, base_t : BaseModel):
        self._log.debug("--> _getParamT %s" % taskdef.name)
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
            base_o = base_t()
            self._log.debug("Base type: %s" % str(base_t))
            for name,f in base_t.model_fields.items():
                ff : dc.Field = f
                fields.append(f)
                if not hasattr(base_o, name):
                    raise Exception("Base type %s does not have field %s" % (str(base_t), name))
                field_m[name] = (f.annotation, getattr(base_o, name))
        else:
            self._log.debug("No base type")

        for p in taskdef.params.keys():
            param = taskdef.params[p]
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

        params_t = pydantic.create_model("Task%sParams" % taskdef.name, **field_m)

        self._log.debug("== Params")
        for name,info in params_t.model_fields.items():
            self._log.debug("  %s: %s" % (name, str(info)))

        self._log.debug("<-- _getParamT %s" % taskdef.name)
        return params_t
    
    def error(self, msg, loc=None):
        if loc is not None:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error,
                                loc=loc)
        else:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error)
        self.marker(marker)

    def marker(self, marker):
        for l in self.marker_listeners:
            l(marker)
