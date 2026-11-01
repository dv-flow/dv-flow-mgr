"""The std Result type family loads, and is-a holds through the lineage."""
import os
import sys

import pytest

from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.ext_rgy import ExtRgy
from dv_flow.mgr.type_match import is_a, type_lineage
from dv_flow.mgr.util import loadProjPkgDef


@pytest.fixture(autouse=True)
def reset_extrgy():
    original_modules = set(sys.modules.keys())
    original_path = sys.path.copy()
    ExtRgy._inst = None
    yield
    ExtRgy._inst = None
    for mod_name in set(sys.modules.keys()) - original_modules:
        del sys.modules[mod_name]
    sys.path[:] = original_path


FLOW = """
package:
  name: user
  types:
  - name: LintResult
    uses: std.Result
    with:
      tool_name: {type: str, value: ""}
  - name: Plain
    with:
      x: {type: int, value: 0}
  tasks:
  - name: t
    uses: std.Null
"""


@pytest.fixture
def env(tmp_path):
    (tmp_path / "flow.dv").write_text(FLOW)
    loader, pkg = loadProjPkgDef(str(tmp_path))
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "rundir"), loader=loader)
    return loader, builder


NEW_TYPES = ["std.Diagnostic", "std.Metric", "std.ResultCheck", "std.Result",
             "std.TaskResult", "std.TestResult", "std.SuiteResult", "std.TestRunResult"]


@pytest.mark.parametrize("name", NEW_TYPES)
def test_type_loads(env, name):
    loader, builder = env
    t = loader.findType(name)
    assert t is not None
    assert t.doc
    item = builder.mkDataItem(name)
    assert item.type == name


def test_test_result_fields(env):
    _, builder = env
    item = builder.mkDataItem("std.TestResult")
    d = item.model_dump(warnings=False)
    for k in ("name", "status", "passed", "msg", "metrics", "checks", "counts",
              "diagnostics", "artifacts", "children", "testname", "seed"):
        assert k in d
    s = builder.mkDataItem("std.SuiteResult").model_dump(warnings=False)
    assert isinstance(s["passed"], bool)
    assert s["total"] == 0


@pytest.mark.parametrize("name", ["std.TestRunResult", "std.SuiteResult",
                                  "std.TestResult", "std.TaskResult", "user.LintResult"])
def test_is_a_result(env, name):
    loader, _ = env
    assert is_a(name, "std.Result", loader.findType)


def test_not_a_result(env):
    loader, _ = env
    assert not is_a("user.Plain", "std.Result", loader.findType)
    assert not is_a("std.FileSet", "std.Result", loader.findType)


def test_lineage(env):
    loader, _ = env
    assert type_lineage("std.TestRunResult", loader.findType) == [
        "std.TestRunResult", "std.SuiteResult", "std.Result", "std.DataItem"]


def test_tag_lookups_unchanged(env):
    loader, _ = env
    # std.Test / std.TestSuite are still the tag types
    assert is_a("std.Test", "std.Tag", loader.findType)
    assert is_a("std.TestSuite", "std.Tag", loader.findType)
    assert not is_a("std.TestSuite", "std.Result", loader.findType)
