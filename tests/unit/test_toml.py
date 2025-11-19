import os
import asyncio
from dv_flow.mgr import PackageLoader, TaskGraphBuilder, TaskSetRunner


def test_load_toml_pkg(tmpdir):
    toml = """
[package]
name = "top"

[[package.tasks]]
name = "hello"
uses = "std.Message"
[package.tasks.with]
msg = "hi"
"""
    with open(os.path.join(tmpdir, "flow.toml"), "w") as f:
        f.write(toml)
    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.toml"))
    assert pkg is not None
    assert pkg.name == "top"
    assert "top.hello" in pkg.task_m


def test_import_toml_from_yaml(tmpdir):
    root_yaml = """
package:
  name: top
  imports:
  - sub/flow.toml
  tasks:
  - name: top
    uses: subpkg.hello
"""
    sub_toml = """
[package]
name = "subpkg"

[[package.tasks]]
name = "hello"
uses = "std.Message"
[package.tasks.with]
msg = "from toml"
"""
    os.makedirs(os.path.join(tmpdir, "sub"))
    with open(os.path.join(tmpdir, "flow.dv"), "w") as f:
        f.write(root_yaml)
    with open(os.path.join(tmpdir, "sub/flow.toml"), "w") as f:
        f.write(sub_toml)
    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.dv"))
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    t = builder.mkTaskNode("top.top")
    assert t is not None


def test_import_yaml_from_toml(tmpdir):
    root_toml = """
[package]
name = "top"
imports = ["sub/flow.dv"]

[[package.tasks]]
name = "top"
uses = "subpkg.hello"
"""
    sub_yaml = """
package:
  name: subpkg
  tasks:
  - name: hello
    uses: std.Message
    with:
      msg: from yaml
"""
    os.makedirs(os.path.join(tmpdir, "sub"))
    with open(os.path.join(tmpdir, "flow.toml"), "w") as f:
        f.write(root_toml)
    with open(os.path.join(tmpdir, "sub/flow.dv"), "w") as f:
        f.write(sub_yaml)
    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.toml"))
    builder = TaskGraphBuilder(pkg, os.path.join(tmpdir, "rundir"))
    t = builder.mkTaskNode("top.top")
    assert t is not None


def test_fragment_toml_and_yaml(tmpdir):
    root_toml = """
[package]
name = "top"
fragments = ["frag.toml", "frag.dv"]
"""
    frag_toml = """
[fragment]

[[fragment.tasks]]
name = "t_from_toml"
uses = "std.Message"
[fragment.tasks.with]
msg = "ft"
"""
    frag_yaml = """
fragment:
  tasks:
  - name: t_from_yaml
    uses: std.Message
    with:
      msg: fy
"""
    with open(os.path.join(tmpdir, "flow.toml"), "w") as f:
        f.write(root_toml)
    with open(os.path.join(tmpdir, "frag.toml"), "w") as f:
        f.write(frag_toml)
    with open(os.path.join(tmpdir, "frag.dv"), "w") as f:
        f.write(frag_yaml)
    pkg = PackageLoader().load(os.path.join(tmpdir, "flow.toml"))
    assert "top.t_from_toml" in pkg.task_m
    assert "top.t_from_yaml" in pkg.task_m
