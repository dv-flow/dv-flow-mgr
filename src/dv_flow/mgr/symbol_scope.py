import dataclasses as dc
from typing import Any, Dict, List, Optional
from .task import Task
from .type import Type

@dc.dataclass(kw_only=True)
class SymbolScope(object):
    name : str
    task_m : Dict[str,Task] = dc.field(default_factory=dict)
    task_elab_m : Dict[str,bool] = dc.field(default_factory=dict)
    type_m : Dict[str,Type] = dc.field(default_factory=dict)
    type_elab_m : Dict[str,bool] = dc.field(default_factory=dict)
    override_m : Dict[str,Any] = dc.field(default_factory=dict)

    def add(self, task, name):
        self.task_m[name] = task

    def addType(self, type, name):
        self.type_m[name] = type

    def findTask(self, name) -> Optional[Task]:
        if name in self.task_m.keys():
            return self.task_m[name]
        else:
            return None

    def findType(self, name) -> Optional[Type]:
        if name in self.type_m.keys():
            return self.type_m[name]
        else:
            return None
        
    def resolve_variable(self, name):
        return None
