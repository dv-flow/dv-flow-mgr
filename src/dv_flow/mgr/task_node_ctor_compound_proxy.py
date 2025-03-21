import os
import json
import dataclasses as dc
import logging
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataOutput, TaskDataResult
from .task_node import TaskNode
from .task_node_ctor import TaskNodeCtor
from .task_node_ctor_compound import TaskNodeCtorCompound

# TaskParamsCtor accepts an evaluation context and returns a task parameter object
TaskParamsCtor = Callable[[object], Any]

@dc.dataclass
class TaskNodeCtorCompoundProxy(TaskNodeCtorCompound):
    """Task has a 'uses' clause, so we delegate creation of the node"""
    uses : TaskNodeCtor = dc.field(default=None)

    _log : ClassVar = logging.getLogger("TaskNodeCtorCompoundProxy")

    def mkTask(self, builder, params, srcdir=None, name=None, needs=None) -> 'TaskNode':
        """Creates a task object"""
        if srcdir is None:
            srcdir = self.srcdir
        node = self.uses.mkTaskNode(
            builder=builder, params=params, srcdir=srcdir, name=name, needs=needs)
        node.passthrough = self.passthrough
        node.consumes = self.consumes
        return node

        if srcdir is None:
            srcdir = self.srcdir

        if self.uses is not None:
            return self.uses.mkTask(name, srcdir)
        else:
            raise NotImplementedError("TaskCtor.mkTask() not implemented for %s" % str(type(self)))
    