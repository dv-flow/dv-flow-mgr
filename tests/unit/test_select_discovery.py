#****************************************************************************
#* test_select_discovery.py
#*
#* Finding out what a `select:` family offers.
#*
#* Cells are runnable tasks, which is what makes them addressable -- and would
#* make a 3x4 family twelve lines in every task listing. The rule: the LISTING
#* shows the family (with its axes standing in for the cells), and `show task`
#* is where the cells themselves live.
#****************************************************************************
import json
import os
import subprocess
import sys
import textwrap
import time

import pytest


FLOW = '''\
package:
    name: p
    tasks:
    - root: img
      desc: Simulation images
      strategy:
        select:
          axes:
            view:  [tlm, wb, rtl]
            build: [opt, dbg, cov, prof]
        body:
        - uses: std.Message
          with: {msg: "${{ this.view }}-${{ this.build }}"}
    - root: other
      desc: Something else
      uses: std.Message
      with: {msg: other}
'''


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(FLOW))
    return tmp_path


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr"] + list(args),
        cwd=str(d), capture_output=True, text=True)


# ---------------------------------------------------------------------------
# The task listing
# ---------------------------------------------------------------------------

def test_the_listing_shows_the_family_not_its_cells(proj):
    proc = _dfm(proj, "run")
    assert proc.returncode == 0, proc.stderr
    assert "p.img " in proc.stdout
    # Twelve cell lines would drown the two tasks this project actually offers.
    assert "p.img.tlm.opt" not in proc.stdout
    assert "p.other" in proc.stdout


def test_the_listing_shows_the_axes(proj):
    """The axes are what the name offers, so they stand in for the cells."""
    proc = _dfm(proj, "run")
    assert "view: tlm,wb,rtl" in proc.stdout
    assert "build: opt,dbg,cov,prof" in proc.stdout


def test_an_ordinary_task_listing_is_unchanged(proj):
    proc = _dfm(proj, "run")
    assert "p.other - Something else" in proc.stdout


# ---------------------------------------------------------------------------
# show task
# ---------------------------------------------------------------------------

def test_show_task_lists_the_cells(proj):
    proc = _dfm(proj, "show", "task", "p.img")
    assert proc.returncode == 0, proc.stderr
    assert "Variant axes" in proc.stdout
    for cell in ("p.img.tlm.opt", "p.img.rtl.prof"):
        assert cell in proc.stdout


def test_show_task_marks_the_default(proj):
    proc = _dfm(proj, "show", "task", "p.img")
    assert "default: view=tlm, build=opt" in proc.stdout


def test_show_task_describes_a_gate(proj, tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes: {build: [opt, prof]}
              default: all
            body:
            - uses: std.Message
              with: {msg: hi}
    '''))
    proc = _dfm(tmp_path, "show", "task", "p.img")
    assert "a gate over every cell" in proc.stdout


def test_show_task_on_a_cell_names_its_family_and_bindings(proj):
    proc = _dfm(proj, "show", "task", "p.img.rtl.cov")
    assert proc.returncode == 0, proc.stderr
    assert "Variant of p.img" in proc.stdout
    assert "view = rtl" in proc.stdout
    assert "build = cov" in proc.stdout


def test_show_task_json_carries_the_cells(proj):
    """`--json` is what a completion script or an editor integration reads, so
    the cells have to be there and not only in the rendered view."""
    proc = _dfm(proj, "show", "task", "p.img", "--json")
    assert proc.returncode == 0, proc.stderr
    info = json.loads(proc.stdout)
    assert info['select']['axes']['view'] == ['tlm', 'wb', 'rtl']
    assert len(info['select']['cells']) == 12
    assert info['select']['mode'] == 'alias'


def test_show_task_on_an_ordinary_task_has_no_select_key(proj):
    proc = _dfm(proj, "show", "task", "p.other", "--json")
    info = json.loads(proc.stdout)
    assert 'select' not in info
    assert 'select_cell' not in info


# ---------------------------------------------------------------------------
# Completion
# ---------------------------------------------------------------------------

def test_completion_offers_cells(proj):
    """Cells are ordinary namespace entries, so they are in the suffix index
    already -- this pins that they stay there."""
    proc = _dfm(proj, "complete", "img.")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.split()
    assert "img.tlm.opt" in out
    assert "img.rtl.prof" in out


def test_completion_stays_fast_on_a_large_family(tmp_path):
    """A 6x8 family is 48 cells, and the suffix index is built over every task
    name. Guards against a quadratic index showing up as a laggy prompt."""
    views = [f"v{i}" for i in range(6)]
    builds = [f"b{i}" for i in range(8)]
    (tmp_path / "flow.dv").write_text(textwrap.dedent('''\
    package:
        name: p
        tasks:
        - root: img
          strategy:
            select:
              axes:
                view: [%s]
                build: [%s]
            body:
            - uses: std.Message
              with: {msg: hi}
    ''') % (", ".join(views), ", ".join(builds)))

    start = time.monotonic()
    proc = _dfm(tmp_path, "complete", "img.")
    elapsed = time.monotonic() - start
    assert proc.returncode == 0, proc.stderr
    assert len(proc.stdout.split()) >= 48
    # Generous: this is a smoke alarm for an algorithmic regression, not a
    # benchmark. A whole interpreter start-up fits inside it.
    assert elapsed < 15.0, "completion took %.1fs" % elapsed
