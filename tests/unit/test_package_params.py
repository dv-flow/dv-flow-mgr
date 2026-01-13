import asyncio
import json
import os
from dv_flow.mgr import TaskGraphBuilder, TaskSetRunner, PackageLoader
from dv_flow.mgr.task_graph_dot_writer import TaskGraphDotWriter
from .marker_collector import MarkerCollector


def test_smoke(tmpdir):
    flow_dv = """
package:
    name: foo
    with:
      p1:
        type: str
        value: hello

    tasks:
    - name: entry
      shell: bash
      run: |
        echo "${{ p1 }}" > out.txt
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("foo.entry", name="t1")

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
    assert os.path.isfile(os.path.join(rundir, "rundir/t1/out.txt"))
    with open(os.path.join(rundir, "rundir/t1/out.txt"), "r") as fp:
        assert fp.read().strip() == "hello"


def test_example(tmpdir):

    flow_dv = """
package:
  name: uvm
  with:
    sim:
      type: str
      value: "base"

  tasks:
  - name: a.base.c

  - name: t1
    uses: "a.${{ sim }}.c"
"""

    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    print("Package:\n%s\n" % json.dumps(pkg.dump(), indent=2))

    assert len(collector.markers) == 0
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    runner = TaskSetRunner(rundir=os.path.join(rundir, "rundir"))

    t1 = builder.mkTaskNode("uvm.t1", name="t1")

    output = asyncio.run(runner.run(t1))

    assert runner.status == 0
#    assert os.path.isfile(os.path.join(rundir, "rundir/t1/out.txt"))
#    with open(os.path.join(rundir, "rundir/t1/out.txt"), "r") as fp:
#        assert fp.read().strip() == "hello"


def test_param_in_uses_elab(tmpdir):
    """Regression: parameter in uses expression should resolve without exception."""
    flow_dv = """
package:
  name: regress
  with:
    sim:
      type: str
      value: base
  tasks:
  - name: t_bad
    uses: "nonexist.${{ sim }}.task"
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)

    from dv_flow.mgr import PackageLoader
    try:
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    except Exception as e:
        assert "Variable 'sim' not found" not in str(e), f"Parameter resolution failed: {e}"
        raise
    assert 'sim' in pkg.paramT.model_fields
    assert pkg.paramT.model_fields['sim'].default == 'base'

def test_pkg_import(tmpdir):
    """Regression: parameter in uses expression should resolve without exception."""
    flow_dv = """
package:
  name: regress
  with:
    sim:
      type: str
      value: base
  imports:
  - pkg.yaml
  tasks:
  - name: t_bad
    uses: pkg.p1_task
    with:
      param:
        type: str
        value: "${{ sim }}"
"""
    pkg_yaml = """
package:
    name: pkg
    tasks:
    - name: p1_task
"""
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    with open(os.path.join(rundir, "pkg.yaml"), "w") as fp:
        fp.write(pkg_yaml)

    from dv_flow.mgr import PackageLoader
    try:
        pkg = PackageLoader().load(os.path.join(rundir, "flow.dv"))
    except Exception as e:
        assert "Variable 'sim' not found" not in str(e), f"Parameter resolution failed: {e}"
        raise
    assert 'sim' in pkg.paramT.model_fields
    assert pkg.paramT.model_fields['sim'].default == 'base'
def test_multi_level_param_inheritance(tmpdir):
    """Test that parameters are inherited through multiple levels of 'uses' relationships.
    
    Scenario: derived_task uses middle_task uses base_task, where base_task defines p1.
    The derived_task should be able to override p1 and access it at runtime.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  # Base task with parameter p1
  - name: base_task
    with:
      p1:
        type: str
        value: default_value
  
  # Middle task that uses base_task
  - name: middle_task
    uses: base_task
  
  # Derived task that uses middle_task (2 levels deep) and overrides p1
  - name: derived_task
    uses: middle_task
    with:
      p1: derived_value
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    # Test that derived_task can be built and has access to p1
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    # Build derived_task node
    t1 = builder.mkTaskNode("test_pkg.derived_task", name="t1")
    
    # Verify the task node has the parameter with the correct value
    assert t1.params is not None
    assert hasattr(t1.params, 'p1')
    # The key test: p1 should be 'derived_value', not 'default_value'
    assert t1.params.p1 == 'derived_value'

def test_three_level_param_inheritance_with_override(tmpdir):
    """Test parameter inheritance through three levels with overrides at each level.
    
    Scenario: task_c uses task_b uses task_a, where:
    - task_a defines p1 and p2
    - task_b overrides p1
    - task_c should inherit both p1 (from task_b) and p2 (from task_a)
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  # Base task with two parameters
  - name: task_a
    with:
      p1:
        type: str
        value: p1_from_a
      p2:
        type: str
        value: p2_from_a
  
  # Middle task overrides p1
  - name: task_b
    uses: task_a
    with:
      p1: p1_from_b
  
  # Derived task should inherit p1 from task_b and p2 from task_a
  - name: task_c
    uses: task_b
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    # Build task_c
    t1 = builder.mkTaskNode("test_pkg.task_c", name="t1")
    
    # Verify it has both parameters
    assert t1.params is not None
    assert hasattr(t1.params, 'p1')
    assert hasattr(t1.params, 'p2')
    
    # p1 should come from task_b, p2 should come from task_a
    assert t1.params.p1 == 'p1_from_b'
    assert t1.params.p2 == 'p2_from_a'

def test_deep_inheritance_chain_param_override(tmpdir):
    """Test parameter override in a deep inheritance chain.
    
    Scenario: task_d uses task_c uses task_b uses task_a
    where task_a defines p1, and task_d overrides it.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: task_a
    with:
      p1:
        type: str
        value: from_a
  
  - name: task_b
    uses: task_a
  
  - name: task_c
    uses: task_b
  
  - name: task_d
    uses: task_c
    with:
      p1: from_d
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    t1 = builder.mkTaskNode("test_pkg.task_d", name="t1")
    
    assert t1.params is not None
    assert hasattr(t1.params, 'p1')
    assert t1.params.p1 == 'from_d'

def test_param_override_cascade(tmpdir):
    """Test that outer-most parameter value wins when multiple levels override.
    
    Scenario: All three levels override the same parameter.
    The leaf task's value should win.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: task_a
    with:
      p1:
        type: str
        value: from_a
  
  - name: task_b
    uses: task_a
    with:
      p1: from_b
  
  - name: task_c
    uses: task_b
    with:
      p1: from_c
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    # Test task_b - should have value from task_b
    tb = builder.mkTaskNode("test_pkg.task_b", name="tb")
    assert tb.params.p1 == 'from_b'
    
    # Test task_c - should have value from task_c (outermost wins)
    tc = builder.mkTaskNode("test_pkg.task_c", name="tc")
    assert tc.params.p1 == 'from_c'

def test_param_defined_at_middle_level(tmpdir):
    """Test that parameters defined at middle levels can be accessed by leaf tasks.
    
    Scenario: task_a has no params, task_b defines p1, task_c tries to override it.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: task_a
  
  - name: task_b
    uses: task_a
    with:
      p1:
        type: str
        value: from_b
  
  - name: task_c
    uses: task_b
    with:
      p1: from_c
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    tc = builder.mkTaskNode("test_pkg.task_c", name="tc")
    assert tc.params is not None
    assert hasattr(tc.params, 'p1')
    assert tc.params.p1 == 'from_c'

def test_missing_parameter_override_error(tmpdir):
    """Test that trying to override a non-existent parameter produces an error.
    
    Scenario: task_b tries to override p1, but p1 is never declared in the chain.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: task_a
    with:
      p2:
        type: str
        value: valid_param
  
  - name: task_b
    uses: task_a
    with:
      p1: trying_to_override_nonexistent
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    # Should have an error marker about missing parameter
    assert len(collector.markers) > 0
    error_msgs = [m.msg for m in collector.markers if m.severity.value == 'error']
    assert any('p1' in msg and 'not found' in msg for msg in error_msgs)

def test_complex_type_inheritance(tmpdir):
    """Test that parameters with complex types (list, dict) are inherited correctly.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: base_task
    with:
      items:
        type: list
        value: [a, b, c]
      config:
        type: map
        value:
          key1: val1
          key2: val2
  
  - name: middle_task
    uses: base_task
  
  - name: derived_task
    uses: middle_task
    with:
      items: [x, y, z]
      config:
        key1: override1
        key3: val3
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    t1 = builder.mkTaskNode("test_pkg.derived_task", name="t1")
    
    assert t1.params is not None
    assert hasattr(t1.params, 'items')
    assert hasattr(t1.params, 'config')
    
    # Check that overridden values are correct
    assert t1.params.items == ['x', 'y', 'z']
    assert t1.params.config == {'key1': 'override1', 'key3': 'val3'}

def test_mixed_params_at_multiple_levels(tmpdir):
    """Test complex scenario with multiple parameters introduced and overridden at different levels.
    
    Scenario:
    - task_a defines p1, p2, p3
    - task_b defines p4, overrides p2
    - task_c defines p5, overrides p1 and p4
    - task_d overrides p3 and p5
    
    task_d should have: p1(from task_c), p2(from task_b), p3(from task_d), 
                        p4(from task_c), p5(from task_d)
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: task_a
    with:
      p1:
        type: str
        value: p1_a
      p2:
        type: str
        value: p2_a
      p3:
        type: str
        value: p3_a
  
  - name: task_b
    uses: task_a
    with:
      p2: p2_b
      p4:
        type: str
        value: p4_b
  
  - name: task_c
    uses: task_b
    with:
      p1: p1_c
      p4: p4_c
      p5:
        type: str
        value: p5_c
  
  - name: task_d
    uses: task_c
    with:
      p3: p3_d
      p5: p5_d
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    td = builder.mkTaskNode("test_pkg.task_d", name="td")
    
    assert td.params is not None
    assert hasattr(td.params, 'p1')
    assert hasattr(td.params, 'p2')
    assert hasattr(td.params, 'p3')
    assert hasattr(td.params, 'p4')
    assert hasattr(td.params, 'p5')
    
    # Verify values come from the correct level
    assert td.params.p1 == 'p1_c'  # from task_c
    assert td.params.p2 == 'p2_b'  # from task_b
    assert td.params.p3 == 'p3_d'  # from task_d (outermost)
    assert td.params.p4 == 'p4_c'  # from task_c
    assert td.params.p5 == 'p5_d'  # from task_d (outermost)

def test_param_template_with_inheritance(tmpdir):
    """Test that parameter values with template expressions work across inheritance.
    
    Scenario: Base task defines p1 and p2, where p2 references p1.
    Derived task overrides p1, and p2's template should still evaluate correctly.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: base_task
    with:
      p1:
        type: str
        value: base
      p2:
        type: str
        value: "prefix_${{ p1 }}"
  
  - name: middle_task
    uses: base_task
  
  - name: derived_task
    uses: middle_task
    with:
      p1: derived
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    # Base task should evaluate p2 with p1=base
    tb = builder.mkTaskNode("test_pkg.base_task", name="tb")
    assert tb.params.p1 == 'base'
    assert tb.params.p2 == 'prefix_base'
    
    # Derived task should evaluate p2 with the overridden p1=derived
    # Templates are re-evaluated during task graph construction with merged params
    td = builder.mkTaskNode("test_pkg.derived_task", name="td")
    assert td.params.p1 == 'derived'
    assert td.params.p2 == 'prefix_derived'  # Template evaluates with overridden p1

def test_no_params_at_any_level(tmpdir):
    """Test inheritance chain where no tasks define parameters.
    
    Scenario: Three-level chain with no parameters at all.
    Should work fine with empty params.
    """
    flow_dv = """
package:
  name: test_pkg
  
  tasks:
  - name: task_a
  
  - name: task_b
    uses: task_a
  
  - name: task_c
    uses: task_b
"""
    
    rundir = os.path.join(tmpdir)
    with open(os.path.join(rundir, "flow.dv"), "w") as fp:
        fp.write(flow_dv)
    
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(rundir, "flow.dv"))
    
    assert len(collector.markers) == 0
    
    builder = TaskGraphBuilder(
        root_pkg=pkg,
        rundir=os.path.join(rundir, "rundir"))
    
    tc = builder.mkTaskNode("test_pkg.task_c", name="tc")
    # Should build successfully even with no parameters
    assert tc is not None
