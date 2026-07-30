#****************************************************************************
#* test_select_e2e.py
#*
#* A realistic shape: an image family (view x build) plus a `matrix:` regression
#* suite that addresses cells by name.
#*
#* The central claim under test is that the two selection mechanisms compose in
#* the right direction WITHOUT knowing about each other:
#*   * `std.TestRunner` prunes from the CONSUMER side -- a deselected case is
#*     never built;
#*   * `select:` never generates from the PRODUCER side -- a cell nobody asks
#*     for does not exist.
#* The seam between them is the cell name. Together, `--views rtl -D build=cov`
#* must compile exactly one image out of six.
#****************************************************************************
import os
import subprocess
import sys
import textwrap

import pytest


FLOW = '''\
package:
    name: p
    with:
      build: {type: str, value: opt}
    tasks:
    # Per-variant build flags. What makes a cell's identity differ by more than
    # its name -- and, in a real flow, what a contract check would bind to.
    - {name: flags-opt,  uses: std.Message, with: {msg: "flags opt"}}
    - {name: flags-cov,  uses: std.Message, with: {msg: "flags cov"}}

    # The ARTIFACT family. Cells are independent; asking for one builds one.
    - root: img
      desc: Simulation images
      with:
        view:  {type: str, value: tlm, cli: true, values: [tlm, wb, rtl]}
        build: {type: str, value: "${{ build }}", cli: true, values: [opt, cov]}
      strategy:
        select:
          axes:
            view:  [tlm, wb, rtl]
            build: [opt, cov]
          default: {view: "${{ view }}", build: "${{ build }}"}
        body:
        - shell: bash
          needs: ["flags-${{ this.build }}"]
          run: touch ${{ rundir }}/../IMG-${{ this.view }}-${{ this.build }}

    # The REGRESSION. A suite IS all of its cells, so it stays a matrix -- and
    # it reaches the image family by cell name, with no alias map in between.
    - name: suite
      strategy:
        matrix:
          view: [tlm, wb, rtl]
          case:
          - {name: smoke}
          - {name: arb}
        body:
        - name: "${{ this.view }}-${{ this.case.name }}"
          uses: std.Message
          needs: ["img.${{ this.view }}.${{ build }}"]
          with: {msg: "${{ this.view }}-${{ this.case.name }}"}
          tags:
          - std.Test: {case: "${{ this.case.name }}", view: "${{ this.view }}"}

    - root: tests
      uses: std.TestRunner
      needs: [suite]
'''


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(FLOW))
    return tmp_path


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


def _images(d):
    rundir = os.path.join(str(d), "rundir")
    if not os.path.isdir(rundir):
        return []
    return sorted(f[4:] for f in os.listdir(rundir) if f.startswith("IMG-"))


def test_a_view_selection_compiles_exactly_one_image(proj):
    """Six cells exist; `--views rtl -D build=cov` builds one. The consumer-side
    prune decides which cases run, and the producer-side laziness means the
    images the dropped cases would have needed are never generated."""
    proc = _dfm(proj, "tests", "--views", "rtl", "-D", "build=cov")
    assert proc.returncode == 0, proc.stderr
    assert _images(proj) == ["rtl-cov"]


def test_selecting_a_case_still_builds_only_its_views_image(proj):
    proc = _dfm(proj, "tests", "--tests", "arb", "--views", "wb")
    assert proc.returncode == 0, proc.stderr
    assert _images(proj) == ["wb-opt"]


def test_the_full_regression_builds_one_image_per_view(proj):
    """Two cases share each view's image -- so three images, not six runs of
    the image build. This is the sharing property at regression scale."""
    proc = _dfm(proj, "tests")
    assert proc.returncode == 0, proc.stderr
    assert _images(proj) == ["tlm-opt", "wb-opt", "rtl-opt"] or \
        _images(proj) == sorted(["tlm-opt", "wb-opt", "rtl-opt"])


def test_the_build_variant_reaches_every_image(proj):
    """One package-level knob moves the whole regression onto another variant,
    which is what the alias-map idiom could not express."""
    proc = _dfm(proj, "tests", "-D", "build=cov")
    assert proc.returncode == 0, proc.stderr
    assert _images(proj) == sorted(["tlm-cov", "wb-cov", "rtl-cov"])


def test_building_one_image_directly_builds_nothing_else(proj):
    proc = _dfm(proj, "img", "--view", "wb", "--build", "cov")
    assert proc.returncode == 0, proc.stderr
    assert _images(proj) == ["wb-cov"]


def test_a_selection_matching_nothing_is_still_an_error(proj):
    """The select work must not weaken TestRunner's strictness: a green run
    that tested nothing is the outcome that matters most to prevent."""
    proc = _dfm(proj, "tests", "--tests", "nosuch")
    assert proc.returncode != 0
    assert _images(proj) == []
