import os
import dataclasses as dc
import importlib
import logging
import pydantic
import sys
import yaml
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Tuple, Union
from .fragment_def import FragmentDef
from .package_def import PackageDef
from .package import Package
from .param_def import ComplexType
from .ext_rgy import ExtRgy
from .srcinfo import SrcInfo
from .task import Task
from .task_def import TaskDef, PassthroughE, ConsumesE, RundirE
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
from .type import Type
from .yaml_srcinfo_loader import YamlSrcInfoLoader

class EmptyParams(pydantic.BaseModel):
    pass

@dc.dataclass
class SymbolScope(object):
    name : str
    task_m : Dict[str,Task] = dc.field(default_factory=dict)
    type_m : Dict[str,Type] = dc.field(default_factory=dict)

    def add(self, task, name):
        self.task_m[name] = task

    def addType(self, type, name):
        self.type_m[name] = type

    def findTask(self, name) -> Task:
        if name in self.task_m.keys():
            return self.task_m[name]
        else:
            return None

    def findType(self, name) -> Type:
        if name in self.type_m.keys():
            return self.type_m[name]
        else:
            return None


@dc.dataclass
class TaskScope(SymbolScope):
    pass

@dc.dataclass
class LoaderScope(SymbolScope):
    loader : 'PackageLoader' = None
    _log : ClassVar = logging.getLogger("LoaderScope")

    def add(self, task, name):
        raise NotImplementedError("LoaderScope.add() not implemented")

    def addType(self, task, name):
        raise NotImplementedError("LoaderScope.addType() not implemented")
    
    def findTask(self, name) -> Task:
        self._log.debug("--> findTask: %s" % name)

        ret = None
        pkg = None

        # Split the name into elements
        name_elems = name.split('.')

        def find_pkg(pkg_name):
            pkg = None

            if pkg_name in self.loader._pkg_m.keys():
                pkg = self.loader._pkg_m[pkg_name]
            else:
                path = self.loader.pkg_rgy.findPackagePath(pkg_name)
                if path is not None:
                    path = os.path.normpath(path)
                    pkg = self.loader._loadPackage(path)
                    self.loader._pkg_m[pkg_name] = pkg
            if pkg is not None:
                self._log.debug("Found pkg %s (%s)" % (pkg_name, str(pkg.task_m.keys())))
            else:
                self._log.debug("Failed to find pkg %s" % pkg_name)
            
            return pkg

        if len(name_elems) > 1:
            for i in range(len(name_elems)-1, -1, -1):
                pkg_name = ".".join(name_elems[:i+1])

                pkg = find_pkg(pkg_name)
                if pkg is not None:
                    break;

        if pkg is not None and name in pkg.task_m.keys():
            ret = pkg.task_m[name]

        self._log.debug("<-- findTask: %s (%s)" % (name, str(ret)))
        
        return ret

    def findType(self, name) -> Type:
        self._log.debug("--> findType: %s" % name)
        ret = None
        pkg = None
        last_dot = name.rfind('.')
        if last_dot != -1:
            pkg_name = name[:last_dot]

            if pkg_name in self.loader._pkg_m.keys():
                pkg = self.loader._pkg_m[pkg_name]
            else:
                path = self.loader.pkg_rgy.findPackagePath(pkg_name)
                if path is not None:
                    pkg = self.loader._loadPackage(path)
                    self.loader._pkg_m[pkg_name] = pkg
            if pkg is not None and name in pkg.type_m.keys():
                ret = pkg.type_m[name]

        self._log.debug("<-- findType: %s (%s)" % (name, str(ret)))

        return ret

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

    def addType(self, type, name):
        if len(self._scope_s):
            self._scope_s[-1].addType(type, name)
        else:
            super().addType(type, name)
        
    def push_scope(self, scope):
        self._scope_s.append(scope)

    def pop_scope(self):
        self._scope_s.pop()

    def findTask(self, name) -> Task:
        self._log.debug("--> %s::findTask %s" % (self.pkg.name, name))
        ret = None
        for i in range(len(self._scope_s)-1, -1, -1):
            scope = self._scope_s[i]
            ret = scope.findTask(name)
            if ret is not None:
                break

        if ret is None:
            ret = super().findTask(name)

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
            ret = self.loader.findTask(name)

        self._log.debug("<-- %s::findTask %s (%s)" % (self.pkg.name, name, ("found" if ret is not None else "not found")))
        return ret

    def findType(self, name) -> Type:
        self._log.debug("--> %s::findType %s" % (self.pkg.name, name))
        ret = None
        for i in range(len(self._scope_s)-1, -1, -1):
            scope = self._scope_s[i]
            ret = scope.findType(name)
            if ret is not None:
                break

        if ret is None:
            ret = super().findType(name)

        if ret is None and name in self.pkg.type_m.keys():
            ret = self.pkg.type_m[name]

        if ret is None:
            for pkg in self.pkg.pkg_m.values():
                self._log.debug("Searching pkg %s for %s" % (pkg.name, name))
                if name in pkg.type_m.keys():
                    ret = pkg.type_m[name]
                    break

        if ret is None:
            self._log.debug("Searching loader for %s" % name)
            ret = self.loader.findType(name)

        self._log.debug("<-- %s::findType %s (%s)" % (self.pkg.name, name, ("found" if ret is not None else "not found")))
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
        pkg = Package(PackageDef(name="anonymous"))
        pkg.paramT = EmptyParams

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
                        if hasattr(obj, "__getitem__"):
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

        # TODO: handle 'uses' for packages
        pkg.paramT = self._getParamT(pkg_def, None)

        pkg_scope = self.package_scope()
        if pkg_scope is not None:
            self._log.debug("Add self (%s) as a subpkg of %s" % (pkg.name, pkg_scope.pkg.name))
            pkg_scope.pkg.pkg_m[pkg.name] = pkg

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
            typedefs = pkg_def.types.copy()

            self._loadFragments(pkg, pkg_def.fragments, pkg.basedir, taskdefs, typedefs)

            self._loadTypes(pkg, typedefs)
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
            for root in (basedir, os.path.dirname(self._file_s[0])):
                self._log.debug("Search basedir: %s ; imp_path: %s" % (root, imp_path))

                resolved_path = self._findFlowDvInDir(root, imp_path)

                if resolved_path is not None and os.path.isfile(resolved_path):
                    self._log.debug("Found root file: %s" % resolved_path)
                    imp_path = resolved_path
                    break

        if not os.path.isfile(imp_path):
            self.error("Import file %s not found" % imp_path, pkg.srcinfo)
            # Don't want to error out 
            return
#            raise Exception("Import file %s not found" % imp_path)

        if imp_path in self._pkg_path_m.keys():
            sub_pkg = self._pkg_path_m[imp_path]
        else:
            self._log.info("Loading imported file %s" % imp_path)
            imp_path = os.path.normpath(imp_path)
            sub_pkg = self._loadPackage(imp_path)
            self._log.info("Loaded imported package %s" % sub_pkg.name)

        pkg.pkg_m[sub_pkg.name] = sub_pkg
        self._log.debug("<-- _loadPackageImport %s" % str(imp))

    def _findFlowDvInDir(self, base, leaf):
        """Search down the tree looking for a flow.dv file"""
        self._log.debug("--> _findFlowDvInDir (%s, %s)" % (base, leaf))
        imp_path = None
        if os.path.isfile(os.path.join(base, leaf)):
            imp_path = os.path.join(base, leaf)
            self._log.debug("Found: %s" % imp_path)
        elif os.path.isdir(os.path.join(base, leaf)):
            path = os.path.join(base, leaf)

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
                self._log.debug("Found: %s" % imp_path)
        self._log.debug("<-- _findFlowDvInDir %s" % imp_path)
        return imp_path

    def _loadFragments(self, pkg, fragments, basedir, taskdefs, typedefs):
        for spec in fragments:
            self._loadFragmentSpec(pkg, spec, basedir, taskdefs, typedefs)

    def _loadFragmentSpec(self, pkg, spec, basedir, taskdefs, typedefs):
        # We're either going to have:
        # - File path
        # - Directory path

        if os.path.isfile(os.path.join(basedir, spec)):
            self._loadFragmentFile(
                pkg, 
                os.path.join(basedir, spec),
                taskdefs, typedefs)
        elif os.path.isdir(os.path.join(basedir, spec)):
            self._loadFragmentDir(pkg, os.path.join(basedir, spec), taskdefs, typedefs)
        else:
            raise Exception("Fragment spec %s not found" % spec)

    def _loadFragmentDir(self, pkg, dir, taskdefs, typedefs):
        for file in os.listdir(dir):
            if os.path.isdir(os.path.join(dir, file)):
                self._loadFragmentDir(pkg, os.path.join(dir, file), taskdefs, typedefs)
            elif os.path.isfile(os.path.join(dir, file)) and file == "flow.dv":
                self._loadFragmentFile(pkg, os.path.join(dir, file), taskdefs, typedefs)

    def _loadFragmentFile(self, pkg, file, taskdefs, typedefs):
        if file in self._file_s:
            raise Exception("Recursive file processing @ %s: %s" % (file, ", ".join(self._file_s)))
        self._file_s.append(file)

        with open(file, "r") as fp:
            doc = yaml.load(fp, Loader=YamlSrcInfoLoader(file))
            self._log.debug("doc: %s" % str(doc))
            if doc is not None and "fragment" in doc.keys():
                try:
                    frag = FragmentDef(**(doc["fragment"]))
                    basedir = os.path.dirname(file)
                    pkg.fragment_def_l.append(frag)

                    self._loadPackageImports(pkg, frag.imports, basedir)
                    self._loadFragments(pkg, frag.fragments, basedir, taskdefs, typedefs)
                    taskdefs.extend(frag.tasks)
                    typedefs.extend(frag.types)
                except pydantic.ValidationError as e:
                    print("Errors: %s" % file)
                    error_paths = []
                    loc = None
                    for ee in e.errors():
#                    print("  Error: %s" % str(ee))
                        obj = doc["fragment"]
                        loc = None
                        for el in ee['loc']:
                            print("el: %s" % str(el))
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
                            marker = TaskMarker(
                                msg=ee['msg'], 
                                severity=SeverityE.Error,
                                loc=TaskMarkerLoc(path=file))
                        self.marker(marker)
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
                package=pkg,
                srcinfo=taskdef.srcinfo)

            if taskdef.iff is not None:
                task.iff = taskdef.iff

            tasks.append((taskdef, task))
            pkg.task_m[task.name] = task
            self._pkg_s[-1].add(task, taskdef.name)

        # Now, build out tasks
        for taskdef, task in tasks:

            if taskdef.uses is not None:
                task.uses = self._findTaskOrType(taskdef.uses)

                if task.uses is None:
                    self.error("failed to resolve task-uses %s" % taskdef.uses, taskdef.srcinfo)
                    continue
            
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
                    self.error("failed to find task %s" % need, taskdef.srcinfo)
                    raise Exception("Failed to find task %s" % need)
                task.needs.append(nt)

            # Determine how to implement this task
            if taskdef.body is not None and len(taskdef.body) > 0:
                self._mkTaskBody(task, taskdef)
            elif taskdef.run is not None:
                task.run = taskdef.run
                if taskdef.shell is not None:
                    task.shell = taskdef.shell
            elif taskdef.pytask is not None: # Deprecated case
                task.run = taskdef.pytask
                task.shell = "pytask"
            elif task.uses is not None and isinstance(task.uses, Task) and task.uses.run is not None:
                task.run = task.uses.run
                task.shell = task.uses.shell

        self._log.debug("<-- _loadTasks %s" % pkg.name)

    def _loadTypes(self, pkg, typedefs):
        self._log.debug("--> _loadTypes")
        types = []
        for td in typedefs:
            tt = Type(
                name=self._getScopeFullname(td.name),
                doc=td.doc,
                srcinfo=td.srcinfo)
            pkg.type_m[tt.name] = tt
            self._pkg_s[-1].addType(tt, td.name)
            types.append((td, tt))
        
        # Now, resolve 'uses' and build out
        for td,tt in types:
            if td.uses is not None:
                tt.uses = self._findType(td.uses)
                if tt.uses is None:
                    raise Exception("Failed to find type %s" % td.uses)
            tt.paramT = self._getParamT(
                td, 
                tt.uses.paramT if tt.uses is not None else None,
                typename=tt.name,
                is_type=True)
        self._log.debug("<-- _loadTypes")
        pass

    def _mkTaskBody(self, task, taskdef):
        self._pkg_s[-1].push_scope(TaskScope(name=taskdef.name))
        pkg = self.package_scope()

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
                package=pkg.pkg,
                srcinfo=td.srcinfo)

            if td.iff is not None:
                st.iff = td.iff

            subtasks.append((td, st))
            task.subtasks.append(st)
            self._pkg_s[-1].add(st, td.name)

        # Now, resolve references
        for td, st in subtasks:
            if td.uses is not None:
                if st.uses is None:
                    st.uses = self._findTask(td.uses)
                    if st.uses is None:
                        self.error("failed to find task %s" % td.uses, td.srcinfo)
#                        raise Exception("Failed to find task %s" % td.uses)

            passthrough, consumes, rundir = self._getPTConsumesRundir(td, st.uses)

            st.passthrough = passthrough
            st.consumes = consumes
            st.rundir = rundir

            for need in td.needs:
                nn = None
                if isinstance(need, str):
                    nn = self._findTask(need)
                elif isinstance(need, TaskDef):
                    nn = self._findTask(need.name)
                else:
                    raise Exception("Unknown need type %s" % str(type(need)))
                
                if nn is None:
                    self.error("failed to find task %s" % need, td.srcinfo)
#                    raise Exception("failed to find task %s" % need)
                
                st.needs.append(nn)

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

    def _findType(self, name):
        if len(self._pkg_s):
            return self._pkg_s[-1].findType(name)
        else:
            return self._loader_scope.findType(name)

    def _findTask(self, name):
        if len(self._pkg_s):
            return self._pkg_s[-1].findTask(name)
        else:
            return self._loader_scope.findTask(name)
        
    def _findTaskOrType(self, name):
        self._log.debug("--> _findTaskOrType %s" % name)
        uses = self._findTask(name)

        if uses is None:
            uses = self._findType(name)

        self._log.debug("<-- _findTaskOrType %s (%s)" % (name, ("found" if uses is not None else "not found")))
        return uses

    
    def _getScopeFullname(self, leaf=None):
        return self._pkg_s[-1].getScopeFullname(leaf)

    def _resolveTaskRefs(self, pkg, task):
        # Determine 
        pass

    def _getPTConsumesRundir(self, taskdef : TaskDef, base_t : Union[Task,Type]):
        self._log.debug("_getPTConsumesRundir %s" % taskdef.name)
        passthrough = taskdef.passthrough
        consumes = taskdef.consumes.copy() if isinstance(taskdef.consumes, list) else taskdef.consumes
        rundir = taskdef.rundir
#        needs = [] if task.needs is None else task.needs.copy()

        if base_t is not None and isinstance(base_t, Task):
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

    def _getParamT(
            self, 
            taskdef, 
            base_t : BaseModel, 
            typename=None,
            is_type=False):
        self._log.debug("--> _getParamT %s" % taskdef.name)
        # Get the base parameter type (if available)
        # We will build a new type with updated fields

        ptype_m = {
            "str" : str,
            "int" : int,
            "float" : float,
            "bool" : bool,
            "list" : List,
            "map" : Dict
        }
        pdflt_m = {
            "str" : "",
            "int" : 0,
            "float" : 0.0,
            "bool" : False,
            "list" : [],
            "map" : {}
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
            if is_type:
                field_m["src"] = (str, "")
                field_m["seq"] = (int, "")

        for p in taskdef.params.keys():
            param = taskdef.params[p]
            self._log.debug("param: %s %s (%s)" % (p, str(param), str(type(param))))
            if hasattr(param, "type") and param.type is not None:
                if isinstance(param.type, ComplexType):
                    if param.type.list is not None:
                        ptype = List
                        pdflt = []
                    elif param.type.map is not None:
                        ptype = Dict
                        pdflt = {}
                    else:
                        raise Exception("Complex type %s not supported" % str(param.type))
                    pass
                else:
                    ptype_s = param.type
                    if ptype_s not in ptype_m.keys():
                        raise Exception("Unknown type %s" % ptype_s)
                    ptype = ptype_m[ptype_s]
                    pdflt = pdflt_m[ptype_s]

                if p in field_m.keys():
                    raise Exception("Duplicate field %s" % p)
                if param.value is not None:
                    field_m[p] = (ptype, param.value)
                else:
                    field_m[p] = (ptype, pdflt)
                self._log.debug("Set param=%s to %s" % (p, str(field_m[p][1])))
            else:
                if p in field_m.keys():
                    if type(param) != dict:
                        value = param
                    elif "value" in param.keys():
                        value = param["value"]
                    else:
                        raise Exception("No value specified for param %s: %s" % (
                            p, str(param)))
                    field_m[p] = (field_m[p][0], value)
                    self._log.debug("Set param=%s to %s" % (p, str(field_m[p][1])))
                else:
                    self.error("Field %s not found in task %s" % (p, taskdef.name), taskdef.srcinfo)

        if typename is not None:
            field_m["type"] = (str, typename)
            params_t = pydantic.create_model(typename, **field_m)
        else:
            params_t = pydantic.create_model("Task%sParams" % taskdef.name, **field_m)

        self._log.debug("== Params")
        for name,info in params_t.model_fields.items():
            self._log.debug("  %s: %s" % (name, str(info)))

        self._log.debug("<-- _getParamT %s" % taskdef.name)
        return params_t
    
    def error(self, msg, loc : SrcInfo =None):
        if loc is not None:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error,
                                loc=TaskMarkerLoc(path=loc.file, line=loc.lineno, pos=loc.linepos))
        else:
            marker = TaskMarker(msg=msg, severity=SeverityE.Error)
        self.marker(marker)

    def marker(self, marker):
        for l in self.marker_listeners:
            l(marker)
