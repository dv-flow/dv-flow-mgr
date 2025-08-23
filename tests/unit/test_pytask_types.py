
import dataclasses as dc
import pytest
from dv_flow.mgr import PyTask, PyPkg

def test_smoke(tmpdir):

    class MyTask(PyTask):
        _uses_ = "std.Message"

        @dc.dataclass
        class Params(PyTask.Params):
            msg : str = "Hello World"

    class MyPkg(PyPkg):
        pass
        

    pass