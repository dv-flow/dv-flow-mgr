"""Tests for type-based tags support on tasks and packages"""
import os
from dv_flow.mgr.package_loader import PackageLoader

def test_task_no_tags(tmpdir):
    """Test that tasks without tags have empty tag list"""
    yaml_content = """
package:
  name: test
  tasks:
    - name: t1
      run: echo "test"
"""
    
    flow_dv = os.path.join(tmpdir, "flow.dv")
    with open(flow_dv, "w") as f:
        f.write(yaml_content)
    
    pkg = PackageLoader().load(flow_dv)
    
    task = pkg.task_m["test.t1"]
    assert task.tags == []

def test_task_simple_tag(tmpdir):
    """Test task with a simple tag (type reference only)"""
    yaml_content = """
package:
  name: test
  
  types:
    - name: BuildTag
      uses: std.Tag
      with:
        category: "build"
  
  tasks:
    - name: t1
      tags: [test.BuildTag]
      run: echo "test"
"""
    
    flow_dv = os.path.join(tmpdir, "flow.dv")
    with open(flow_dv, "w") as f:
        f.write(yaml_content)
    
    pkg = PackageLoader().load(flow_dv)
    
    task = pkg.task_m["test.t1"]
    assert len(task.tags) == 1
    assert task.tags[0].name == "test.BuildTag"
    assert task.tags[0].paramT is not None
    assert task.tags[0].paramT.category == "build"

def test_tag_parameter_override(tmpdir):
    """Test tag with parameter overrides"""
    yaml_content = """
package:
  name: test
  
  types:
    - name: SeverityTag
      uses: std.Tag
      with:
        category: "severity"
        value: "info"
  
  tasks:
    - name: t1
      tags:
        - test.SeverityTag:
            value: "error"
      run: echo "test"
"""
    
    flow_dv = os.path.join(tmpdir, "flow.dv")
    with open(flow_dv, "w") as f:
        f.write(yaml_content)
    
    pkg = PackageLoader().load(flow_dv)
    
    task = pkg.task_m["test.t1"]
    assert len(task.tags) == 1
    assert task.tags[0].name == "test.SeverityTag"
    assert task.tags[0].paramT.category == "severity"
    assert task.tags[0].paramT.value == "error"

def test_tag_multiple_on_task(tmpdir):
    """Test multiple tags on a single task"""
    yaml_content = """
package:
  name: test
  
  types:
    - name: CategoryTag
      uses: std.Tag
      with:
        category: "type"
    - name: OwnerTag
      uses: std.Tag
      with:
        category: "owner"
  
  tasks:
    - name: t1
      tags:
        - test.CategoryTag:
            value: "unit"
        - test.OwnerTag:
            value: "alice"
      run: echo "test"
"""
    
    flow_dv = os.path.join(tmpdir, "flow.dv")
    with open(flow_dv, "w") as f:
        f.write(yaml_content)
    
    pkg = PackageLoader().load(flow_dv)
    
    task = pkg.task_m["test.t1"]
    assert len(task.tags) == 2
    assert task.tags[0].paramT.category == "type"
    assert task.tags[0].paramT.value == "unit"
    assert task.tags[1].paramT.category == "owner"
    assert task.tags[1].paramT.value == "alice"

def test_tag_inheritance(tmpdir):
    """Test tag type inheritance from base tag type"""
    yaml_content = """
package:
  name: test
  
  types:
    - name: BaseTag
      uses: std.Tag
      with:
        category: "base"
        value: "default"
    - name: DerivedTag
      uses: test.BaseTag
      with:
        category: "derived"
  
  tasks:
    - name: t1
      tags: [test.DerivedTag]
      run: echo "test"
"""
    
    flow_dv = os.path.join(tmpdir, "flow.dv")
    with open(flow_dv, "w") as f:
        f.write(yaml_content)
    
    pkg = PackageLoader().load(flow_dv)
    
    task = pkg.task_m["test.t1"]
    assert len(task.tags) == 1
    assert task.tags[0].name == "test.DerivedTag"
    # DerivedTag overrides category but inherits value from BaseTag
    assert task.tags[0].paramT.category == "derived"
    assert task.tags[0].paramT.value == "default"

def test_package_tags_simple(tmpdir):
    """Test simple tags on package"""
    yaml_content = """
package:
  name: test
  tags:
    - std.Tag:
        category: "project"
        value: "core"
  
  tasks:
    - name: t1
      run: echo "test"
"""
    
    flow_dv = os.path.join(tmpdir, "flow.dv")
    with open(flow_dv, "w") as f:
        f.write(yaml_content)
    
    pkg = PackageLoader().load(flow_dv)
    
    assert len(pkg.tags) == 1
    assert pkg.tags[0].name == "std.Tag"
    assert pkg.tags[0].paramT.category == "project"
    assert pkg.tags[0].paramT.value == "core"
