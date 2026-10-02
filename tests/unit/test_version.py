#****************************************************************************
#* test_version.py
#*
#* dfm's version: one value in dv_flow/mgr/__version__.py, reported by
#* `dfm --version`.
#*
#* That file is the ONE source: pyproject.toml reads it, so the wheel's
#* metadata and the runtime version cannot drift apart again (the old
#* hand-maintained pair had: `__version__` said 1.5.0 at 1.12.0).
#****************************************************************************
import os
import re
import subprocess
import sys
import textwrap

import dv_flow.mgr
from dv_flow.mgr import __version__ as version_mod_attr
from dv_flow.mgr.__version__ import BASE, SUFFIX, get_version


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))


def test_pyproject_reads_the_version_rather_than_declaring_one():
    with open(os.path.join(ROOT, "pyproject.toml")) as f:
        text = f.read()
    assert not re.search(r'^version\s*=\s*"', text, re.M), \
        "pyproject.toml declares a version; __version__.py is the only source"
    assert re.search(r'^dynamic\s*=\s*\[[^]]*"version"', text, re.M)
    assert re.search(
        r'^version\s*=\s*\{\s*attr\s*=\s*"dv_flow\.mgr\.__version__\._pkg_version"',
        text, re.M)


def test_the_version_file_imports_nothing_dfm():
    """setuptools loads it alone, in an isolated build without dfm's
    dependencies installed."""
    with open(os.path.join(ROOT, "src", "dv_flow", "mgr", "__version__.py")) as f:
        imports = [l.strip() for l in f
                   if re.match(r"\s*(import|from)\s", l)]
    assert all(l in ("import os", "import subprocess") for l in imports), imports


def test_package_exposes_the_version_string():
    assert version_mod_attr == dv_flow.mgr.__version__ == BASE + SUFFIX
    assert get_version().startswith(BASE)


def test_dash_dash_version_prints_it_and_exits():
    for flag in ("--version", "-V"):
        proc = subprocess.run([sys.executable, "-m", "dv_flow.mgr", flag],
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "dfm %s" % get_version()


def test_a_project_may_still_declare_a_version_flag(tmp_path):
    """`--version` is read before the subcommand only, so it cannot collide
    with a task's flag and is not reserved against one."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        with:
          version: {type: str, value: "1", cli: true}
        tasks:
        - {root: t, uses: std.Message, with: {msg: "v=${{ version }}"}}
    '''))
    proc = subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run", "t", "--version", "7"],
        cwd=str(tmp_path), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "v=7" in proc.stdout
