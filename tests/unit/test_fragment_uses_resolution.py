"""
Test that tasks within a named fragment can reference sibling tasks
via unqualified names in their 'uses' field.

When a fragment named 'apb' defines tasks 'eval-base' and 'design-doc',
and 'design-doc' has 'uses: eval-base', the loader should resolve
'eval-base' to the fragment-qualified 'apb.eval-base' automatically.
"""
import os
import pytest
from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector
from dv_flow.mgr.task_graph_builder import TaskGraphBuilder


def test_fragment_uses_unqualified_sibling(tmpdir):
    """Unqualified 'uses' in a fragment task should resolve to a sibling in the same fragment."""
    flow_dv = """
package:
    name: bench

    fragments:
    - apb.dv
"""

    frag_dv = """
fragment:
    name: apb

    tasks:
    - local: base-task
      with:
        msg:
          type: str
          value: hello

    - root: compound-task
      uses: base-task
      tasks:
      - name: step1
        run: echo "step1"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(tmpdir, "apb.dv"), "w") as fp:
        fp.write(frag_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    errors = [m for m in marker_collector.markers if "Error" in str(m.severity)]
    assert len(errors) == 0, (
        "Expected no errors, got: %s" % [m.msg for m in errors]
    )
    assert pkg is not None
    assert "bench.apb.base-task" in pkg.task_m
    assert "bench.apb.compound-task" in pkg.task_m

    compound = pkg.task_m["bench.apb.compound-task"]
    base = pkg.task_m["bench.apb.base-task"]
    assert compound.uses is base, (
        "compound-task.uses should point to base-task, got %s" % compound.uses
    )


def test_fragment_uses_qualified_still_works(tmpdir):
    """Fully-qualified 'uses' in a fragment should continue to work."""
    flow_dv = """
package:
    name: bench

    fragments:
    - apb.dv
"""

    frag_dv = """
fragment:
    name: apb

    tasks:
    - local: base-task

    - root: compound-task
      uses: apb.base-task
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(tmpdir, "apb.dv"), "w") as fp:
        fp.write(frag_dv)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    errors = [m for m in marker_collector.markers if "Error" in str(m.severity)]
    assert len(errors) == 0, (
        "Expected no errors, got: %s" % [m.msg for m in errors]
    )
    compound = pkg.task_m["bench.apb.compound-task"]
    base = pkg.task_m["bench.apb.base-task"]
    assert compound.uses is base


def test_fragment_uses_cross_fragment_requires_qualification(tmpdir):
    """Using a task from a different fragment requires at least fragment-qualified name."""
    flow_dv = """
package:
    name: bench

    fragments:
    - a.dv
    - b.dv
"""

    frag_a = """
fragment:
    name: fa

    tasks:
    - local: helper
"""

    frag_b = """
fragment:
    name: fb

    tasks:
    - root: user-task
      uses: helper
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(tmpdir, "a.dv"), "w") as fp:
        fp.write(frag_a)
    with open(os.path.join(tmpdir, "b.dv"), "w") as fp:
        fp.write(frag_b)

    marker_collector = MarkerCollector()
    pkg = PackageLoader(
        marker_listeners=[marker_collector]).load(os.path.join(tmpdir, "flow.dv"))

    # 'helper' is in fragment 'fa', but user-task is in fragment 'fb'.
    # Unqualified 'helper' should NOT resolve to fa.helper from fb context,
    # so we expect an error.
    errors = [m for m in marker_collector.markers if "Error" in str(m.severity)]
    assert len(errors) > 0, "Expected an error for cross-fragment unqualified uses"


def test_compound_uses_noncompound_param_only(tmpdir):
    """A compound task can 'uses' a non-compound task that only provides parameters."""
    flow_dv = """
package:
    name: bench

    fragments:
    - apb.dv
"""

    frag_dv = """
fragment:
    name: apb

    tasks:
    - local: eval-base
      with:
        model:
          type: str
          value: "test-model"
        grade_model:
          type: str
          value: "test-grade-model"

    - root: design-doc
      uses: eval-base
      tasks:
      - name: step1
        shell: bash
        run: echo "step1"

      - name: step2
        shell: bash
        needs: [step1]
        run: echo "step2"
"""

    with open(os.path.join(tmpdir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(tmpdir, "apb.dv"), "w") as fp:
        fp.write(frag_dv)

    marker_collector = MarkerCollector()
    loader = PackageLoader(marker_listeners=[marker_collector])
    pkg = loader.load(os.path.join(tmpdir, "flow.dv"))

    errors = [m for m in marker_collector.markers if "Error" in str(m.severity)]
    assert len(errors) == 0, (
        "Expected no errors, got: %s" % [m.msg for m in errors]
    )

    # Building the task graph should succeed (previously raised
    # "Task ... is not compound").
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmpdir), loader=loader)
    node = builder.mkTaskNode("bench.apb.design-doc")

    assert node is not None
    assert node.name == "bench.apb.design-doc"
    # Parameters from eval-base should be inherited
    assert hasattr(node.params, "model")
    assert node.params.model == "test-model"
    assert hasattr(node.params, "grade_model")
    assert node.params.grade_model == "test-grade-model"
