"""cache_util with a symlinked rundir (e.g. a rundir store entry)."""
import os

from dv_flow.mgr.cache_util import convert_output_to_template, validate_output_paths
from dv_flow.mgr.fileset import FileSet


def _setup(tmp_path):
    real = tmp_path / "store" / "entry"
    (real / "pkg.t").mkdir(parents=True)
    link = tmp_path / "proj" / "rundir"
    link.parent.mkdir()
    os.symlink(real, link)
    return str(link), str(real)


def _fs(basedir):
    return FileSet(filetype="text", basedir=basedir, files=["a.txt"])


def test_validate_logical_basedir(tmp_path):
    link, real = _setup(tmp_path)
    assert validate_output_paths([_fs(os.path.join(link, "pkg.t"))], link)


def test_validate_resolved_basedir(tmp_path):
    link, real = _setup(tmp_path)
    assert validate_output_paths([_fs(os.path.join(real, "pkg.t"))], link)


def test_validate_outside(tmp_path):
    link, real = _setup(tmp_path)
    assert not validate_output_paths([_fs(str(tmp_path / "other"))], link)


def test_template_logical_and_resolved(tmp_path):
    link, real = _setup(tmp_path)
    for base in (os.path.join(link, "pkg.t"), os.path.join(real, "pkg.t")):
        t = convert_output_to_template([_fs(base)], link)
        assert t["output"][0]["basedir"] == "${{ rundir }}/pkg.t"


def test_template_outside_unchanged(tmp_path):
    link, real = _setup(tmp_path)
    other = str(tmp_path / "other")
    t = convert_output_to_template([_fs(other)], link)
    assert t["output"][0]["basedir"] == other
