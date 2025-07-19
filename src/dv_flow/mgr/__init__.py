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
from .package_def import *
from .package_loader import PackageLoader
from .ext_rgy import ExtRgy
from .task_data import *
from .task_def import *
from .task_graph_builder import TaskGraphBuilder
from .task_run_ctxt import TaskRunCtxt
from .task_runner import TaskRunner
from .task_runner import TaskSetRunner
from .task_listener_log import TaskListenerLog

VERSION="1.5.0"
SUFFIX=""
__version__="%s%s" % (VERSION, SUFFIX)

def task(paramT,passthrough=PassthroughE.Unused,consumes=ConsumesE.All):
    """Decorator to wrap a task method as a TaskNodeCtor"""

    def wrapper(T):
        from dv_flow.mgr.task_node_leaf import TaskNodeLeaf
        from .param import Param
        task_mname = T.__module__
        task_module = sys.modules[task_mname]
        task_passthrough = passthrough
        task_consumes = consumes

        def mkTaskParams(params : Dict) -> Any:
            obj = paramT()

            # Apply user-specified params
            if params is not None:
                for key,value in params.items():
                    if not hasattr(obj, key):
                        raise Exception("Parameters class %s does not contain field %s" % (
                            str(type(obj)),
                            key
                        ))
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
                                pass
                            else:
                                raise Exception("Unhandled value spec: %s" % str(value))
                        else:
                            setattr(obj, key, value)
            return obj

        def ctor(
                builder=None, 
                name=None, 
                srcdir=None, 
                params=None, 
                needs=None, 
                passthrough=None, 
                consumes=None, 
                **kwargs):
            if params is None:
                params = mkTaskParams(kwargs)
            if passthrough is None:
                passthrough = task_passthrough
            if consumes is None:
                consumes = task_consumes
            if srcdir is None:
                srcdir=os.path.dirname(os.path.abspath(task_module.__file__))
            
            print("needs: %s" % str(needs))

            task_mname = T.__module__
            task_module = sys.modules[task_mname]
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
        # ctor = TaskNodeCtorWrapper(
        #     name=T.__name__,
        #     srcdir=os.path.dirname(os.path.abspath(task_module.__file__)),
        #     paramT=paramT,
        #     passthrough=passthrough,
        #     consumes=consumes,
        #     needs=[],
        #     T=T)
        return ctor
    return wrapper

