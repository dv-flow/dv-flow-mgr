import abc
import dataclasses as dc
from typing import Type
from dv_flow.mgr.task_data import TaskDataInput
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt

# Note: uses the 'descriptor' pattern
@dc.dataclass
class PyTask(object):
    # Desc: _desc_
    # Doc: _doc_ --> Use Python docstring
    # Consumes -> _consumes_ (could add class method)
    # (Produces)
    # Uses ... _uses_ (leverage base class)
    # Iff
    # Feeds (?)
    # Needs (?)
    # Strategy
    # Allow setting shell (pytask=run)
    # - When non-pytask, must return a string to execute
    # Implement 'body' for a compound task
    # TODO: Are there two materially-different use models for
    # generate and body?
    # - Body should look DSL-like
    # - Generate builds nodes directly

    @dc.dataclass
    class Params(): pass

    @abc.abstractmethod
    async def run(self, ctxt : TaskRunCtxt, input : TaskDataInput[Params]):
        pass


    pass
