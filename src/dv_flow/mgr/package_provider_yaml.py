
import dataclasses as dc
import logging
import os
import pydantic
import yaml
from typing import ClassVar, Dict, List, Optional, Union
from .fragment_def import FragmentDef
from .loader_scope import LoaderScope
from .marker_listener import MarkerListener
from .package import Package
from .package_loader import PackageLoader
from .package_def import PackageDef
from .package_provider import PackageProvider
from .package_scope import PackageScope
from .param_def import ComplexType
from .srcinfo import SrcInfo
from .symbol_scope import SymbolScope
from .task import Task, Strategy, StrategyGenerate
from .task_def import TaskDef, ConsumesE, RundirE, PassthroughE, StrategyDef
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
from .type import Type
from .yaml_srcinfo_loader import YamlSrcInfoLoader

@dc.dataclass
class PackageProviderYaml(PackageProvider):
    path : str
    pkg : Optional[Package] = None
    _pkg_s : List[PackageScope] = dc.field(default_factory=list)
    _log : ClassVar[logging.Logger] = logging.getLogger("PackageProviderYaml")

    def getPackageNames(self, loader : PackageLoader) -> List[str]: 
        if self.pkg is None:
            self.pkg = Package(
                basedir=os.path.dirname(self.path),
                srcinfo=SrcInfo(file=self.path))
            self._loadPackage(self.pkg, self.path, loader)
        return [self.pkg.name]

    def getPackage(self, name : str, loader : PackageLoader) -> Package: 
        if self.pkg is None:
            self.pkg = Package(
                basedir=os.path.dirname(self.path),
                srcinfo=SrcInfo(file=self.path))
            self._loadPackage(self.pkg, self.path, loader)
        if name != self.pkg.name:
            raise Exception("Internal error: this provider only handles %s:%s" % (
                self.pkg.name, self.path))
        return self.pkg
    
    def findPackage(self, name : str, loader : PackageLoader) -> Optional[Package]:
        if self.pkg is None:
            self.pkg = Package(
                basedir=os.path.dirname(self.path),
                srcinfo=SrcInfo(file=self.path))
            self.pkg = self._loadPackage(self.pkg, self.path, loader)
        if name == self.pkg.name:
            return self.getPackage(name, loader)
        return None
    
    def _loadPackage(self, 
                     pkg : Package,
                     root, 
                     loader : PackageLoader,
                     exp_pkg_name=None) -> Package:
        loader.pushPath(root)

        pkg_def : Optional[PackageDef] = None

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
                            try:
                                obj = obj[el]
                            except KeyError as ke:
                                pass
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
                    loader.marker(marker)

            if pkg_def is not None:
                self._mkPackage(pkg, pkg_def, root, loader)

        loader.popPath()

        self._pkg_path_m[root] = pkg

        return pkg
    
    def _mkPackage(self, 
                   pkg : Package,
                   pkg_def : PackageDef, 
                   root : str,
                   loader : PackageLoader) -> Package:
        self._log.debug("--> _mkPackage %s" % pkg_def.name)

        pkg.name = pkg_def.name

        # TODO: handle 'uses' for packages
        pkg.paramT = self._getParamT(pkg_def, None)

        # Apply any overrides from above

        # Now, apply these overrides to the 
        for target,override in pkg_def.overrides.items():
            # TODO: expand target, override
            pass

        pkg_scope = self.package_scope()
        if pkg_scope is not None:
            self._log.debug("Add self (%s) as a subpkg of %s" % (pkg.name, pkg_scope.pkg.name))
            pkg_scope.pkg.pkg_m[pkg.name] = pkg

        if loader.findPackage(pkg.name, loader) is not None:
            epkg = loader.getPackage(pkg.name, loader)
            if epkg.srcinfo.file != pkg.srcinfo.file:
                self.error("Package %s already loaded from %s. Duplicate defined in %s" % (
                    pkg.name, epkg.srcinfo.file, pkg.srcinfo.file))
        else:
            pkg_scope = self.package_scope()
            if pkg_scope is not None:
                self._log.debug("Add self (%s) as a subpkg of %s" % (pkg.name, pkg_scope.pkg.name))
                pkg_scope.pkg.pkg_m[pkg.name] = pkg

            self.push_package_scope(PackageScope(
                name=pkg.name, 
                pkg=pkg, 
                loader=LoaderScope(name=None, loader=loader)))

            # Imports are loaded first
            self._loadPackageImports(pkg, pkg_def.imports, pkg.basedir)

            taskdefs = pkg_def.tasks.copy()
            typedefs = pkg_def.types.copy()

            self._loadFragments(pkg, pkg_def.fragments, pkg.basedir, taskdefs, typedefs)

            self._loadTypes(pkg, loader, typedefs)
            self._loadTasks(pkg, loader, taskdefs, pkg.basedir)

            self.pop_package_scope()

        # Apply feeds after all tasks are loaded
        for fed_name, feeding_tasks in self._feeds_map.items():
            fed_task = self._findTask(fed_name, loader)
            if fed_task is not None:
                for feeding_task in feeding_tasks:
                    # Only add if not already present
                    if all(
                        not (isinstance(n, tuple) and n[0] == feeding_task) and n != feeding_task
                        for n in fed_task.needs):
                        fed_task.needs.append(feeding_task)

        self._log.debug("<-- _mkPackage %s (%s)" % (pkg_def.name, pkg.name))
        return pkg
    
    def _findType(self, name, loader):
        if len(self._pkg_s):
            return self._pkg_s[-1].findType(name)
        else:
            return loader.findType(name)

    def _findTask(self, name, loader):
        ret = None
        if len(self._pkg_s):
            ret = self._pkg_s[-1].findTask(name)
        else:
            ret = loader.findTask(name)
        return ret

    def _findTaskOrType(self, name, loader):
        self._log.debug("--> _findTaskOrType %s" % name)
        uses = self._findTask(name, loader)

        if uses is None:
            uses = self._findType(name, loader)
            if uses is not None and uses.typedef:
                self._elabType(uses, loader)
                pass
        elif uses.taskdef:
            self._elabTask(uses, loader)

        self._log.debug("<-- _findTaskOrType %s (%s)" % (name, ("found" if uses is not None else "not found")))
        return uses
    
    def _loadPackageImports(self, pkg, imports, basedir):
        self._log.debug("--> _loadPackageImports %s" % str(imports))
        if len(imports) > 0:
            self._log.info("Loading imported packages (basedir=%s)" % basedir)
        for imp in imports:
            self._log.debug("Loading import %s" % imp)
            self._loadPackageImport(pkg, imp, basedir)
        self._log.debug("<-- _loadPackageImports %s" % str(imports))
    
    def _loadPackageImport(self, 
                           loader : PackageLoader,
                           pkg : Package, 
                           imp : Union[str,object], 
                           basedir : str):
        self._log.debug("--> _loadPackageImport %s" % str(imp))
        # TODO: need to locate and load these external packages (?)
        if type(imp) == str:
            imp_path = imp
        elif imp.path is not None:
            imp_path = imp.path
        else:
            raise Exception("imp.path is none: %s" % str(imp))
        
        self._log.info("Loading imported package %s" % imp_path)

        imp_path = loader.evalExpr(imp_path)

        if not os.path.isabs(imp_path):
            for root in (basedir, os.path.dirname(self._file_s[0])):
                self._log.debug("Search basedir: %s ; imp_path: %s" % (root, imp_path))

                resolved_path = self._findFlowDvInDir(os.path.join(root, imp_path))

                if resolved_path is not None and os.path.isfile(resolved_path):
                    self._log.debug("Found root file: %s" % resolved_path)
                    imp_path = resolved_path
                    break
        else:
            # absolute path. 
            if os.path.isdir(imp_path):
                imp_path = self._findFlowDvInDir(imp_path)

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

    def _findFlowDvInDir(self, base):
        """Search down the tree looking for a <flow.dv> file"""
        self._log.debug("--> _findFlowDvInDir (%s)" % base)
        imp_path = None
        if os.path.isfile(base):
            imp_path = base
        else:
            for name in ("flow.dv", "flow.yaml", "flow.yml"):
                self._log.debug("Searching for %s in %s" % (name, base))
                if os.path.isfile(os.path.join(base, name)):
                    imp_path = os.path.join(base, name)
                    break
            if imp_path is None and os.path.isdir(base):
                imp_path = self._findFlowDvSubdir(base)
        self._log.debug("<-- _findFlowDvInDir %s" % imp_path)
        return imp_path
    
    def _findFlowDvSubdir(self, dir):
        ret = None
        # Search deeper
        ret = None
        for subdir in os.listdir(dir):
            for name in ("flow.dv", "flow.yaml", "flow.yml"):
                if os.path.isfile(os.path.join(dir, subdir, name)):
                    ret = os.path.join(dir, subdir, name)
                    self._log.debug("Found: %s" % ret)
                elif os.path.isdir(os.path.join(dir, subdir)):
                    ret = self._findFlowDvSubdir(os.path.join(dir, subdir))
                if ret is not None:
                    break
            if ret is not None:
                break
        return ret

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

    def _loadTasks(self, 
                   pkg : Package, 
                   loader : PackageLoader,
                   taskdefs : List[TaskDef], 
                   basedir : str):
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
                srcinfo=taskdef.srcinfo,
                taskdef=taskdef)

            if taskdef.iff is not None:
                task.iff = taskdef.iff

            tasks.append((taskdef, task))
            pkg.task_m[task.name] = task
            self._pkg_s[-1].add(task, taskdef.name)

        # Collect feeds: for each taskdef with feeds, record feeding tasks in _feeds_map
        for taskdef, task in tasks:
            for fed_name in getattr(taskdef, "feeds", []):
                fq_fed_name = fed_name
                if fq_fed_name not in self._feeds_map:
                    self._feeds_map[fq_fed_name] = []
                self._feeds_map[fq_fed_name].append(task)
        # Now, build out tasks
        for taskdef, task in tasks:
            task.taskdef = taskdef
            self._elabTask(task, loader)

        self._log.debug("<-- _loadTasks %s" % pkg.name)

    def _loadTypes(self, 
                   pkg, 
                   loader : PackageLoader,
                   typedefs):
        self._log.debug("--> _loadTypes")
        types = []
        for td in typedefs:
            tt = Type(
                name=self._getScopeFullname(td.name),
                doc=td.doc,
                srcinfo=td.srcinfo,
                typedef=td)
            pkg.type_m[tt.name] = tt
            self._pkg_s[-1].addType(tt, td.name)
            types.append((td, tt))
        
        # Now, resolve 'uses' and build out
        for td,tt in types:
            self._elabType(tt)

        self._log.debug("<-- _loadTypes")
        pass

    def _getParamT(
            self, 
            taskdef, 
            base_t : pydantic.BaseModel, 
            typename=None,
            is_type=False):
        self._log.debug("--> _getParamT %s (%s)" % (taskdef.name, str(taskdef.params)))
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

                    if type(value) == list:
                        for i in range(len(value)):
                            if "${{" in value[i]:
                                value[i] = self._eval.eval(value[i])
                    else:
                        if "${{" in value:
                            value = self._eval.eval(value)

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
    
    def _elabTask(self, 
                  task,
                  loader : PackageLoader):
        self._log.debug("--> _elabTask %s" % task.name)
        taskdef = task.taskdef

        task.taskdef = None
        if taskdef.uses is not None:
            task.uses = self._findTaskOrType(taskdef.uses, loader)

            if task.uses is None:
                similar = self._getSimilarError(taskdef.uses)
                self.error("failed to resolve task-uses %s.%s" % (
                    taskdef.uses, similar), taskdef.srcinfo)
                return

        loader.pushEvalScope(dict(srcdir=os.path.dirname(taskdef.srcinfo.file)))
        
        passthrough, consumes, rundir = self._getPTConsumesRundir(taskdef, task.uses)

        task.passthrough = passthrough
        task.consumes = consumes
        task.rundir = rundir

        task.paramT = self._getParamT(
            taskdef, 
            task.uses.paramT if task.uses is not None else None)

        for need in taskdef.needs:
            nt = None

            need_name = None
            if isinstance(need, str):
                need_name = need
                nt = self._findTask(need, loader)
            elif isinstance(need, TaskDef):
                need_name = need.name
            else:
                raise Exception("Unknown need type %s" % str(type(need)))
            
            if need_name.endswith(".needs"):
                # Find the original task first
                nt = self._findTask(need_name[:-len(".needs")], loader)
                if nt is None:
                    self.error("failed to find task %s" % need, taskdef.srcinfo)
                    raise Exception("Failed to find task %s" % need)
                for nn in nt.needs:
                    task.needs.append(nn)
            else:
                nt = self._findTask(need_name, loader)
            
                if nt is None:
                    self.error("failed to find task %s" % need, taskdef.srcinfo)
                    raise Exception("Failed to find task %s" % need)
                task.needs.append(nt)

        if taskdef.strategy is not None:
            self._log.debug("Task %s strategy: %s" % (task.name, str(taskdef.strategy)))
            if taskdef.strategy.generate is not None:
                shell = taskdef.strategy.generate.shell
                if shell is None:
                    shell = "pytask"
                task.strategy = Strategy(
                    generate=StrategyGenerate(
                        shell=shell,
                        run=taskdef.strategy.generate.run))

        # Determine how to implement this task
        if taskdef.body is not None and len(taskdef.body) > 0:
            self._mkTaskBody(task, loader, taskdef)
        elif taskdef.run is not None:
            task.run = self._eval.eval(taskdef.run)
            if taskdef.shell is not None:
                task.shell = taskdef.shell
        elif taskdef.pytask is not None: # Deprecated case
            task.run = taskdef.pytask
            task.shell = "pytask"
        elif task.uses is not None and isinstance(task.uses, Task) and task.uses.run is not None:
            task.run = task.uses.run
            task.shell = task.uses.shell

        self._log.debug("<-- _elabTask %s" % task.name)

    def _elabType(self, tt):
        self._log.debug("--> _elabType %s" % tt.name)
        td = tt.typedef

        tt.typedef = None
        if td.uses is not None:
            tt.uses = self._findType(td.uses)
            if tt.uses is None:
                raise Exception("Failed to find type %s" % td.uses)
        tt.paramT = self._getParamT(
            td, 
            tt.uses.paramT if tt.uses is not None else None,
            typename=tt.name,
            is_type=True)
        self._log.debug("<-- _elabType %s" % tt.name)


    def _mkTaskBody(self, 
                    task, 
                    loader : PackageLoader,
                    taskdef):
        self._pkg_s[-1].push_scope(SymbolScope(name=taskdef.name))
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
                    st.uses = self._findTask(td.uses, loader)
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
                    nn = self._findTask(need, loader)
                elif isinstance(need, TaskDef):
                    nn = self._findTask(need.name, loader)
                else:
                    raise Exception("Unknown need type %s" % str(type(need)))
                
                if nn is None:
                    self.error("failed to find task %s" % need, td.srcinfo)
#                    raise Exception("failed to find task %s" % need)
                
                st.needs.append(nn)

            if td.body is not None and len(td.body) > 0:
                self._mkTaskBody(st, loader, td)
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

    def package_scope(self):
        ret = None
        for i in range(len(self._pkg_s)-1, -1, -1):
            scope = self._pkg_s[i]
            if isinstance(scope, PackageScope):
                ret = scope
                break
        return ret
    
    def push_package_scope(self, pkg):
        if len(self._pkg_s):
            # Pull forward the overrides 
            pkg.override_m = self._pkg_s[-1].override_m.copy()
        self._pkg_s.append(pkg)
        pass

    def pop_package_scope(self):
        self._pkg_s.pop()

    def _getScopeFullname(self, leaf=None):
        return self._pkg_s[-1].getScopeFullname(leaf)

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
