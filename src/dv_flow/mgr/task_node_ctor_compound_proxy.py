import os
import json
import dataclasses as dc
import logging
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataOutput, TaskDataResult
from .task_node import TaskNode
from .task_node_compound import TaskNodeCompound
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor_compound import TaskNodeCtorCompound

# TaskParamsCtor accepts an evaluation context and returns a task parameter object
TaskParamsCtor = Callable[[object], Any]

@dc.dataclass
class TaskNodeCtorCompoundProxy(TaskNodeCtorCompound):
    """Task has a 'uses' clause, so we delegate creation of the node"""
    uses : TaskNodeCtor = dc.field(default=None)

    _log : ClassVar = logging.getLogger("TaskNodeCtorCompoundProxy")

    def mkTaskNode(self, builder, params, srcdir=None, name=None, needs=None) -> 'TaskNode':
        """Creates a task object without a base task"""
        if srcdir is None:
            srcdir = self.srcdir

        node = TaskNodeCompound(
            name=name, 
            srcdir=srcdir,
            params=params)

        is_compound_uses = builder.is_compound_uses()

        if not is_compound_uses:
            # 'uses' tasks should see the same 'in'
            builder.enter_compound(node)
            builder.addTask("in", node.input)
        else:
            builder.enter_compound_uses()

        # Build 'uses' node
        need_m = {}
        self._buildSubGraph(builder, node, need_m)

        builder.leave_compound(node)

        if not is_compound_uses:
            builder.leave_compound(node)
        else:
            builder.leave_compound_uses()

        return node
    