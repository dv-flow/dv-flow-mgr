"""B1 tests: import forms -- name, name+from (pin), and `as:` aliasing."""
import asyncio
import os

import pytest

from dv_flow.mgr import PackageLoader, TaskGraphBuilder
from dv_flow.mgr.task_runner import TaskSetRunner

from .marker_collector import MarkerCollector


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _run(pkg, tmpdir, task):
    builder = TaskGraphBuilder(root_pkg=pkg, rundir=os.path.join(str(tmpdir), "rundir"))
    runner = TaskSetRunner(os.path.join(str(tmpdir), "rundir"))
    node = builder.mkTaskNode(task)
    return asyncio.run(runner.run(node)), builder


VLT_FLOW = """
package:
    name: hdlsim.vlt
    tasks:
    - name: SimImage
      uses: std.Message
      with:
        msg: "vlt.SimImage"
"""


def test_import_name_with_from(tmpdir):
    """`{name: foo, from: <file>}` pins a location without any map."""
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "vlt", "flow.dv"), VLT_FLOW)
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - name: hdlsim.vlt
      from: vendor/vlt/flow.dv
    tasks:
    - name: build
      uses: hdlsim.vlt.SimImage
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    assert "hdlsim.vlt" in pkg.pkg_m
    out, _ = _run(pkg, tmpdir, "top.build")
    assert out is not None


def test_import_alias_qualified_task(tmpdir):
    """`as: sim` makes `sim.SimImage` resolve to hdlsim.vlt.SimImage."""
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "vlt", "flow.dv"), VLT_FLOW)
    _write(os.path.join(td, "flow.dv"), """
package:
    name: proj
    imports:
    - name: hdlsim.vlt
      from: vendor/vlt/flow.dv
      as: sim
    tasks:
    - name: build
      uses: sim.SimImage
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    assert pkg.pkg_alias_m.get("sim") == "hdlsim.vlt"
    out, builder = _run(pkg, tmpdir, "proj.build")
    assert out is not None
    # The alias-qualified task name resolves in the builder
    assert builder.findTask("proj.build") is not None


def test_import_alias_param(tmpdir):
    """A qualified param reference through an alias resolves at load time."""
    td = str(tmpdir)
    _write(os.path.join(td, "vendor", "ip", "flow.dv"), """
package:
    name: vendor.ip
    with:
      WIDTH:
        type: int
        value: 16
    tasks:
    - name: t
      uses: std.Message
      with:
        msg: "ip"
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: proj
    imports:
    - name: vendor.ip
      from: vendor/ip/flow.dv
      as: ip
    tasks:
    - name: build
      uses: std.Message
      with:
        msg: "width=${{ ip.WIDTH }}"
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    assert pkg.pkg_alias_m.get("ip") == "vendor.ip"
    out, _ = _run(pkg, tmpdir, "proj.build")
    assert out is not None


def test_import_alias_collision_error(tmpdir):
    """Two imports aliased to the same name produce an error marker."""
    td = str(tmpdir)
    _write(os.path.join(td, "a", "flow.dv"), VLT_FLOW)
    _write(os.path.join(td, "b", "flow.dv"), """
package:
    name: hdlsim.vcs
    tasks:
    - name: SimImage
      uses: std.Message
      with:
        msg: "vcs"
""")
    _write(os.path.join(td, "flow.dv"), """
package:
    name: proj
    imports:
    - name: hdlsim.vlt
      from: a/flow.dv
      as: sim
    - name: hdlsim.vcs
      from: b/flow.dv
      as: sim
""")
    mc = MarkerCollector()
    PackageLoader(marker_listeners=[mc]).load(os.path.join(td, "flow.dv"))
    assert any("alias" in m.msg and "sim" in m.msg for m in mc.markers), \
        [m.msg for m in mc.markers]


def test_import_name_only_via_registry(tmpdir):
    """Regression: a bare registry-name import (std) still works."""
    td = str(tmpdir)
    _write(os.path.join(td, "flow.dv"), """
package:
    name: top
    imports:
    - std
    tasks:
    - name: build
      uses: std.Message
      with:
        msg: "hi"
""")
    pkg = PackageLoader().load(os.path.join(td, "flow.dv"))
    out, _ = _run(pkg, tmpdir, "top.build")
    assert out is not None
