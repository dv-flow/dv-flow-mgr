#****************************************************************************
#* __init__.py
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
#
# Lazy-loading __init__.py
#
# Heavy modules (PackageLoader, TaskGraphBuilder, TaskRunner, rich-based
# listeners, etc.) are imported on first access via __getattr__ so that
# ``python -m dv_flow.mgr`` doesn't pay a large upfront import tax just
# to parse CLI arguments.
#
# Lightweight / decorator-support imports stay eager because they are
# needed at module-definition time (e.g. PassthroughE used as a default
# argument value in the ``task()`` decorator below).
#

import importlib as _importlib
import os as _os
import sys as _sys

# ── Eager (lightweight) imports ──────────────────────────────────────
from .task_def import *        # PassthroughE, ConsumesE, … (used by task() decorator)
from .task_data import *       # TaskMarker, SeverityE, TaskDataResult, …
from .package_def import PackageDef, PackageSpec
from .ext_rgy import ExtRgy
from .pytask import PyTask, pytask
from .pypkg import PyPkg, pypkg

VERSION = "1.5.0"
SUFFIX = ""
__version__ = "%s%s" % (VERSION, SUFFIX)

# ── Lazy-loaded symbols ─────────────────────────────────────────────
# Maps public name → (module_path, attribute).
_LAZY_IMPORTS = {
    "PackageLoader":        (".package_loader",      "PackageLoader"),
    "PackageLoaderP":       (".package_loader_p",    "PackageLoaderP"),
    "TaskGraphBuilder":     (".task_graph_builder",   "TaskGraphBuilder"),
    "TaskRunner":           (".task_runner",          "TaskRunner"),
    "TaskSetRunner":        (".task_runner",          "TaskSetRunner"),
    "TaskGenCtxt":          (".task_gen_ctxt",        "TaskGenCtxt"),
    "TaskGenInputData":     (".task_gen_ctxt",        "TaskGenInputData"),
    "TaskRunCtxt":          (".task_run_ctxt",        "TaskRunCtxt"),
    "ExecCmd":              (".task_run_ctxt",        "ExecCmd"),
    "TaskListenerLog":      (".task_listener_log",    "TaskListenerLog"),
    "CLITaskResolver":      (".cli_task_resolver",    "CLITaskResolver"),
    "TaskResolutionError":  (".cli_task_resolver",    "TaskResolutionError"),
    "TaskNotFoundError":    (".cli_task_resolver",    "TaskNotFoundError"),
    "AmbiguousTaskError":   (".cli_task_resolver",    "AmbiguousTaskError"),
    "NamingScheme":         (".naming_scheme",        "NamingScheme"),
    "NamingSchemeRegistry": (".naming_scheme",        "NamingSchemeRegistry"),
    "TaskNamingContext":    (".naming_scheme",        "TaskNamingContext"),
    "parse_parameter_overrides": (".util.util",       "parse_parameter_overrides"),
    "loadProjPkgDef":       (".util.util",            "loadProjPkgDef"),
}

def __getattr__(name):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path, __package__)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# Naming schemes must be registered before TaskGraphBuilder usage.
import dv_flow.mgr.naming_scheme_legacy  # noqa: F401
import dv_flow.mgr.naming_scheme_leaf    # noqa: F401


def task(paramT, passthrough=PassthroughE.Unused, consumes=ConsumesE.All):
    """Decorator to wrap a task method as a TaskNodeCtor"""

    def wrapper(T):
        from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
        from .param import Param
        import typing
        task_mname = T.__module__
        task_module = _sys.modules[task_mname]
        task_passthrough = passthrough
        task_consumes = consumes

        def _coerce_param(obj, key, value):
            """Coerce a scalar str to a list when the field type expects a list."""
            if not isinstance(value, str):
                return value
            model_fields = getattr(obj.__class__, 'model_fields', None)
            if model_fields is None or key not in model_fields:
                return value
            ann = model_fields[key].annotation
            args = typing.get_args(ann) if typing.get_origin(ann) is typing.Union else [ann]
            for arg in args:
                if typing.get_origin(arg) is list:
                    return [value]
            return value

        def mkTaskParams(params):
            obj = paramT()
            if params is not None:
                for key, value in params.items():
                    if not hasattr(obj, key):
                        raise Exception("Parameters class %s does not contain field %s" % (
                            str(obj), key))
                    else:
                        if isinstance(value, Param):
                            if value.append is not None:
                                ex_value = getattr(obj, key, [])
                                ex_value.extend(value.append)
                                setattr(obj, key, ex_value)
                            elif value.prepend is not None:
                                ex_value = getattr(obj, key, [])
                                value = value.copy()
                                value.extend(ex_value)
                                setattr(obj, key, value)
                            else:
                                raise Exception("Unhandled value spec: %s" % str(value))
                        else:
                            setattr(obj, key, _coerce_param(obj, key, value))
            return obj

        def ctor(builder=None, name=None, srcdir=None, params=None,
                 needs=None, passthrough=None, consumes=None, **kwargs):
            if params is None:
                params = mkTaskParams(kwargs)
            if passthrough is None:
                passthrough = task_passthrough
            if consumes is None:
                consumes = task_consumes
            if srcdir is None:
                srcdir = _os.path.dirname(_os.path.abspath(task_module.__file__))

            print("needs: %s" % str(needs))

            task_mname = T.__module__
            task_module_local = _sys.modules[task_mname]
            node = TaskNodeLeaf(
                name=T.__name__,
                params=params,
                task=T,
                srcdir=srcdir,
                ctxt=None,
                passthrough=passthrough,
                consumes=consumes,
                needs=needs)
            return node
        return ctor
    return wrapper
