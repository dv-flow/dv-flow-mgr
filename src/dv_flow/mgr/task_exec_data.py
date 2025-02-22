import pydantic.dataclasses as dc
from pydantic import BaseModel
from typing import Any, Dict, List


class TaskExecData(BaseModel):
    """Data from a single exection of a task"""
    name : str
    start : str
    finish : str
    status : int
    memento : Any
    markers : List[Any]

class FlowExecData(BaseModel):
    """
    Data from multiple tasks executions. 'info' holds information
    across multiple flow invocations. 'tasks' holds the names of
    tasks executed in the most-recent invocation.
    """
    info : Dict[str, TaskExecData] = dc.Field(default_factory=dict)
    tasks : List[str] = dc.Field(default_factory=list)
