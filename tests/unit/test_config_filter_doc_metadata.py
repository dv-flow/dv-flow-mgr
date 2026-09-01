"""Prose and source locations for configurations and filters.

A configuration is selected by name from the command line by whoever runs the
flow -- which makes it the one thing in a package chosen by someone who did not
write it. Until now it had nowhere to say what it was for.

Source locations matter for the same reason they do on a task: a diagnostic,
or a documentation tool, should point at the definition rather than at the file
that happens to contain it. Both `filters:` and `configs:` are declared at
package or fragment level, so without an entry in the srcinfo loader's scope
set, the only location available is the whole file.
"""
import os

import pytest

from dv_flow.mgr import PackageLoader
from .marker_collector import MarkerCollector


def _load(tmpdir, flow, name="flow.dv"):
    with open(os.path.join(str(tmpdir), name), "w") as f:
        f.write(flow)
    collector = MarkerCollector()
    pkg = PackageLoader(marker_listeners=[collector]).load(
        os.path.join(str(tmpdir), name))
    assert [m.msg for m in collector.markers] == []
    return pkg


FLOW = """\
package:
    name: p
    imports:
    - std

    filters:
    - export: by_arch
      desc: Select inputs matching an architecture
      doc: |
        Longer prose about what this keeps.
      with:
        arch:
          type: str
      expr: "input[] | select(input.arch == $arg0)"

    configs:
    - name: debug
      desc: Build with debug output
      doc: |
        Select it with `dfm run -c debug`.
      tasks:
      - override: t1
        uses: std.Message
        with:
          msg: "debug"

    tasks:
    - name: t1
      uses: std.Message
      with:
        msg: "release"
"""


def _config(pkg, name):
    for cfg in pkg.all_configs:
        if cfg.name == name:
            return cfg
    raise AssertionError("no config named %s" % name)


def test_config_carries_desc(tmpdir):
    assert _config(_load(tmpdir, FLOW), "debug").desc == \
        "Build with debug output"


def test_config_carries_doc(tmpdir):
    assert "dfm run -c debug" in _config(_load(tmpdir, FLOW), "debug").doc


def test_config_has_a_source_location(tmpdir):
    cfg = _config(_load(tmpdir, FLOW), "debug")
    assert cfg.srcinfo is not None
    assert cfg.srcinfo.file.endswith("flow.dv")
    assert cfg.srcinfo.lineno > 0


def test_filter_has_a_source_location(tmpdir):
    pkg = _load(tmpdir, FLOW)
    fd = pkg.pkg_def.filters[0]
    assert fd.srcinfo is not None
    assert fd.srcinfo.file.endswith("flow.dv")
    assert fd.srcinfo.lineno > 0


def test_config_prose_is_optional(tmpdir):
    """Every existing flow file has configurations with neither field."""
    pkg = _load(tmpdir, """\
package:
    name: p
    imports:
    - std
    configs:
    - name: plain
      tasks: []
    tasks: []
""")
    cfg = _config(pkg, "plain")
    assert cfg.desc is None
    assert cfg.doc is None


def test_the_location_points_at_the_definition_not_the_file(tmpdir):
    """Two configurations in one file must not report the same line."""
    pkg = _load(tmpdir, """\
package:
    name: p
    imports:
    - std
    configs:
    - name: first
      tasks: []
    - name: second
      tasks: []
    tasks: []
""")
    assert _config(pkg, "first").srcinfo.lineno != \
        _config(pkg, "second").srcinfo.lineno
