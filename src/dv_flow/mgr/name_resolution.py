#****************************************************************************
#* name_resolution.py
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
#****************************************************************************

import dataclasses as dc
from typing import Any, Dict, List
from .package import Package
from .task_node import TaskNode

@dc.dataclass
class TaskNameResolutionScope:
    """Represents a single task scope in the name resolution stack"""
    task: TaskNode
    variables: Dict[str, Any] = dc.field(default_factory=dict)

@dc.dataclass
class NameResolutionContext:
    """Represents a complete name resolution context"""
    builder: 'TaskGraphBuilder'  # Forward reference to avoid circular import
    package: Package
    task_scopes: List[TaskNameResolutionScope] = dc.field(default_factory=list)

    def resolve_variable(self, name: str) -> Any:
        """
        Resolve a variable name following scoping rules:
        1. Current task scope
        2. Enclosing compound-task scopes
        3. Current package variables
        4. Package-qualified variables
        """
        # Check if this is a package-qualified reference
        ret = None

        if name in self.builder._pkg_params_m.keys():
            # Check if this is a package-qualified reference
            ret = self.builder._pkg_params_m[name]

        # Check task scopes from innermost to outermost
        if ret is None:
            for scope in reversed(self.task_scopes):
                if name in scope.variables.keys():
                    ret = scope.variables[name]
                    break
                elif hasattr(scope.task.params, name):
                    # Check task parameters
                    ret = getattr(scope.task.params, name)
                    break

        # Check package variables
        if ret is None and hasattr(self.package.paramT, name):
            ret = getattr(self.package.paramT, name)

#        if ret is None and name in self.builder._pkg_m.keys():
#            pkg = self.builder._pkg_m[name]
#            ret = pkg.paramT

        print("<-- resolve: %s" % type(ret))
        return ret
