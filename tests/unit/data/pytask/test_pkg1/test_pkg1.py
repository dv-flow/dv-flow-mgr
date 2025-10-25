import dataclasses as dc
import pytest
from dv_flow.mgr import PyPkg, pypkg
from typing import ClassVar

pytestmark = pytest.mark.skip(reason="Not a test module")

def package(T):
    return T

@pypkg
class TestPkg1(PyPkg):
    name : ClassVar = ".".join(__module__.split(".")[:-1])

    pass

@pypkg
class TestPkg2(PyPkg):
    pass
