
import dataclasses as dc
import difflib
import logging
import os
import pydantic
import re
import yaml
from typing import Any, ClassVar, Dict, List, Optional, Union
from .cond_def import CondDef
from .config_def import ConfigDef
from .fragment_def import FragmentDef
from .loader_scope import LoaderScope
from .marker_listener import MarkerListener
from .package import Package
from .package_loader_p import PackageLoaderP
from .package_def import PackageDef
from .package_provider import PackageProvider
from .package_scope import PackageScope
from .param_def import ComplexType, ParamDef
from .param_def_collection import ParamDefCollection
from .srcinfo import SrcInfo
from .symbol_scope import SymbolScope
from .task import Task, Strategy, StrategyGenerate
from .task_def import TaskDef, ConsumesE, RundirE, PassthroughE, StrategyDef, CacheDef
from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
from .type import Type
from .type_def import TypeDef
from .yaml_srcinfo_loader import YamlSrcInfoLoader

def _suggest_similar_field(invalid_field: str, model_class: type) -> str:
    """Suggest similar valid field names using similarity matching"""
    if not hasattr(model_class, 'model_fields'):
        return ""
    
    valid_fields = list(model_class.model_fields.keys())
    
    # Special cases where the semantic meaning suggests a specific field
    semantic_map = {
        'type': 'uses',  # 'type' usually means task/type reference
    }
    
    if invalid_field in semantic_map:
        suggested = semantic_map[invalid_field]
        if suggested in valid_fields:
            return f". Did you mean '{suggested}'?"
    
    # Try fuzzy matching with lower cutoff for better suggestions
    matches = difflib.get_close_matches(invalid_field, valid_fields, n=3, cutoff=0.5)
    
    if matches:
        if len(matches) == 1:
            return f". Did you mean '{matches[0]}'?"
        else:
            return f". Did you mean one of: {', '.join(repr(m) for m in matches)}?"
    return ""

@dc.dataclass
class PackageProviderYaml(PackageProvider):
    path : str
    pkg : Optional[Package] = None
    _pkg_s : List[PackageScope] = dc.field(default_factory=list)
    _pkg_path_m : Dict[str, Package] = dc.field(default_factory=dict)
    _loading : bool = dc.field(default=False)
    _fragment_names : Dict[str, str] = dc.field(default_factory=dict)  # Track fragment names -> file
    _field_srcinfo_map : Dict[int, Dict] = dc.field(default_factory=dict)  # Store _field_srcinfo by object id
    _log : ClassVar[logging.Logger] = logging.getLogger("PackageProviderYaml")

    # Shared parser hook that dispatches based on file extension
    def _parse_file(self, file: str, is_root: bool):
        if file.endswith(".toml"):
            from .package_provider_toml import PackageProviderToml
            return PackageProviderToml(path=file)._parse_file(file, is_root)
        with open(file, "r") as fp:
            return yaml.load(fp, Loader=YamlSrcInfoLoader(file))
    
    def _save_field_srcinfo(self, obj):
        """Recursively save and remove _field_srcinfo from dict objects."""
        if isinstance(obj, dict):
            # Save _field_srcinfo if present
            if '_field_srcinfo' in obj:
                self._field_srcinfo_map[id(obj)] = obj.pop('_field_srcinfo')
            # Recurse into dict values
            for v in obj.values():
                self._save_field_srcinfo(v)
        elif isinstance(obj, list):
            # Recurse into list items
            for item in obj:
                self._save_field_srcinfo(item)
    
    def _get_field_srcinfo(self, obj, field_name):
        """Get field srcinfo for an object if available."""
        obj_id = id(obj)
        if obj_id in self._field_srcinfo_map:
            field_info = self._field_srcinfo_map[obj_id]
            if field_name in field_info:
                return field_info[field_name]
        return None

    def getPackageNames(self, loader : PackageLoaderP) -> List[str]: 
        assert not self._loading
        if self.pkg is None:
            self._loading = True
            self.pkg = Package(
                basedir=os.path.dirname(self.path),
                srcinfo=SrcInfo(file=self.path))
            self._loadPackage(self.pkg, self.path, loader)
            self._loading = False
        return [self.pkg.name]

    def getPackage(self, name : str, loader : PackageLoaderP) -> Package: 
        assert not self._loading
        if self.pkg is None:
            self._loading = True
            self.pkg = Package(
                basedir=os.path.dirname(self.path),
                srcinfo=SrcInfo(file=self.path))
            self._loadPackage(self.pkg, self.path, loader)
            self._loading = False
        if name != self.pkg.name:
            raise Exception("Internal error: this provider only handles %s:%s" % (
                self.pkg.name, self.path))
        return self.pkg
    
    def findPackage(self, name : str, loader : PackageLoaderP) -> Optional[Package]:
        ret = None
        self._log.debug("--> findPackage %s" % name)

        if not self._loading:
            if self.pkg is None:
                ret = self.getPackage(name, loader)
                if name != ret.name:
                    raise Exception("Package name doesn't match expected")
            else:
                ret = self.pkg

        self._log.debug("<-- findPackage %s" % name)
        return ret
    
    def _loadPackage(self, 
                     pkg : Package,
                     root, 
                     loader : PackageLoaderP,
                     exp_pkg_name=None) -> Package:
        self._log.debug("--> _loadPackage")
        loader.pushPath(root)

        pkg_def : Optional[PackageDef] = None

        self._log.debug("open %s" % root)
        doc = self._parse_file(root, is_root=True)

        if "package" not in doc.keys():
            raise Exception("Missing 'package' key in %s" % root)
        
        # Save _field_srcinfo before Pydantic validation (it's metadata, not schema)
        self._save_field_srcinfo(doc)
        
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
                    self._log.debug("Validation error: %s" % str(ee))
                    
                    # Extract parent object and model class for similarity matching
                    parent_obj = None
                    model_class = None
                    # Check context path to determine which model we're validating
                    loc_list = list(ee['loc'])
                    
                    # Determine model class based on path context
                    if 'tasks' in loc_list:
                        model_class = TaskDef
                    elif 'types' in loc_list:
                        model_class = TypeDef
                    elif 'configs' in loc_list:
                        model_class = ConfigDef
                    elif 'strategy' in loc_list:
                        model_class = StrategyDef
                    elif 'cache' in loc_list and isinstance(obj, dict):
                        model_class = CacheDef
                    elif len(loc_list) == 1:
                        # Top-level package field
                        model_class = PackageDef
                    
                    # Navigate to the object with the error
                    for i, el in enumerate(ee['loc']):
                        if i == len(ee['loc']) - 1:
                            parent_obj = obj
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
                    
                    # Try to get field-level location if available
                    if parent_obj is not None:
                        field_name = str(ee['loc'][-1])
                        field_loc = self._get_field_srcinfo(parent_obj, field_name)
                        if field_loc is not None:
                            # Use field-level location for more precise error reporting
                            loc = field_loc
                            self._log.debug("Using field-level srcinfo for '%s'" % field_name)
                    
                    # Enhance error message for extra_forbidden errors
                    error_msg = ee['msg']
                    if ee['type'] == 'extra_forbidden' and model_class is not None:
                        invalid_field = str(ee['loc'][-1])
                        suggestion = _suggest_similar_field(invalid_field, model_class)
                        error_msg = f"{error_msg}{suggestion}"
                    
                    if loc is not None:
                        marker_loc = TaskMarkerLoc(path=loc['file'])
                        if 'lineno' in loc.keys():
                            marker_loc.line = loc['lineno']
                        if 'linepos' in loc.keys():
                            marker_loc.pos = loc['linepos']

                        marker = TaskMarker(
                            msg=("%s (in %s)" % (error_msg, str(ee['loc'][-1]))),
                            severity=SeverityE.Error,
                            loc=marker_loc)
                    else:
                        marker_loc = TaskMarkerLoc(path=root)   
                        marker = TaskMarker(
                            msg=("%s (at '%s')" % (error_msg, loc_s)),
                            severity=SeverityE.Error,
                            loc=marker_loc)
                    loader.marker(marker)

        if pkg_def is not None:
            self._mkPackage(pkg, pkg_def, root, loader)

        loader.popPath()

        self._pkg_path_m[root] = pkg

        self._log.debug("<-- _loadPackage")

        return pkg
    
    def _mkPackage(self, 
                   pkg : Package,
                   pkg_def : PackageDef, 
                   root : str,
                   loader : PackageLoaderP) -> Package:
        self._log.debug("--> _mkPackage %s (%d types ; %d tasks)" % (
            pkg_def.name,
            len(pkg_def.tasks),
            len(pkg_def.types)))

        pkg.name = pkg_def.name
        pkg.desc = pkg_def.desc
        pkg.pkg_def = pkg_def  # expose original PackageDef for tests
        # Register package with loader for global lookup
        try:
            loader._pkg_m[pkg.name] = pkg
        except Exception:
            pass

        # TODO: handle 'uses' for packages
        pkg.paramT = self._getParamT(loader, pkg_def, None)
        # Apply parameter overrides (qualified or unqualified) before elaboration of tasks/types
        if hasattr(loader, 'param_overrides') and loader.param_overrides:
            import yaml
            for k, v in loader.param_overrides.items():
                if '.' in k:
                    pkg_name, pname = k.split('.',1)
                    if pkg_name != pkg.name:
                        continue
                else:
                    pname = k
                if pname in pkg.paramT.model_fields:
                    ann_t = pkg.paramT.model_fields[pname].annotation
                    # Coerce value similar to main loader
                    try:
                        parsed = yaml.safe_load(v) if isinstance(v, str) else v
                    except Exception:
                        parsed = v
                    if ann_t is int and not isinstance(parsed, int):
                        try: parsed = int(str(v),0)
                        except Exception: parsed = 0
                    elif ann_t is float and not isinstance(parsed,(int,float)):
                        try: parsed = float(str(v))
                        except Exception: parsed = 0.0
                    elif ann_t is bool and not isinstance(parsed,bool):
                        s=str(v).lower().strip()
                        parsed = s in ("1","true","yes","y","on")
                    elif ann_t is str and not isinstance(parsed,str):
                        parsed = str(parsed)
                    pkg.paramT.model_fields[pname].default = parsed

        # Apply any overrides from above

        # Now, apply these overrides to the 
        for target,override in pkg_def.overrides.items():
            # TODO: expand target, override
            pass

        pkg_scope = self.package_scope()
        if pkg_scope is not None:
            self._log.debug("Add self (%s) as a subpkg of %s" % (pkg.name, pkg_scope.pkg.name))
            pkg_scope.pkg.pkg_m[pkg.name] = pkg

        pkg_scope = self.package_scope()
        if pkg_scope is not None:
            self._log.debug("Add self (%s) as a subpkg of %s" % (pkg.name, pkg_scope.pkg.name))
            pkg_scope.pkg.pkg_m[pkg.name] = pkg

        self.push_package_scope(PackageScope(
            name=pkg.name, 
            pkg=pkg, 
            loader=LoaderScope(name=None, loader=loader)))
        # Ensure eval uses current package scope for variable resolution
        prev_name_res = loader._eval.expr_eval.name_resolution
        loader._eval.set_name_resolution(self._pkg_s[-1])

        try:
            # Imports are loaded first
            self._loadPackageImports(loader, pkg, pkg_def.imports, pkg.basedir)

            taskdefs = pkg_def.tasks.copy()
            typedefs = pkg_def.types.copy()

            # Load package-level fragments before config selection
            self._loadFragments(loader, pkg, pkg_def.fragments, pkg.basedir, taskdefs, typedefs)

            # Select and apply configuration (if any) prior to elaborating types/tasks
            cfg = self._selectConfig(pkg_def, loader)
            if cfg is not None:
                self._applyConfig(pkg_def, cfg, loader, pkg, taskdefs, typedefs)

            # Validate task overrides against base (uses) package when not in config
            base_pkg = None
            if pkg_def.uses is not None and pkg_def.uses in pkg.pkg_m:
                base_pkg = pkg.pkg_m[pkg_def.uses]
            for td in taskdefs:
                if hasattr(td, 'override') and td.override:
                    target = td.override
                    found = False
                    if base_pkg is not None:
                        # base tasks are keyed by fully-qualified name
                        fq = f"{base_pkg.name}.{target}"
                        found = fq in base_pkg.task_m
                    else:
                        # Attempt to locate base package lazily if not yet loaded
                        if pkg_def.uses is not None and pkg_def.uses in pkg.pkg_m:
                            base_pkg = pkg.pkg_m[pkg_def.uses]
                            fq = f"{base_pkg.name}.{target}"
                            found = fq in base_pkg.task_m
                    if not found:
                        loader.error(f"override target task '{target}' not found in base (uses) package", td.srcinfo)
                    # Ensure the override task takes the target name
                    if td.name is None or td.name != target:
                        td.name = target
                    # Implicitly inherit from overridden task if no explicit 'uses'
                    if td.uses is None and base_pkg is not None:
                        td.uses = f"{base_pkg.name}.{target}"
            # Alias inherited base-package tasks into root package namespace
            if base_pkg is not None:
                override_targets = {td.override for td in taskdefs if getattr(td, 'override', None)}
                from .task import Task
                for task in base_pkg.task_m.values():
                    leaf = task.name.split('.', 1)[1] if '.' in task.name else task.name
                    if leaf in override_targets:
                        continue  # overridden
                    alias_name = f"{pkg.name}.{leaf}"
                    if alias_name in pkg.task_m:
                        continue  # already present
                    alias = Task(
                        name=alias_name,
                        desc=task.desc,
                        doc=task.doc,
                        package=pkg,
                        srcinfo=task.srcinfo)
                    # Inherit implementation via uses chain
                    alias.uses = task
                    alias.paramT = task.paramT
                    alias.run = task.run
                    alias.shell = task.shell
                    alias.passthrough = getattr(task, 'passthrough', None)
                    alias.consumes = getattr(task, 'consumes', None)
                    alias.rundir = getattr(task, 'rundir', None)
                    # Shallow-copy needs/subtasks for graph continuity
                    alias.needs = list(getattr(task, 'needs', []))
                    alias.subtasks = list(getattr(task, 'subtasks', []))
                    # Mark alias so we don't recurse into base 'uses' when gathering needs
                    alias.inherited = True
                    pkg.task_m[alias.name] = alias
            self._loadTypes(pkg, loader, typedefs)
            self._loadTasks(pkg, loader, taskdefs, pkg.basedir)
            
            # Validate feeds references after all tasks are loaded
            for fed_name, feeding_tasks in loader.feedsMap().items():
                fed_task = self._findTask(fed_name, loader)
                if fed_task is None:
                    # Task referenced in feeds does not exist - report error
                    if feeding_tasks:
                        feeding_task = feeding_tasks[0]
                        if hasattr(feeding_task, 'srcinfo') and feeding_task.srcinfo is not None:
                            loc = feeding_task.srcinfo
                            
                            error_msg = f"Task '{feeding_task.name}' references undefined task '{fed_name}' in feeds field"
                            error_msg += loader.getSimilarNamesError(fed_name, only_tasks=True)
                            
                            marker = TaskMarker(
                                msg=error_msg,
                                severity=SeverityE.Error,
                                loc=TaskMarkerLoc(path=loc.file, line=loc.lineno, pos=loc.linepos))
                        else:
                            error_msg = f"Undefined task '{fed_name}' referenced in feeds"
                            error_msg += loader.getSimilarNamesError(fed_name, only_tasks=True)
                            marker = TaskMarker(
                                msg=error_msg,
                                severity=SeverityE.Error)
                        loader.marker(marker)
            
            # Resolve tags after types and tasks are loaded
            self._resolveTags(pkg, pkg_def.tags, loader)
            # Remap needs of tasks in root namespace to overridden names
            if base_pkg is not None:
                override_targets = {td.override for td in taskdefs if getattr(td, 'override', None)}
                for ot in override_targets:
                    overridden_name = f"{pkg.name}.{ot}"
                    base_name = f"{base_pkg.name}.{ot}"
                    overridden = pkg.task_m.get(overridden_name)
                    if overridden is None:
                        continue
                    for task in pkg.task_m.values():
                        for i, need in enumerate(task.needs):
                            if need.name == base_name:
                                task.needs[i] = overridden
        finally:
            # Restore previous name-resolution context and scope
            loader._eval.set_name_resolution(prev_name_res)
            self.pop_package_scope()

    def _selectConfig(self, pkg_def, loader):
        # Explicit config from loader overrides implicit selection
        cfg_name = getattr(loader, 'config_name', None)
        if cfg_name is not None:
            # Only enforce explicit config for the root package. Imported packages
            # may not define the same config name; in that case, silently skip.
            is_root = False
            try:
                is_root = (loader.rootDir() == loader.pathStack()[-1])
            except Exception:
                pass
            for c in pkg_def.configs:
                if c.name == cfg_name:
                    return c
            if is_root:
                loader.error(f"Configuration '{cfg_name}' not found in package {pkg_def.name}")
            return None
        # Implicit default
        for c in pkg_def.configs:
            if c.name == 'default':
                return c
        return None

    def _applyConfig(self, pkg_def, cfg, loader, pkg, taskdefs, typedefs):
        self._log.debug(f"Applying config {cfg.name} to package {pkg_def.name}")
        # Handle config inheritance (single level for now)
        base_cfg = None
        if cfg.uses is not None:
            for c in pkg_def.configs:
                if c.name == cfg.uses:
                    base_cfg = c
                    break
            if base_cfg is None:
                loader.error(f"Base configuration '{cfg.uses}' not found for '{cfg.name}'")
        def merge_params(base_params: Dict, new_params) -> Dict:
            """Merge parameter maps.
            ConfigDef.params is defined as a List[ParamDef]; PackageDef.params is a Dict.
            Handle list gracefully (ignored for now, since ParamDef lacks a name field)."""
            ret = {} if base_params is None else dict(base_params)
            if isinstance(new_params, dict):
                for k,v in new_params.items():
                    # Convert dict with 'type'/etc to ParamDef if needed
                    if isinstance(v, dict) and ('type' in v.keys() or 'value' in v.keys()):
                        from .param_def import ParamDef
                        try:
                            v = ParamDef(**v)
                        except Exception:
                            pass
                    ret[k] = v
            elif isinstance(new_params, list):
                # Future: support list[ParamDef] updates (requires a 'name' attribute)
                pass
            return ret
        # Merge params: package -> base_cfg -> cfg
        merged_params = pkg_def.params
        if base_cfg is not None:
            merged_params = merge_params(merged_params, base_cfg.params)
        merged_params = merge_params(merged_params, cfg.params)
        # Update pkg_def params then rebuild paramT
        pkg_def.params = merged_params
        pkg.paramT = self._getParamT(loader, pkg_def, None)
        # Apply imports/fragments from base then cfg
        if base_cfg is not None:
            self._loadPackageImports(loader, pkg, base_cfg.imports, pkg.basedir)
            self._loadFragments(loader, pkg, base_cfg.fragments, pkg.basedir, taskdefs, typedefs)
        self._loadPackageImports(loader, pkg, cfg.imports, pkg.basedir)
        self._loadFragments(loader, pkg, cfg.fragments, pkg.basedir, taskdefs, typedefs)
        # Apply types (overrides)
        def apply_type_list(lst):
            for td in lst:
                # Override support
                if hasattr(td, 'override') and td.override:
                    target = td.override
                    # Remove existing type definition matching target
                    for i in range(len(typedefs)-1, -1, -1):
                        if typedefs[i].name == target:
                            typedefs.pop(i)
                            break
                    td.name = target
                typedefs.append(td)
        if base_cfg is not None:
            apply_type_list(base_cfg.types)
        apply_type_list(cfg.types)
        # Apply tasks (overrides)
        def apply_task_list(lst):
            for td in lst:
                if hasattr(td, 'override') and td.override:
                    target = td.override
                    # Remove any prior taskdef with same name
                    for i in range(len(taskdefs)-1, -1, -1):
                        if taskdefs[i].name == target:
                            taskdefs.pop(i)
                            break
                    td.name = target if td.name is None else td.name
                    if td.name != target:
                        td.name = target
                    # Implicitly inherit from overridden task (base package) if no explicit 'uses'
                    if td.uses is None and pkg_def.uses is not None:
                        td.uses = f"{pkg_def.uses}.{target}"
                taskdefs.append(td)
        if base_cfg is not None:
            apply_task_list(base_cfg.tasks)
        apply_task_list(cfg.tasks)

        # Apply feeds after all tasks are loaded
        for fed_name, feeding_tasks in loader.feedsMap().items():
            fed_task = self._findTask(fed_name, loader)
            if fed_task is not None:
                for feeding_task in feeding_tasks:
                    # Only add if not already present
                    if all(
                        not (isinstance(n, tuple) and n[0] == feeding_task) and n != feeding_task
                        for n in fed_task.needs):
                        fed_task.needs.append(feeding_task)
            else:
                # Task referenced in feeds does not exist - report error
                # Find the feeding task to get source location
                if feeding_tasks:
                    feeding_task = feeding_tasks[0]
                    if hasattr(feeding_task, 'srcinfo') and feeding_task.srcinfo is not None:
                        loc = feeding_task.srcinfo
                        
                        error_msg = f"Task '{feeding_task.name}' references undefined task '{fed_name}' in feeds field"
                        error_msg += loader.getSimilarNamesError(fed_name, only_tasks=True)
                        
                        marker = TaskMarker(
                            msg=error_msg,
                            severity=SeverityE.Error,
                            loc=TaskMarkerLoc(path=loc.file, line=loc.lineno, pos=loc.linepos))
                    else:
                        error_msg = f"Undefined task '{fed_name}' referenced in feeds"
                        error_msg += loader.getSimilarNamesError(fed_name, only_tasks=True)
                        marker = TaskMarker(
                            msg=error_msg,
                            severity=SeverityE.Error)
                    loader.marker(marker)

        self._log.debug("<-- _mkPackage %s (%s)" % (pkg_def.name, pkg.name))
        return pkg
    
    def _findType(self, loader, name):
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
            uses = self._findType(loader, name)
            if uses is not None and uses.typedef:
                self._elabType(loader, uses)
                pass
        elif uses.taskdef:
            self._elabTask(uses, loader)

        self._log.debug("<-- _findTaskOrType %s (%s)" % (name, ("found" if uses is not None else "not found")))
        return uses
    
    def _loadPackageImports(self, loader, pkg, imports, basedir):
        self._log.debug("--> _loadPackageImports %s" % str(imports))
        if len(imports) > 0:
            self._log.info("Loading imported packages (basedir=%s)" % basedir)
        for imp in imports:
            self._log.debug("Loading import %s" % imp)
            self._loadPackageImport(loader, pkg, imp, basedir)
        self._log.debug("<-- _loadPackageImports %s" % str(imports))
    
    def _loadPackageImport(self, 
                           loader : PackageLoaderP,
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
            for root in (basedir, os.path.dirname(loader.rootDir())):
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
            loader.error("Import file %s not found" % imp_path, pkg.srcinfo)
            return

        if imp_path in self._pkg_path_m.keys():
            sub_pkg = self._pkg_path_m[imp_path]
        else:
            self._log.info("Loading imported file %s" % imp_path)
            imp_path = os.path.normpath(imp_path)
            if imp_path.endswith(".toml"):
                from .package_provider_toml import PackageProviderToml
                sub_pkg = Package(
                    basedir=os.path.dirname(imp_path),
                    srcinfo=SrcInfo(file=imp_path))
                # Use TOML provider to load
                sub_pkg = PackageProviderToml(path=imp_path)._loadPackage(sub_pkg, imp_path, loader)
            else:
                sub_pkg = Package(
                    basedir=os.path.dirname(imp_path),
                    srcinfo=SrcInfo(file=imp_path))
                sub_pkg = self._loadPackage(sub_pkg, imp_path, loader)
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
            for name in ("flow.dv", "flow.yaml", "flow.yml", "flow.toml"):
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
            for name in ("flow.dv", "flow.yaml", "flow.yml", "flow.toml"):
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

    def _loadFragments(self, loader, pkg, fragments, basedir, taskdefs, typedefs):
        for spec in fragments:
            self._loadFragmentSpec(loader, pkg, spec, basedir, taskdefs, typedefs)

    def _loadFragmentSpec(self, loader, pkg, spec, basedir, taskdefs, typedefs):
        # We're either going to have:
        # - File path
        # - Directory path

        if os.path.isfile(os.path.join(basedir, spec)):
            self._loadFragmentFile(
                loader,
                pkg, 
                os.path.join(basedir, spec),
                taskdefs, typedefs)
        elif os.path.isdir(os.path.join(basedir, spec)):
            self._loadFragmentDir(loader, pkg, os.path.join(basedir, spec), taskdefs, typedefs)
        else:
            raise Exception("Fragment spec %s not found" % spec)

    def _loadFragmentDir(self, loader, pkg, dir, taskdefs, typedefs):
        for file in os.listdir(dir):
            if os.path.isdir(os.path.join(dir, file)):
                self._loadFragmentDir(loader, pkg, os.path.join(dir, file), taskdefs, typedefs)
            elif os.path.isfile(os.path.join(dir, file)) and file in ("flow.dv","flow.yaml","flow.yml","flow.toml"):
                self._loadFragmentFile(loader, pkg, os.path.join(dir, file), taskdefs, typedefs)

    def _loadFragmentFile(self, loader, pkg, file, taskdefs, typedefs):
        if file in loader.pathStack():
            raise Exception("Recursive file processing @ %s: %s" % (file, ", ".join(loader.pathStack())))
        loader.pushPath(file)

        doc = self._parse_file(file, is_root=False)
        self._log.debug("doc: %s" % str(doc))
        if doc is not None and "fragment" in doc.keys():
            # Save _field_srcinfo before validation
            self._save_field_srcinfo(doc)
            
            try:
                    frag = FragmentDef(**(doc["fragment"]))
                    basedir = os.path.dirname(file)
                    pkg.fragment_def_l.append(frag)

                    # Check for name collisions
                    if frag.name is not None:
                        if frag.name in self._fragment_names:
                            marker = TaskMarker(
                                msg=f"Duplicate fragment name '{frag.name}' (previously defined in {self._fragment_names[frag.name]})",
                                severity=SeverityE.Error,
                                loc=TaskMarkerLoc(path=file))
                            loader.marker(marker)
                        else:
                            self._fragment_names[frag.name] = file

                    self._loadPackageImports(loader, pkg, frag.imports, basedir)
                    self._loadFragments(loader, pkg, frag.fragments, basedir, taskdefs, typedefs)
                    
                    # Annotate each task and type with the fragment name
                    for task in frag.tasks:
                        if not hasattr(task, '_fragment_name'):
                            task._fragment_name = frag.name
                    for typedef in frag.types:
                        if not hasattr(typedef, '_fragment_name'):
                            typedef._fragment_name = frag.name
                    
                    taskdefs.extend(frag.tasks)
                    typedefs.extend(frag.types)
            except pydantic.ValidationError as e:
                    self._log.debug("Fragment validation errors: %s" % file)
                    error_paths = []
                    loc = None
                    for ee in e.errors():
#                    print("  Error: %s" % str(ee))
                        obj = doc["fragment"]
                        loc = None
                        parent_obj = None
                        model_class = None
                        # Check context path to determine which model we're validating
                        loc_list = list(ee['loc'])
                        
                        # Determine model class based on path context
                        if 'tasks' in loc_list:
                            model_class = TaskDef
                        elif 'types' in loc_list:
                            model_class = TypeDef
                        elif len(loc_list) == 1:
                            # Top-level fragment field
                            model_class = FragmentDef
                        
                        for i, el in enumerate(ee['loc']):
                            if i == len(ee['loc']) - 1:
                                parent_obj = obj
                            self._log.debug("el: %s" % str(el))
                            obj = obj[el]
                            if type(obj) == dict and 'srcinfo' in obj.keys():
                                loc = obj['srcinfo']
                        
                        # Try to get field-level location if available
                        if parent_obj is not None:
                            field_name = str(ee['loc'][-1])
                            field_loc = self._get_field_srcinfo(parent_obj, field_name)
                            if field_loc is not None:
                                # Use field-level location for more precise error reporting
                                loc = field_loc
                                self._log.debug("Using field-level srcinfo for '%s'" % field_name)
                        
                        # Enhance error message for extra_forbidden errors
                        error_msg = ee['msg']
                        if ee['type'] == 'extra_forbidden' and model_class is not None:
                            invalid_field = str(ee['loc'][-1])
                            suggestion = _suggest_similar_field(invalid_field, model_class)
                            error_msg = f"{error_msg}{suggestion}"
                        
                        if loc is not None:
                            marker_loc = TaskMarkerLoc(path=loc['file'])
                            if 'lineno' in loc.keys():
                                marker_loc.line = loc['lineno']
                            if 'linepos' in loc.keys():
                                marker_loc.pos = loc['linepos']

                            marker = TaskMarker(
                                msg=("%s (in %s)" % (error_msg, str(ee['loc'][-1]))),
                                severity=SeverityE.Error,
                                loc=marker_loc)
                        else:
                            marker = TaskMarker(
                                msg=error_msg, 
                                severity=SeverityE.Error,
                                loc=TaskMarkerLoc(path=file))
                        loader.marker(marker)
        else:
            print("Warning: file %s is not a fragment" % file)
        loader.popPath()

    def _loadTasks(self, 
                   pkg : Package, 
                   loader : PackageLoaderP,
                   taskdefs : List[TaskDef], 
                   basedir : str):
        self._log.debug("--> _loadTasks %s" % pkg.name)

        # Declare first
        tasks = []
        for taskdef in taskdefs:
            # Build the task name, including fragment name if present
            if hasattr(taskdef, '_fragment_name') and taskdef._fragment_name is not None:
                task_name = f"{pkg.name}.{taskdef._fragment_name}.{taskdef.name}"
            else:
                task_name = f"{pkg.name}.{taskdef.name}"
            
            # Skip duplicate check for override tasks - they're allowed to override existing tasks
            if not (hasattr(taskdef, 'override') and taskdef.override):
                if task_name in pkg.task_m.keys():
                    raise Exception("Duplicate task %s" % task_name)
            
            # TODO: resolve 'needs'
            needs = []

            if taskdef.srcinfo is None:
                raise Exception("null srcinfo")
            self._log.debug("Create task %s in pkg %s" % (task_name, pkg.name))
            desc = taskdef.desc if taskdef.desc is not None else ""
            doc = taskdef.doc if taskdef.doc is not None else ""
            task = Task(
                name=task_name,
                desc=desc,
                doc=doc,
                package=pkg,
                srcinfo=taskdef.srcinfo,
                taskdef=taskdef)

            if taskdef.iff is not None:
                task.iff = taskdef.iff

            # Process visibility scope
            if taskdef.scope is not None:
                scope_list = taskdef.scope if isinstance(taskdef.scope, list) else [taskdef.scope]
                task.is_root = 'root' in scope_list
                task.is_export = 'export' in scope_list
                task.is_local = 'local' in scope_list
            # If no scope specified, task is visible within the package (default)

            tasks.append((taskdef, task))
            pkg.task_m[task.name] = task
            
            # Add task to symbol scope with appropriate name
            if hasattr(taskdef, '_fragment_name') and taskdef._fragment_name is not None:
                # Add to fragment scope
                self._pkg_s[-1].add(task, f"{taskdef._fragment_name}.{taskdef.name}")
            else:
                self._pkg_s[-1].add(task, taskdef.name)

        # Collect feeds: for each taskdef with feeds, record feeding tasks in _feeds_map
        for taskdef, task in tasks:
            for fed_name in getattr(taskdef, "feeds", []):
                # Qualify unqualified feed names with current package
                qname = fed_name if '.' in fed_name else f"{pkg.name}.{fed_name}"
                loader.addFeed(task, qname)

        # Now, build out tasks
        for taskdef, task in tasks:
            task.taskdef = taskdef
            self._elabTask(task, loader)
            # Resolve tags for this task after elaboration
            self._resolveTags(task, taskdef.tags, loader)
            # Allow error markers to be reported without raising here

        self._log.debug("<-- _loadTasks %s" % pkg.name)

    def _loadTypes(self, 
                   pkg, 
                   loader : PackageLoaderP,
                   typedefs):
        self._log.debug("--> _loadTypes")
        types = []
        for td in typedefs:
            # Build the type name, including fragment name if present
            if hasattr(td, '_fragment_name') and td._fragment_name is not None:
                type_name = f"{pkg.name}.{td._fragment_name}.{td.name}"
            else:
                type_name = f"{pkg.name}.{td.name}"
            
            tt = Type(
                name=type_name,
                doc=td.doc,
                tags=td.tags if td.tags else [],
                srcinfo=td.srcinfo,
                typedef=td)
            pkg.type_m[tt.name] = tt
            
            # Add type to symbol scope with appropriate name
            if hasattr(td, '_fragment_name') and td._fragment_name is not None:
                self._pkg_s[-1].addType(tt, f"{td._fragment_name}.{td.name}")
            else:
                self._pkg_s[-1].addType(tt, td.name)
            types.append((td, tt))
        
        # Now, resolve 'uses' and build out
        for td,tt in types:
            self._elabType(loader, tt)

        self._log.debug("<-- _loadTypes")
        pass

    def _getParamT(
            self, 
            loader,
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
            self._log.debug("Base type: %s (%d fields)" % (
                str(base_t),
                len(base_t.model_fields)))
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
            self._log.debug("hasattr[type]: %s" % hasattr(param, "type"))
            self._log.debug("type: %s" % getattr(param, "type", "<notpresent>"))
            if isinstance(param, dict) and "type" in param.keys():
                # Parameter declaration
                try:
                    param = ParamDef(**param)
                except Exception as e:
                    self._log.error("Failed to convert param-def %s to ParamDef" % str(param))
                    raise e
            
            if hasattr(param, "type") and param.type is not None:
                self._log.debug("  is being defined")
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
                    val = param.value
                    if isinstance(val, str) and "${{" in val:
                        val = loader.evalExpr(val)
                    field_m[p] = (ptype, val)
                else:
                    field_m[p] = (ptype, pdflt)
                self._log.debug("Set param=%s to %s" % (p, str(field_m[p][1])))
            else:
                self._log.debug("  is already defined")
                if p in field_m.keys():
                    if hasattr(param, "copy"):
                        value = param.copy()
                    else:
                        value = param

                    # if type(param) != dict:
                    #     value = param
                    # elif "value" in param.keys():
                    #     value = param["value"]
                    # else:
                    #     raise Exception("No value specified for param %s: %s" % (
                    #         p, str(param)))

                    if type(value) == list:
                        for i in range(len(value)):
                            if "${{" in value[i]:
                                value[i] = loader.evalExpr(value[i])
                    elif type(value) == dict:
                        self._log.debug("TODO: dict value")
                        for k in value.keys():
                            v = value[k]
                            if "${{" in v:
                                v = loader.evalExpr(v)
                                value[k] = v
                    elif type(value) == ParamDef:
                        self._log.debug("TODO: paramdef value")
                    elif type(value) == str and "${{" in value:
                        value = loader.evalExpr(value)

                    # if type(value) == list:
                    #     for i in range(len(value)):
                    #         if "${{" in value[i]:
                    #             value[i] = loader.evalExpr(value[i])
                    # else:
                    #     if "${{" in value:
                    #         value = loader.evalExpr(value)

                    field_m[p] = (field_m[p][0], value)
                    self._log.debug("Set param=%s to %s" % (p, str(field_m[p][1])))
                else:
                    loader.error("Field %s not found in task %s (%s)" % (
                        p, 
                        taskdef.name,
                        ",".join(field_m.keys())), taskdef.srcinfo)

        self._log.debug("Total of %d fields" % len(field_m))
        if typename is not None:
            self._log.debug("Creating caller-defined type %s" % typename)
            field_m["type"] = (str, typename)
            params_t = pydantic.create_model(typename, **field_m)
        else:
            typename = "Task%sParams" % taskdef.name
            self._log.debug("Creating TaskParams type %s" % typename)
            params_t = pydantic.create_model(typename, **field_m)

        self._log.debug("== Params")
        for name,info in params_t.model_fields.items():
            self._log.debug("  %s: %s" % (name, str(info)))

        if params_t is None:
            raise Exception("Failed to build params_t")

        self._log.debug("<-- _getParamT %s" % taskdef.name)
        return params_t
    
    def _collectParamDefs(self, 
                          loader,
                          taskdef,
                          base_task: Optional[Union[Task, Type]]) -> ParamDefCollection:
        """
        Collect parameter definitions WITHOUT evaluating template expressions.
        This enables lazy evaluation during task graph building.
        """
        self._log.debug("--> _collectParamDefs %s (%s)" % (taskdef.name, str(taskdef.params)))
        
        collection = ParamDefCollection(srcinfo=taskdef.srcinfo)
        
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
        
        for p in taskdef.params.keys():
            param = taskdef.params[p]
            self._log.debug("param: %s %s (%s)" % (p, str(param), str(type(param))))
            
            # Convert dict to ParamDef if needed
            if isinstance(param, dict) and "type" in param.keys():
                try:
                    param = ParamDef(**param)
                except Exception as e:
                    self._log.error("Failed to convert param-def %s to ParamDef" % str(param))
                    raise e
            
            if hasattr(param, "type") and param.type is not None:
                # Parameter declaration with type
                self._log.debug("  is being defined")
                
                if isinstance(param.type, ComplexType):
                    if param.type.list is not None:
                        ptype = List
                        pdflt = []
                    elif param.type.map is not None:
                        ptype = Dict
                        pdflt = {}
                    else:
                        raise Exception("Complex type %s not supported" % str(param.type))
                else:
                    ptype_s = param.type
                    if ptype_s not in ptype_m.keys():
                        raise Exception("Unknown type %s" % ptype_s)
                    ptype = ptype_m[ptype_s]
                    pdflt = pdflt_m[ptype_s]
                
                if collection.has_param(p):
                    raise Exception("Duplicate field %s" % p)
                
                # Store raw value - DON'T evaluate template expressions
                val = param.value if param.value is not None else pdflt
                collection.add_param(p, ParamDef(value=val), ptype)
                self._log.debug("  Added param %s: type=%s, raw_value=%s" % (p, ptype, val))
                
            else:
                # Parameter override/assignment
                self._log.debug("  is being overridden")
                
                # Get the parameter value
                if hasattr(param, "copy"):
                    value = param.copy()
                elif isinstance(param, ParamDef):
                    value = param.value
                else:
                    value = param
                
                # Try to get type from base task inheritance chain
                ptype = None
                if collection.has_param(p):
                    ptype = collection.get_type(p)
                else:
                    # Search the full inheritance chain for this parameter
                    ptype = self._find_param_type_in_chain(p, base_task)
                
                # Check if parameter exists in base chain
                param_exists_in_base = (ptype is not None)
                
                if not param_exists_in_base and base_task:
                    # Parameter not found in base inheritance chain
                    loader.error("Parameter %s not found in base task %s" % (p, base_task.name), 
                               taskdef.srcinfo)
                    continue
                
                # Store raw value - DON'T evaluate template expressions
                collection.add_param(p, ParamDef(value=value), ptype)
                self._log.debug("  Overriding param %s: type=%s, raw_value=%s" % (p, ptype, value))
        
        self._log.debug("<-- _collectParamDefs %s: %d params" % (taskdef.name, len(collection.definitions)))
        return collection
    
    def _find_param_type_in_chain(self, param_name: str, base_task: Optional[Union[Task, Type]]) -> Optional[type]:
        """
        Search the inheritance chain for a parameter type declaration.
        Walks up the 'uses' chain until finding a parameter with a type declaration.
        """
        current = base_task
        visited = set()
        
        while current is not None:
            if id(current) in visited:
                break
            visited.add(id(current))
            
            # Check param_defs
            if hasattr(current, 'param_defs') and current.param_defs and current.param_defs.has_param(param_name):
                return current.param_defs.get_type(param_name)
            
            # Check paramT (old-style)
            if hasattr(current, 'paramT') and current.paramT:
                if hasattr(current.paramT, 'model_fields') and param_name in current.paramT.model_fields:
                    return current.paramT.model_fields[param_name].annotation
            
            # Move up the inheritance chain
            current = getattr(current, 'uses', None)
        
        return None
    
    def _collect_inherited_param_defaults(self, task: Union[Task, Type]) -> Dict[str, Any]:
        """
        Walk the inheritance chain and collect parameter default values.
        This is used to make parameters available during eager evaluation of 'run' expressions.
        Returns a dict of {param_name: default_value}
        """
        params = {}
        current = task
        visited = set()
        
        # Walk inheritance chain from root to derived (reverse order for correct override behavior)
        chain = []
        while current is not None:
            if id(current) in visited:
                break
            visited.add(id(current))
            chain.append(current)
            current = getattr(current, 'uses', None)
        
        # Process in reverse order (root first) so derived overrides base
        for task_in_chain in reversed(chain):
            # Get params from param_defs
            if hasattr(task_in_chain, 'param_defs') and task_in_chain.param_defs:
                for param_name, param_def in task_in_chain.param_defs.definitions.items():
                    params[param_name] = param_def.value
            # Fallback to paramT for old-style tasks
            elif hasattr(task_in_chain, 'paramT') and task_in_chain.paramT:
                if hasattr(task_in_chain.paramT, 'model_fields'):
                    for param_name, field_info in task_in_chain.paramT.model_fields.items():
                        params[param_name] = field_info.default
        
        return params
    
    def _elabTask(self, 
                  task,
                  loader : PackageLoaderP):
        self._log.debug("--> _elabTask %s" % task.name)
        taskdef = task.taskdef

        task.taskdef = None
        # Ensure name resolution uses current package scope for parameter lookup
        loader._eval.set_name_resolution(self.package_scope())
        if taskdef.uses is not None:
            uses_name = taskdef.uses
            if isinstance(uses_name, str):
                uses_name = loader.evalExpr(uses_name)
            task.uses = self._findTaskOrType(uses_name, loader)

            if task.uses is None:
                similar = loader.getSimilarNamesError(uses_name)
                loader.error("failed to resolve task-uses %s.%s" % (
                    uses_name, similar), taskdef.srcinfo)
                self._log.error("failed to resolve task-uses %s.%s" % (uses_name, similar))
                return

        loader.pushEvalScope(dict(srcdir=os.path.dirname(taskdef.srcinfo.file)))
        
        passthrough, consumes, rundir, uptodate = self._getPTConsumesRundirUptodate(taskdef, task.uses)

        task.passthrough = passthrough
        task.consumes = consumes
        task.rundir = rundir
        task.uptodate = uptodate

        # NEW: Collect parameter definitions without evaluating
        task.param_defs = self._collectParamDefs(
            loader,
            taskdef, 
            task.uses if task.uses is not None else None)
        
        # NOTE: paramT will be built lazily during task graph construction
        # For now, we don't set 'this' in eval context since params aren't evaluated yet

        for need in taskdef.needs:
            nt = None

            need_name = None
            if isinstance(need, str):
                need_name = need
            elif isinstance(need, TaskDef):
                need_name = need.name
            else:
                raise Exception("Unknown need type %s" % str(type(need)))

            assert need_name is not None

            if "${{" in need_name:
                need_name = loader.evalExpr(need_name)
            
            # If this taskdef is from a fragment and the need is unqualified, 
            # try to qualify it with the fragment name first
            fragment_name = getattr(taskdef, '_fragment_name', None)
            
            if need_name.endswith(".needs"):
                # Find the original task first
                need_base = need_name[:-len(".needs")]
                # Try fragment-qualified name first if in a fragment
                if fragment_name and '.' not in need_base:
                    nt = self._findTask(f"{fragment_name}.{need_base}", loader)
                if nt is None:
                    nt = self._findTask(need_base, loader)
                if nt is None:
                    loader.error("failed to find task %s" % need_name, taskdef.srcinfo)
                for nn in nt.needs:
                    task.needs.append(nn)
            else:
                # Try fragment-qualified name first if in a fragment and need is unqualified
                if fragment_name and '.' not in need_name:
                    nt = self._findTask(f"{fragment_name}.{need_name}", loader)
                if nt is None:
                    nt = self._findTask(need_name, loader)
            
                if nt is None:
                    loader.error("failed to find task %s" % need_name, taskdef.srcinfo)
                else:
                    # Check visibility: warn if referencing non-export task from another package
                    if nt.package != task.package and not nt.is_export:
                        from .task_data import TaskMarker, TaskMarkerLoc, SeverityE
                        loader.marker(TaskMarker(
                            msg=f"Task '{task.name}' references task '{nt.name}' in package '{nt.package.name}' that is not marked 'export'",
                            severity=SeverityE.Warning,
                            loc=TaskMarkerLoc(path=taskdef.srcinfo.file, line=taskdef.srcinfo.lineno, pos=taskdef.srcinfo.linepos)))
                task.needs.append(nt)

        if taskdef.strategy is not None:
            self._log.debug("Task %s strategy: %s" % (task.name, str(taskdef.strategy)))
            task.strategy = Strategy()
            if taskdef.strategy.generate is not None:
                shell = taskdef.strategy.generate.shell
                if shell is None:
                    shell = "pytask"
                task.strategy.generate = StrategyGenerate(
                    shell=shell,
                    run=taskdef.strategy.generate.run)
            if taskdef.strategy.matrix is not None:
                task.strategy.matrix = taskdef.strategy.matrix
            
            # Handle body tasks for matrix strategy
            if taskdef.strategy.body and len(taskdef.strategy.body) > 0:
                # Create a temporary taskdef with the body for processing
                temp_taskdef = taskdef.model_copy()
                temp_taskdef.body = taskdef.strategy.body
                self._mkTaskBody(task, loader, temp_taskdef)

        # Determine how to implement this task
        if taskdef.body is not None and len(taskdef.body) > 0:
            self._mkTaskBody(task, loader, taskdef)
        elif taskdef.run is not None:
            # Add inherited parameters to eval scope before evaluating 'run'
            # This allows base task parameters to be referenced in 'run' expressions
            inherited_params = self._collect_inherited_param_defaults(task)
            loader.pushEvalScope(inherited_params)
            task.run = loader.evalExpr(taskdef.run)
            loader.popEvalScope()
            self._log.debug("Task %s run: %s (%s)" % (task.name, str(task.run), str(taskdef.run)))
            if taskdef.shell is not None:
                task.shell = taskdef.shell
        elif taskdef.pytask is not None: # Deprecated case
            task.run = taskdef.pytask
            task.shell = "pytask"
        elif task.uses is not None and isinstance(task.uses, Task) and task.uses.run is not None:
            task.run = task.uses.run
            task.shell = task.uses.shell

        self._log.debug("<-- _elabTask %s" % task.name)
        loader.popEvalScope()

    def _elabType(self, loader, tt):
        self._log.debug("--> _elabType %s" % tt.name)
        td = tt.typedef

        tt.typedef = None
        if td.uses is not None:
            tt.uses = self._findType(loader, td.uses)
            if tt.uses is None:
                raise Exception("Failed to find type %s" % td.uses)
        
        # Collect parameter definitions (like tasks) for deferred evaluation
        tt.param_defs = self._collectParamDefs(
            loader,
            td,
            tt.uses if tt.uses is not None else None)
        
        # Also build paramT for backward compatibility
        tt.paramT = self._getParamT(
            loader,
            td, 
            tt.uses.paramT if tt.uses is not None else None,
            typename=tt.name,
            is_type=True)
        self._log.debug("<-- _elabType %s" % tt.name)


    def _mkTaskBody(self, 
                    task, 
                    loader : PackageLoaderP,
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

            # Process visibility scope for subtasks
            if td.scope is not None:
                scope_list = td.scope if isinstance(td.scope, list) else [td.scope]
                st.is_root = 'root' in scope_list
                st.is_export = 'export' in scope_list
                st.is_local = 'local' in scope_list
            # If no scope specified, task is visible within the package (default)

            subtasks.append((td, st))
            task.subtasks.append(st)
            self._pkg_s[-1].add(st, td.name)

        # Now, resolve references
        for td, st in subtasks:
            if td.uses is not None:
                if st.uses is None:
                    uses_name = td.uses
                    if "${{" in uses_name:
                        uses_name = loader.evalExpr(uses_name)
                    st.uses = self._findTask(uses_name, loader)
                    if st.uses is None:
                        loader.error("failed to find task %s" % td.uses, td.srcinfo)
#                        raise Exception("Failed to find task %s" % uses_name)

            passthrough, consumes, rundir, uptodate = self._getPTConsumesRundirUptodate(td, st.uses)

            st.passthrough = passthrough
            st.consumes = consumes
            st.rundir = rundir
            st.uptodate = uptodate

            for need in td.needs:
                nn = None
                if isinstance(need, str):
                    need_name = need
                    if "${{" in need_name:
                        need_name = loader.evalExpr(need_name)
                    nn = self._findTask(need_name, loader)
                elif isinstance(need, TaskDef):
                    nn = self._findTask(need.name, loader)
                else:
                    raise Exception("Unknown need type %s" % str(type(need)))
                
                if nn is None:
                    loader.error("failed to find task %s" % need, td.srcinfo)
#                    raise Exception("failed to find task %s" % need)
                
                st.needs.append(nn)

            # Build parameter definitions (lazy evaluation)
            st.param_defs = self._collectParamDefs(
                loader,
                td, 
                st.uses if st.uses is not None else None)
            
            # Build 'this' context from param_defs for run command evaluation
            # Include both parent task params and subtask params
            this_vars = {}
            
            # Add parent task parameters to 'this' (evaluate them first)
            if task.param_defs:
                for pname, param_def in task.param_defs.definitions.items():
                    value = param_def.value
                    # Evaluate if it has template expressions
                    if isinstance(value, str) and "${{" in value:
                        try:
                            value = loader.evalExpr(value)
                        except:
                            pass  # Keep original if evaluation fails
                    this_vars[pname] = value
                    # Also make available as top-level variable
                    loader._eval.set(pname, value)
            
            # Set up 'this' so subtask params can reference parent params
            loader._eval.set("this", this_vars)
            
            # Now evaluate subtask parameters (they can use this.xxx)
            subtask_vars = {}
            if st.param_defs:
                for pname, param_def in st.param_defs.definitions.items():
                    value = param_def.value
                    # Evaluate if it has template expressions
                    if isinstance(value, str) and "${{" in value:
                        try:
                            value = loader.evalExpr(value)
                        except:
                            pass  # Keep original if evaluation fails
                    subtask_vars[pname] = value
                    # Make available as top-level variable for run command
                    loader._eval.set(pname, value)
                    # Also add to this
                    this_vars[pname] = value
            
            # Update 'this' with subtask params
            loader._eval.set("this", this_vars)

            if td.body is not None and len(td.body) > 0:
                self._mkTaskBody(st, loader, td)
            elif td.run is not None:
                loader.pushEvalScope(dict(srcdir=os.path.dirname(td.srcinfo.file)))
                _expanded = loader.evalExpr(td.run)
                st.run = _expanded
                loader.popEvalScope()
                st.shell = getattr(td, "shell", None)
            elif td.pytask is not None:
                st.run = td.pytask
                st.shell = "pytask"
            elif st.uses is not None and st.uses.run is not None:
                st.run = st.uses.run
                st.shell = st.uses.shell

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

    def _getPTConsumesRundirUptodate(self, taskdef : TaskDef, base_t : Union[Task,Type]):
        self._log.debug("_getPTConsumesRundirUptodate %s" % taskdef.name)
        passthrough = taskdef.passthrough
        consumes = taskdef.consumes.copy() if isinstance(taskdef.consumes, list) else taskdef.consumes
        rundir = taskdef.rundir
        uptodate = taskdef.uptodate
#        needs = [] if task.needs is None else task.needs.copy()

        if base_t is not None and isinstance(base_t, Task):
            if passthrough is None:
                passthrough = base_t.passthrough
            if consumes is None:
                consumes = base_t.consumes
            if rundir is None:
                rundir = base_t.rundir
            if uptodate is None:
                uptodate = base_t.uptodate

        if passthrough is None:
            passthrough = PassthroughE.Unused
        if consumes is None:
            consumes = ConsumesE.All


        return (passthrough, consumes, rundir, uptodate)

    def _resolveTags(self, target, tag_defs, loader):
        """Resolve tag type references and instantiate Type objects."""
        self._log.debug("--> _resolveTags for %s" % (target.name if hasattr(target, 'name') else str(target)))
        
        if not tag_defs:
            return
        
        for tag_def in tag_defs:
            if isinstance(tag_def, str):
                type_name = tag_def
                param_overrides = {}
            elif isinstance(tag_def, dict):
                if len(tag_def) != 1:
                    loader.error(f"Tag definition must have exactly one key (type reference), got {len(tag_def)}", 
                               getattr(target, 'srcinfo', None))
                    continue
                type_name = list(tag_def.keys())[0]
                param_overrides = tag_def[type_name]
                if not isinstance(param_overrides, dict):
                    loader.error(f"Tag parameter overrides must be a dict, got {type(param_overrides)}", 
                               getattr(target, 'srcinfo', None))
                    continue
            else:
                loader.error(f"Invalid tag definition type: {type(tag_def)}", 
                           getattr(target, 'srcinfo', None))
                continue
            
            tag_type = self._findType(loader, type_name)
            
            if tag_type is None:
                similar = loader.getSimilarNamesError(type_name)
                loader.error(f"Failed to resolve tag type {type_name}.{similar}", 
                           getattr(target, 'srcinfo', None))
                continue
            
            if not self._isTagType(tag_type):
                loader.error(f"Type {type_name} is not derived from std.Tag", 
                           getattr(target, 'srcinfo', None))
                continue
            
            tag_instance = self._instantiateTag(tag_type, param_overrides, loader)
            target.tags.append(tag_instance)
        
        self._log.debug("<-- _resolveTags for %s: %d tags" % (
            target.name if hasattr(target, 'name') else str(target), 
            len(target.tags)))
    
    def _isTagType(self, typ):
        """Check if a type is derived from std.Tag"""
        if typ.name == "std.Tag":
            return True
        if typ.uses is not None:
            return self._isTagType(typ.uses)
        return False
    
    def _instantiateTag(self, tag_type, param_overrides, loader):
        """Instantiate a tag Type with parameter overrides merged with defaults."""
        from .type import Type
        from .param_def import ParamDef
        from .param_def_collection import ParamDefCollection
        import copy
        
        tag_instance = Type(
            name=tag_type.name,
            doc=tag_type.doc,
            srcinfo=tag_type.srcinfo
        )
        
        param_defs = ParamDefCollection(srcinfo=tag_type.srcinfo)
        
        # Walk inheritance chain to collect all parameters
        inheritance_chain = []
        current = tag_type
        visited = set()
        while current is not None:
            if id(current) in visited:
                break
            visited.add(id(current))
            inheritance_chain.append(current)
            current = getattr(current, 'uses', None)
        
        # Process in reverse order (base first) so derived overrides base
        for typ in reversed(inheritance_chain):
            if typ.param_defs:
                for pname, param_def in typ.param_defs.definitions.items():
                    ptype = typ.param_defs.get_type(pname)
                    value = copy.deepcopy(param_def.value) if param_def else None
                    param_defs.add_param(pname, ParamDef(value=value), ptype)
        
        # Apply overrides from tag usage
        for key, value in param_overrides.items():
            if param_defs.has_param(key):
                ptype = param_defs.get_type(key)
                if isinstance(value, str) and "${{" in value:
                    value = loader.evalExpr(value)
                param_defs.add_param(key, ParamDef(value=value), ptype)
            else:
                loader.error(f"Parameter {key} not found in tag type {tag_type.name}", None)
        
        tag_instance.param_defs = param_defs
        
        # Build paramT for eager access
        if tag_instance.param_defs:
            field_m = {}
            for pname, param_def in tag_instance.param_defs.definitions.items():
                ptype = tag_instance.param_defs.get_type(pname)
                value = param_def.value
                if isinstance(value, str) and "${{" in value:
                    try:
                        value = loader.evalExpr(value)
                    except:
                        pass
                field_m[pname] = (ptype, value)
            
            if field_m:
                import pydantic
                typename = f"Tag{tag_type.name}Params"
                tag_instance.paramT = pydantic.create_model(typename, **field_m)()
        
        return tag_instance
