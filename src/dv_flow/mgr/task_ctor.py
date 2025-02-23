import os
import json
import dataclasses as dc
import logging
from pydantic import BaseModel
from typing import Any, Callable, ClassVar, Dict, List, Tuple
from .task_data import TaskDataOutput, TaskDataResult

# TaskParamsCtor accepts an evaluation context and returns a task parameter object
TaskParamsCtor = Callable[[object], Any]

@dc.dataclass
class TaskCtor(object):
    name : str
    uses : 'TaskCtor' = None
    srcdir : str = None

    _log : ClassVar = logging.getLogger("TaskCtor")

    def mkTask(self, name : str, srcdir=None) -> 'Task':
        """Creates a task object"""
        if srcdir is None:
            srcdir = self.srcdir

        if self.uses is not None:
            return self.uses.mkTask(name, srcdir)
        else:
            raise NotImplementedError("TaskCtor.mkTask() not implemented for %s" % str(type(self)))
    
    def mkParams(self, params=None) -> TaskParamsCtor:
        """Creates a list of task-parameter objects used produce the params object"""
        self._log.debug("--> %s::mkParams" % self.name)
        if self.uses is not None:
            params = self.uses.mkParams()
        else:
            params = TaskParams()
        self._log.debug("<-- %s::mkParams: %s" % (self.name, str(params)))

        return params

    def applyParams(self, params):
        if self.uses is not None:
            self.uses.applyParams(params)