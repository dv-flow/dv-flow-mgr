import abc
import dataclasses as dc
from typing import Optional, Type, Self, Union
from dv_flow.mgr.task_data import TaskDataInput
from dv_flow.mgr.task_run_ctxt import TaskRunCtxt

# Note: uses the 'descriptor' pattern
@dc.dataclass
class PyTask(object):
    desc : str = dc.field(default="")
    doc  : str = dc.field(default="")
    shell : str = dc.field(default="pytask")

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
    class Params(object): pass

    _ctxt : Optional[TaskRunCtxt] = dc.field(default=None)
    _input : Optional[TaskDataInput[Params]] = dc.field(default=None)

    @property
    def params(self) -> Params:
        if self._input is None:
            raise Exception()
        return self._input.params


    @abc.abstractmethod
    async def __call__(self) -> Union[str,None]:
        pass


    pass

def pytask(pkg):
    def __inner(T):
        pkg.registerTask(T)
        return T
    return __inner


