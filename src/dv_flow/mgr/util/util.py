#****************************************************************************
#* util.py
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
import logging
import os
import yaml
from ..package_loader import PackageLoader
from ..task_data import TaskMarker, TaskMarkerLoc, SeverityE

_log = logging.getLogger("util")

def parse_parameter_overrides(def_list):
    """Parses ['name=value', ...] into categorized parameter overrides.
    
    Returns:
        dict with keys:
            'package': {param_name: value}  # Package-level parameters
            'task': {task_name: {param: value}}  # Task-level parameters
            'leaf': {param_name: value}  # Ambiguous leaf names (could be task params)
    """
    package_ov = {}
    task_ov = {}
    leaf_ov = {}  # NEW: leaf names that could match task parameters
    
    if not def_list:
        return {'package': package_ov, 'task': task_ov, 'leaf': leaf_ov}
    
    for item in def_list:
        # Accept raw 'name=value' values (regardless of how '-D' was passed)
        s = item.strip()
        if s.startswith("-D"):
            s = s[2:]
        if "=" not in s:
            continue
        name, value = s.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        
        # Categorize: package vs task parameter
        # No dots → leaf parameter (could be package or task)
        # One dot → could be pkg.param or task.param (defer to runtime)
        # Two+ dots → definitely task parameter (pkg.task.param)
        
        dot_count = name.count('.')
        if dot_count == 0:
            # No dots: leaf name - could be package or task parameter
            # Store in both package (backward compat) and leaf (for task matching)
            package_ov[name] = value
            leaf_ov[name] = value
        elif dot_count == 1:
            # One dot: could be pkg.param or task.param
            # Store in both for now, will be resolved at runtime
            parts = name.split('.', 1)
            package_ov[name] = value  # For backward compat: pkg.param
            # Also store as potential task override
            task_name, param_name = parts
            if task_name not in task_ov:
                task_ov[task_name] = {}
            task_ov[task_name][param_name] = value
        else:
            # Two+ dots: ambiguous. Could be `pkg.task.param` (task override) OR
            # `<dotted.pkg>.var` -- a package var of a multi-segment package
            # (e.g. `hdlsim.vlt.trace_fmt`). Offer BOTH candidates (as the 1-dot
            # case does): the package-override consumer matches the whole name
            # against actual package names (rsplit), binding only if such a
            # package+var exists; otherwise it is ignored, leaving the task
            # override to apply.
            package_ov[name] = value
            parts = name.rsplit('.', 1)
            task_name = parts[0]
            param_name = parts[1]
            if task_name not in task_ov:
                task_ov[task_name] = {}
            task_ov[task_name][param_name] = value
    
    return {'package': package_ov, 'task': task_ov, 'leaf': leaf_ov}

def load_param_file(filepath):
    """Load parameter overrides from JSON file or inline JSON string.
    
    Accepts either:
    - A file path: "params.json"
    - An inline JSON string: '{"tasks": {"build": {"top": "counter"}}}'
    
    File format:
    {
        "package": {"param1": "value1"},
        "tasks": {
            "taskname": {"param2": ["list", "value"]},
            "pkg.taskname": {"param3": {"complex": "object"}}
        }
    }
    
    Returns: Same format as parse_parameter_overrides
    """
    import json
    import os
    
    # Check if it's a JSON string (starts with { or [) or a file path
    if filepath.strip().startswith('{') or filepath.strip().startswith('['):
        # It's an inline JSON string
        try:
            data = json.loads(filepath)
        except json.JSONDecodeError as e:
            raise Exception(f"Error parsing inline JSON: {e}")
    else:
        # It's a file path
        if not os.path.exists(filepath):
            raise Exception(f"Parameter file not found: {filepath}")
        
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise Exception(f"Error parsing parameter file {filepath}: {e}")
    
    # Normalize to expected format
    package_ov = data.get('package', {})
    tasks_data = data.get('tasks', {})
    
    # Convert tasks format: {taskname: {param: value}} → nested dict
    task_ov = {}
    for task_name, params in tasks_data.items():
        task_ov[task_name] = params
    
    return {'package': package_ov, 'task': task_ov, 'leaf': {}}

def merge_parameter_overrides(cli_overrides, file_overrides):
    """Merge -D and -P overrides (CLI takes precedence).
    
    Args:
        cli_overrides: Result from parse_parameter_overrides
        file_overrides: Result from load_param_file
    
    Returns: Merged dict with same structure
    """
    merged = {
        'package': {},
        'task': {},
        'leaf': {}
    }
    
    # Start with file overrides
    merged['package'].update(file_overrides.get('package', {}))
    merged['leaf'].update(file_overrides.get('leaf', {}))
    
    file_tasks = file_overrides.get('task', {})
    for task_name, params in file_tasks.items():
        if task_name not in merged['task']:
            merged['task'][task_name] = {}
        merged['task'][task_name].update(params)
    
    # CLI overrides take precedence
    merged['package'].update(cli_overrides.get('package', {}))
    merged['leaf'].update(cli_overrides.get('leaf', {}))
    
    cli_tasks = cli_overrides.get('task', {})
    for task_name, params in cli_tasks.items():
        if task_name not in merged['task']:
            merged['task'][task_name] = {}
        merged['task'][task_name].update(params)
    
    return merged

def _yaml_error_loc(exc, fpath: str):
    """Build a TaskMarkerLoc for a flow-file parse error. A yaml
    MarkedYAMLError carries a `problem_mark` with 0-based line/column; convert to
    1-based for display. Falls back to just the path for non-YAML errors."""
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    if mark is not None:
        return TaskMarkerLoc(
            path=getattr(mark, "name", None) or fpath,
            line=getattr(mark, "line", -1) + 1,
            pos=getattr(mark, "column", -1) + 1)
    return TaskMarkerLoc(path=fpath)


def _classify_flow_file(fpath: str):
    """Classify a candidate flow file. Returns (is_package, parse_error):

      * (True, None)   -- parsed OK and has a 'package' key (a package root).
      * (False, None)  -- parsed OK but no 'package' key (a fragment) -> skip.
      * (False, exc)   -- FAILED to parse. The exception is the *real* error the
                          user needs to see; the caller must surface it rather
                          than silently skipping the file (which would later be
                          mis-reported as "no flow.yaml found").
    """
    try:
        if fpath.endswith(".toml"):
            import tomllib
            with open(fpath, "rb") as fp:
                doc = tomllib.load(fp)
        else:
            with open(fpath, "r") as fp:
                doc = yaml.safe_load(fp)
    except Exception as e:
        return False, e
    return (doc is not None and "package" in doc), None


def _is_package_file(fpath: str) -> bool:
    """Check if a flow file parses and contains a 'package' key (not a fragment).
    A parse error is treated as "not a package file" (returns False); callers
    that must distinguish a parse error from a fragment use _classify_flow_file."""
    is_pkg, _ = _classify_flow_file(fpath)
    return is_pkg


def loadProjPkgDef(path, listener=None, parameter_overrides=None, config: str | None = None,
                   package_maps=None):
    """Locates the project's flow spec and returns the PackageDef.
    
    Searches for a flow file containing a 'package' key. Fragment files
    (those with 'fragment' instead of 'package') are skipped, and the
    search continues up the directory tree.
    
    Args:
        parameter_overrides: Can be either:
            - Old format: dict of {name: value} for package params
            - New format: dict with 'package' and 'task' keys
    """

    _log.debug("--> loadProjPkgDef %s" % path)

    ret = None
    if os.path.isfile(path):
        dir = os.path.dirname(path)
        rootfile = path
    else:
        dir = path
        rootfile = None

        while dir != "/" and dir != "" and os.path.isdir(dir):
            for name in ("flow.dv", "flow.yaml", "flow.yml", "flow.toml"):
                fpath = os.path.join(dir, name)
                _log.debug("Trying path %s (%s)" % (
                    fpath, ("exists" if os.path.exists(fpath) else "doesn't exist")))
                if os.path.exists(fpath):
                    # Check if this is actually a package file, not a fragment
                    is_pkg, parse_error = _classify_flow_file(fpath)
                    if parse_error is not None:
                        # The file exists but does not parse. Select it as the
                        # rootfile so the full loader below re-parses it and
                        # reports the real syntax error *with source location*,
                        # instead of silently skipping it and mis-reporting
                        # "no flow.yaml found" once the search runs out.
                        _log.debug("Flow file %s failed to parse: %s" % (
                            fpath, parse_error))
                        rootfile = fpath
                        break
                    elif is_pkg:
                        rootfile = fpath
                        break
                    else:
                        _log.debug("Skipping %s (fragment file, not a package)" % fpath)
            if rootfile is not None:
                break
            else:
                dir = os.path.dirname(dir)

        if rootfile is None:
            _log.debug("Failed to find flow.yaml/flow.toml with 'package' key")
            if listener:
                listener(TaskMarker(
                    msg="Failed to find a 'flow.yaml/flow.toml' file that defines a package in %s or its parent directories" % path,
                    severity=SeverityE.Error))
    loader = None
    ret = None

    if rootfile is not None:
        _log.debug("Loading rootfile: %s" % rootfile)
        try:
            listeners = [listener] if listener is not None else []
            
            # Extract package overrides (support both old and new format)
            pkg_overrides = parameter_overrides or {}
            if isinstance(pkg_overrides, dict) and 'package' in pkg_overrides:
                # New format - extract only package overrides for loader
                pkg_overrides = pkg_overrides['package']
            
            loader = PackageLoader(
                marker_listeners=listeners,
                param_overrides=pkg_overrides,
                package_maps=list(package_maps) if package_maps else [])
            ret = loader.load(rootfile, config=config)
        except Exception as e:
            # A parse/scan error while reading the selected flow file. Report the
            # *real* error (with source location when available) rather than
            # letting the search fall through to the misleading "no flow.yaml
            # found". When a listener is present (the CLI path), emit a located
            # Error marker and return None so the caller reports it cleanly; with
            # no listener (programmatic callers / tests) re-raise so the
            # exception is still observable.
            if listener is not None:
                listener(TaskMarker(
                    msg="Failed to parse %s: %s" % (rootfile, e),
                    severity=SeverityE.Error,
                    loc=_yaml_error_loc(e, rootfile)))
                ret = None
            else:
                print("Fatal Error: while parsing %s" % rootfile)
                raise

    _log.debug("<-- loadProjPkgDef %s" % path)
    
    return loader, ret
