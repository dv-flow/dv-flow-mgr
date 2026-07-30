#****************************************************************************
#* test_package_cli_params.py
#*
#* Package variables exposed as command-line flags.
#*
#* A package variable is a PROJECT-WIDE knob, not one task's argument, so its
#* flag applies to whatever task is being run. The declaration site is the same
#* as for a task parameter -- `cli:` on the declaration -- because that is the
#* only place the type, default, help and accepted values live.
#*
#* The load-ordering property this pins: a package variable is read DURING the
#* load (a select family's axes, an `iff:`), so a package flag must take effect
#* there. Binding it after the load would make `--build cov` and `-D build=cov`
#* mean different things, which is the failure this design exists to avoid.
#****************************************************************************
import os
import subprocess
import sys
import textwrap

import pytest

from dv_flow.mgr.cli_args import collect_package_cli
from dv_flow.mgr.util import loadProjPkgDef


FLOW = '''\
package:
    name: q
    with:
      build:
        type: str
        value: opt
        cli: true
        values: [opt, dbg, cov]
        desc: Project-wide build variant
      quiet:
        type: bool
        value: false
        cli: {short: Q}
    tasks:
    - root: img
      strategy:
        select:
          axes: {build: [opt, dbg, cov]}
          default: {build: "${{ build }}"}
        body:
        - uses: std.Message
          with: {msg: "built ${{ this.build }}"}
'''


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(FLOW))
    return tmp_path


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------

def test_a_marked_package_variable_is_collected(proj):
    loader, pkg = loadProjPkgDef(str(proj))
    args = {a.name: a for a in collect_package_cli(pkg, loader)}
    assert set(args) == {"build", "quiet"}
    assert args["quiet"].short == "Q"
    assert args["build"].help == "Project-wide build variant"


def test_an_unmarked_package_variable_is_not_collected(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        with:
          plain: {type: str, value: x}
        tasks:
        - {root: t, uses: std.Message, with: {msg: hi}}
    '''))
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert collect_package_cli(pkg, loader) == []


def test_a_base_package_can_expose_a_project_interface(tmp_path):
    """A base project defining a flag its leaves inherit is the point of
    collecting along the package `uses:` chain -- it is how a family of
    projects gets a uniform command-line interface."""
    (tmp_path / "base.yaml").write_text(textwrap.dedent('''\
    package:
        name: base
        with:
          build: {type: str, value: opt, cli: true}
    '''))
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: leaf
        uses: base
        imports:
        - base.yaml
        tasks:
        - {root: t, uses: std.Message, with: {msg: "${{ build }}"}}
    '''))
    loader, pkg = loadProjPkgDef(str(tmp_path))
    assert [a.name for a in collect_package_cli(pkg, loader)] == ["build"]


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def test_a_package_flag_sets_the_variable(proj):
    proc = _dfm(proj, "img", "--build", "cov")
    assert proc.returncode == 0, proc.stderr
    assert "built cov" in proc.stdout


def test_the_define_form_still_works(proj):
    proc = _dfm(proj, "img", "-D", "build=dbg")
    assert proc.returncode == 0, proc.stderr
    assert "built dbg" in proc.stdout


def test_the_flag_and_the_define_agree(proj, tmp_path_factory):
    """Two spellings of the same override must not diverge. Separate project
    copies, so the second run is not simply up-to-date from the first."""
    import shutil
    other = tmp_path_factory.mktemp("copy")
    shutil.copy(str(proj / "flow.dv"), str(other / "flow.dv"))
    a = _dfm(proj, "img", "--build", "cov")
    b = _dfm(other, "img", "-D", "build=cov")
    assert a.returncode == 0, a.stderr
    assert b.returncode == 0, b.stderr
    assert "built cov" in a.stdout and "built cov" in b.stdout


def test_a_package_flag_reaches_load_time_constructs(tmp_path):
    """The property that forced the reload: a package variable that decides a
    select family's AXES is consumed while the flow loads. A flag bound after
    the load could not change the cell set at all."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        with:
          builds: {type: list, value: [opt, dbg], cli: true}
        tasks:
        - name: img
          strategy:
            select:
              axes: {build: "${{ builds }}"}
              default: all
            body:
            - uses: std.Message
              with: {msg: "built ${{ this.build }}"}
        - root: all-imgs
          uses: std.Message
          needs: [img]
          with: {msg: done}
    '''))
    proc = _dfm(tmp_path, "all-imgs", "--builds", "cov,prof")
    assert proc.returncode == 0, proc.stderr
    assert "built cov" in proc.stdout
    assert "built prof" in proc.stdout
    # The declared axis members are gone -- the family's SHAPE changed.
    assert "built opt" not in proc.stdout


def test_a_bad_value_is_rejected_at_the_parser(proj):
    """Caught by the flag itself, before the project is reloaded -- naming the
    accepted values, exactly as a task flag does."""
    proc = _dfm(proj, "img", "--build", "nosuch")
    assert proc.returncode != 0
    assert "invalid choice" in proc.stderr
    assert "opt" in proc.stderr and "cov" in proc.stderr


# ---------------------------------------------------------------------------
# Collision with a task parameter
# ---------------------------------------------------------------------------

COLLIDE = '''\
package:
    name: q
    with:
      build: {type: str, value: pkgdefault, cli: true}
    tasks:
    - root: t
      uses: std.Message
      with:
        build: {type: str, value: taskdefault, cli: true}
        msg: "pkg=${{ build }}"
'''


def test_a_collision_warns_and_names_both(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(COLLIDE))
    proc = _dfm(tmp_path, "t", "--build", "FROMCLI")
    assert proc.returncode == 0, proc.stderr
    assert "declared by both" in proc.stderr
    assert "the task parameter wins" in proc.stderr
    assert "-D build=" in proc.stderr


def test_a_collision_binds_the_task_parameter(tmp_path):
    """The rule has to be stated once and be observable: the package variable
    keeps its declared value, so the flag went to the task."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent(COLLIDE))
    proc = _dfm(tmp_path, "t", "--build", "FROMCLI")
    assert "pkg=pkgdefault" in proc.stdout


def test_the_package_variable_stays_reachable_by_define(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(COLLIDE))
    proc = _dfm(tmp_path, "t", "-D", "build=FROMDEFINE")
    assert "pkg=FROMDEFINE" in proc.stdout


# ---------------------------------------------------------------------------
# Diagnostics and help
# ---------------------------------------------------------------------------

def test_a_reserved_option_name_is_rejected(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        with:
          clean: {type: str, value: "", cli: true}
        tasks:
        - {root: t, uses: std.Message, with: {msg: hi}}
    '''))
    proc = _dfm(tmp_path, "t")
    assert proc.returncode != 0
    assert "collides with the dfm option" in proc.stderr


def test_help_lists_project_options(proj):
    """From the command line a project flag is indistinguishable from a task's
    own, so listing only half of what `dfm run <task>` accepts would mislead."""
    proc = _dfm(proj, "img", "--help")
    assert proc.returncode == 0, proc.stderr
    assert "Project options" in proc.stdout
    assert "--build" in proc.stdout
    assert "Project-wide build variant" in proc.stdout


def test_an_unknown_flag_mentions_the_project_options(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        with:
          build: {type: str, value: opt, cli: true}
        tasks:
        - {root: t, uses: std.Message, with: {msg: hi}}
    '''))
    proc = _dfm(tmp_path, "t", "--nosuch")
    assert proc.returncode != 0
    assert "This project accepts: --build" in proc.stderr


def test_a_project_with_no_flags_is_unaffected(tmp_path):
    """The common case: no package variable is exposed, so nothing changes --
    including the error text for a stray flag."""
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: q
        tasks:
        - {root: t, uses: std.Message, with: {msg: hi}}
    '''))
    proc = _dfm(tmp_path, "t", "--nosuch")
    assert proc.returncode != 0
    assert "accepts no arguments" in proc.stderr
    assert "This project accepts" not in proc.stderr
