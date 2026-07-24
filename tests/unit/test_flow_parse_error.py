"""A flow.yaml/flow.dv with a *parse* error must surface the REAL error (with
source location) -- not the misleading "Failed to find a flow.yaml" that results
when a broken file is silently skipped like a fragment.

Regression guard for the masking bug: `_is_package_file` used to swallow every
exception and return False, so a syntax error made the directory search fall
through to "no package file found". See dv_flow.mgr.util.util._classify_flow_file
and loadProjPkgDef.
"""
import os
import pytest
from dv_flow.mgr.util import loadProjPkgDef
from dv_flow.mgr.util.util import _classify_flow_file, _yaml_error_loc
from dv_flow.mgr.task_data import TaskMarker, SeverityE


# A YAML mapping-value error at a known spot (line 5, column ~16): the extra
# indent turns `bad_indent:` into a mapping value where one isn't allowed.
BROKEN_FLOW = """\
package:
  name: broken
  tasks:
  - name: a
     bad_indent: x
"""

FRAGMENT_FLOW = """\
fragment:
  tasks: []
"""

GOOD_FLOW = """\
package:
  name: good
  tasks:
  - name: t
    uses: std.Message
    with: {msg: hi}
"""


def _write(d, name, text):
    p = os.path.join(str(d), name)
    with open(p, "w") as fp:
        fp.write(text)
    return p


# ---------------------------------------------------------------------------
# _classify_flow_file: the three-way classification the fix hinges on
# ---------------------------------------------------------------------------

def test_classify_package_file(tmp_path):
    p = _write(tmp_path, "flow.yaml", GOOD_FLOW)
    is_pkg, err = _classify_flow_file(p)
    assert is_pkg is True and err is None


def test_classify_fragment_file(tmp_path):
    p = _write(tmp_path, "flow.yaml", FRAGMENT_FLOW)
    is_pkg, err = _classify_flow_file(p)
    assert is_pkg is False and err is None


def test_classify_parse_error_returns_the_exception(tmp_path):
    # The whole point: a parse error is distinguishable from a fragment -- it
    # comes back as the actual exception, not a bare False.
    p = _write(tmp_path, "flow.yaml", BROKEN_FLOW)
    is_pkg, err = _classify_flow_file(p)
    assert is_pkg is False
    assert err is not None
    assert "mapping values are not allowed" in str(err)


# ---------------------------------------------------------------------------
# loadProjPkgDef: the real error surfaces (both listener and no-listener paths)
# ---------------------------------------------------------------------------

def test_parse_error_raises_when_no_listener(tmp_path):
    # Programmatic callers (and tests) with no listener see the real exception,
    # NOT a "package not found" -- and NOT a silently-returned None.
    _write(tmp_path, "flow.yaml", BROKEN_FLOW)
    with pytest.raises(Exception) as ei:
        loadProjPkgDef(str(tmp_path))
    msg = str(ei.value)
    assert "mapping values are not allowed" in msg
    assert "Failed to find" not in msg


def test_parse_error_emits_located_marker_with_listener(tmp_path):
    # The CLI path passes a listener: the real error is reported as a located
    # Error marker and pkg comes back None (so the command exits cleanly).
    _write(tmp_path, "flow.yaml", BROKEN_FLOW)
    markers = []
    loader, pkg = loadProjPkgDef(str(tmp_path), listener=markers.append)

    assert pkg is None
    errs = [m for m in markers if m.severity == SeverityE.Error]
    assert len(errs) == 1, "expected exactly one error marker, got %s" % markers
    m = errs[0]
    # The real parse error, not the "not found" fallback.
    assert "mapping values are not allowed" in m.msg
    assert "Failed to find" not in m.msg
    # ...located at the offending line/column of the broken file.
    assert m.loc is not None
    assert m.loc.path.endswith("flow.yaml")
    assert m.loc.line == 5


def test_no_masking_as_not_found(tmp_path):
    # Explicit regression: the broken file must NOT be reported as a missing
    # package file (the pre-fix behavior).
    _write(tmp_path, "flow.yaml", BROKEN_FLOW)
    markers = []
    loader, pkg = loadProjPkgDef(str(tmp_path), listener=markers.append)
    joined = " | ".join(m.msg for m in markers)
    assert "Failed to find a 'flow.yaml" not in joined
    assert "does not define a package" not in joined


# ---------------------------------------------------------------------------
# The fix must not break the legitimate fragment-skip behavior
# ---------------------------------------------------------------------------

def test_valid_fragment_in_cwd_still_finds_parent_package(tmp_path):
    # A valid fragment in the start dir is still skipped; the package in the
    # parent directory is found normally (a parse error is the ONLY reason to
    # stop the search early).
    _write(tmp_path, "flow.yaml", GOOD_FLOW)
    sub = tmp_path / "sub"
    sub.mkdir()
    _write(sub, "flow.yaml", FRAGMENT_FLOW)

    markers = []
    loader, pkg = loadProjPkgDef(str(sub), listener=markers.append)
    assert not [m for m in markers if m.severity == SeverityE.Error]
    assert pkg is not None
    assert pkg.name == "good"


# ---------------------------------------------------------------------------
# _yaml_error_loc: 0-based YAML marks are converted to 1-based for display
# ---------------------------------------------------------------------------

def test_yaml_error_loc_is_one_based(tmp_path):
    import yaml
    p = _write(tmp_path, "flow.yaml", BROKEN_FLOW)
    try:
        with open(p) as fp:
            yaml.safe_load(fp)
        pytest.fail("expected a YAML parse error")
    except Exception as e:
        loc = _yaml_error_loc(e, p)
        assert loc.line == 5          # yaml reports 0-based line 4 -> 5
        assert loc.pos >= 1
