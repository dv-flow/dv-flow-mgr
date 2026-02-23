"""
Regression test for the "Illegal character" bug.

When a body-step parameter contains a ${{ }} template expression (e.g.
"${{ rundir }}/patched"), TaskGraphBuilder._expandParam passes the raw
template string to ExprParser.parse().  ExprParser does not understand
the '$', '{', or '}' delimiter characters and emits five "Illegal
character" warnings to stdout for every such expression.

This test builds a task graph that contains a body step whose 'base'
parameter references ${{ rundir }} and asserts that no "Illegal
character" lines are printed.  The test fails against the unfixed code
and passes once the fix (extracting the inner expression before parsing)
is applied.
"""

import os
import pytest
from dv_flow.mgr import TaskGraphBuilder, PackageLoader
from dv_flow.mgr.util import loadProjPkgDef


FLOW_DV = """
package:
    name: foo

    tasks:
    - name: CollectSrc
      body:
      - name: patched-src
        uses: std.FileSet
        with:
          base: "${{ rundir }}/patched"
          type: "systemVerilogSource"
          include:
            - "*.sv"
"""


def test_no_illegal_character_warnings_on_body_param(tmpdir, capsys):
    """Graph construction must not print 'Illegal character' for ${{ }} params."""

    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as fh:
        fh.write(FLOW_DV)

    loader, pkg_def = loadProjPkgDef(str(tmpdir))
    assert pkg_def is not None

    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(str(tmpdir), "rundir"),
    )

    # Building the task graph is where _expandParam runs and the bug
    # manifests; we do not need to execute the tasks.
    builder.mkTaskNode("foo.CollectSrc")

    captured = capsys.readouterr()
    assert "Illegal character" not in captured.out, (
        "ExprParser emitted 'Illegal character' warnings while building "
        "the task graph for a body-step parameter containing ${{ }}.\n"
        "Captured stdout:\n" + captured.out
    )


def test_no_illegal_character_warnings_list_param(tmpdir, capsys):
    """Same check for a list-valued parameter containing ${{ }} entries."""

    flow_dv = """
package:
    name: foo

    tasks:
    - name: CollectSrc
      body:
      - name: deperl
        uses: std.FileSet
        with:
          base: "."
          include:
            - "${{ rundir }}/lib/a.sv"
            - "${{ rundir }}/lib/b.sv"
"""

    with open(os.path.join(str(tmpdir), "flow.dv"), "w") as fh:
        fh.write(flow_dv)

    loader, pkg_def = loadProjPkgDef(str(tmpdir))
    assert pkg_def is not None

    builder = TaskGraphBuilder(
        root_pkg=pkg_def,
        rundir=os.path.join(str(tmpdir), "rundir"),
    )

    builder.mkTaskNode("foo.CollectSrc")

    captured = capsys.readouterr()
    assert "Illegal character" not in captured.out, (
        "ExprParser emitted 'Illegal character' warnings for a list-valued "
        "body-step parameter containing ${{ }} entries.\n"
        "Captured stdout:\n" + captured.out
    )
