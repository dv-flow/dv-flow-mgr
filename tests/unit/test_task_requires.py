#****************************************************************************
#* test_task_requires.py
#*
#* `requires:` -- a task's contract, checked at graph build.
#*
#* The property that makes it worth having: a slot a base project declared and
#* a leaf never filled otherwise RUNS AND REPORTS SUCCESS. That is the worst
#* outcome for a uniform project interface, because it makes `dfm run <verb>`
#* trustworthy in some projects and meaningless in others.
#*
#* The ordering is the mechanism, not an implementation detail. Checks run
#* after override resolution (so a leaf's `override:` is what satisfies a base's
#* requirement), after `iff:` (a node that does not exist is not checked), and
#* after elaboration (so they see the wired graph, not the declaration).
#****************************************************************************
import os
import subprocess
import sys
import textwrap

import pytest

from dv_flow.mgr import TaskGraphBuilder
from dv_flow.mgr.util import loadProjPkgDef


def _write(tmp_path, flow):
    (tmp_path / "flow.dv").write_text(textwrap.dedent(flow))
    return tmp_path


def _dfm(d, *args):
    return subprocess.run(
        [sys.executable, "-m", "dv_flow.mgr", "run"] + list(args),
        cwd=str(d), capture_output=True, text=True)


def _build(tmp_path, task):
    """Build `task`, returning the error markers the checks produced."""
    loader, pkg = loadProjPkgDef(str(tmp_path))
    msgs = []
    b = TaskGraphBuilder(root_pkg=pkg, rundir=str(tmp_path / "rundir"),
                         loader=loader, marker_l=msgs.append)
    b.mkTaskNode(task)
    return [m.msg for m in msgs]


# ---------------------------------------------------------------------------
# std.check.Implemented
# ---------------------------------------------------------------------------

UNFILLED = '''\
package:
    name: p
    tasks:
    - export: src-rtl
      desc: Provides synthesizable RTL sources
      requires:
      - std.check.Implemented
    - root: build
      uses: std.Message
      needs: [src-rtl]
      with: {msg: building}
'''


def test_an_unfilled_slot_is_reported(tmp_path):
    msgs = _build(_write(tmp_path, UNFILLED), "p.build")
    assert any("not implemented" in m for m in msgs)


def test_an_unfilled_slot_fails_the_run(tmp_path):
    """Reporting is not enough -- a contract that reports and then runs anyway
    is worse than no contract, because it teaches people to ignore it."""
    proc = _dfm(_write(tmp_path, UNFILLED), "build")
    assert proc.returncode != 0
    assert "not implemented" in proc.stdout + proc.stderr


def test_an_override_that_fills_the_slot_satisfies_it(tmp_path):
    """The whole mechanism: the requirement is declared on the base task and
    checked on the effective one, so a leaf's `override:` is what answers it."""
    d = _write(tmp_path, UNFILLED + """\
    - override: src-rtl
      needs: [rtl-files]
    - name: rtl-files
      uses: std.Message
      with: {msg: rtl}
""")
    assert _build(d, "p.build") == []


def test_a_task_with_a_run_body_satisfies_it(tmp_path):
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - root: t
          requires: [std.check.Implemented]
          shell: bash
          run: echo hi
    ''')
    assert _build(d, "p.t") == []


def test_a_disabled_task_is_not_checked(tmp_path):
    """A project may legitimately conditionalize a slot out; a node that does
    not exist has no contract to answer."""
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - name: slot
          iff: false
          requires: [std.check.Implemented]
        - root: build
          uses: std.Message
          needs: [slot]
          with: {msg: b}
    ''')
    assert _build(d, "p.build") == []


# ---------------------------------------------------------------------------
# std.check.Needs -- produces
# ---------------------------------------------------------------------------

# ONE artifact type, qualified by ATTRIBUTES where the producer declares them.
# A variant is a property of the image, not a different kind of thing, so there
# is no type per variant.
#
# Note what is being pinned and what is not: this is a COARSE static gate over
# what tasks DECLARE. It is not a proof about the data. A requirement that
# depends on what a run actually emitted belongs in the consuming task, at
# runtime -- see test_a_static_contract_does_not_replace_a_runtime_check.
TYPED = '''\
package:
    name: p
    types:
    - {name: SimImg, uses: std.DataItem}
    tasks:
    - name: img
      strategy:
        select:
          axes: {build: [opt, prof]}
        body:
        - uses: std.Message
          with: {msg: "image ${{ this.build }}"}
          produces:
          - type: p.SimImg
            build: "${{ this.build }}"
            profile: "${{ this.build == 'prof' }}"
    - root: Analyze
      uses: std.Message
      with: {msg: analyzing}
      requires:
      - std.check.Needs:
          produces: {type: p.SimImg, profile: true}
          hint: |
            Analyze needs a profiling build. Try:
                dfm run Analyze --needs p.img.prof
    - root: Package
      uses: std.Message
      with: {msg: packaging}
      requires:
      - {std.check.Needs: {produces: {type: p.SimImg}}}
'''


def test_an_attribute_qualified_input_is_accepted(tmp_path):
    d = _write(tmp_path, TYPED)
    proc = _dfm(d, "Analyze", "--needs", "img.prof")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_wrong_variant_is_rejected(tmp_path):
    d = _write(tmp_path, TYPED)
    proc = _dfm(d, "Analyze", "--needs", "img.opt")
    assert proc.returncode != 0
    out = proc.stdout + proc.stderr
    assert "{type: p.SimImg, profile: true}" in out
    # The diagnostic shows what the input DOES offer, so the mismatch is
    # visible rather than merely asserted.
    assert "build: opt" in out and "profile: false" in out


def test_an_unqualified_requirement_accepts_any_variant(tmp_path):
    """Subset match: the producer may carry attributes the requirement does not
    name. That is what lets one artifact type serve both consumers."""
    d = _write(tmp_path, TYPED)
    for variant in ("opt", "prof"):
        proc = _dfm(d, "Package", "--needs", "img.%s" % variant)
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_an_attribute_may_be_produced_transitively(tmp_path):
    """What qualifies an artifact is often declared upstream of it -- by the
    flag-holder that turned profiling on rather than by the image -- so the
    search follows needs.

    Note the `passthrough: all` on the image body, and that it is load-bearing:
    forwarding is a function of `passthrough` AND `consumes`, and the DEFAULT
    combination (`unused` + an undeclared `consumes`, which defaults to *all*)
    forwards nothing. An undeclared task is a sink, so an upstream declaration
    does not reach past it -- which is a good reason to write a contract
    against what the DIRECT need declares wherever possible.
    """
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: SimImg, uses: std.DataItem}
        tasks:
        - {name: flags-opt, uses: std.Message, with: {msg: opt}}
        - name: flags-prof
          uses: std.Message
          with: {msg: prof}
          produces:
          - {type: p.BuildFlags, profile: true}
        - name: img
          strategy:
            select:
              axes: {build: [opt, prof]}
            body:
            - uses: std.Message
              passthrough: all
              needs: ["flags-${{ this.build }}"]
              with: {msg: "image ${{ this.build }}"}
        - root: Analyze
          uses: std.Message
          with: {msg: a}
          requires:
          - {std.check.Needs: {produces: {type: p.BuildFlags, profile: true}}}
    ''')
    assert _dfm(d, "Analyze", "--needs", "img.prof").returncode == 0
    assert _dfm(d, "Analyze", "--needs", "img.opt").returncode != 0


def test_a_bare_string_is_shorthand_for_a_type(tmp_path):
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: SimImg, uses: std.DataItem}
        tasks:
        - name: img
          uses: std.Message
          with: {msg: i}
          produces:
          - {type: p.SimImg, build: opt}
        - root: t
          uses: std.Message
          with: {msg: t}
          requires:
          - {std.check.Needs: {produces: p.SimImg}}
    ''')
    assert _dfm(d, "t", "--needs", "img").returncode == 0


def test_the_diagnostic_says_what_to_type(tmp_path):
    """A diagnostic that names the problem without naming the fix makes the
    reader do the work the check already did."""
    d = _write(tmp_path, TYPED)
    proc = _dfm(d, "Analyze", "--needs", "img.opt")
    out = proc.stdout + proc.stderr
    assert "dfm run Analyze --needs p.img.prof" in out
    assert "required by  std.check.Needs" in out


def test_the_wrong_variant_is_rejected_before_anything_builds(tmp_path):
    """Rejection at graph build, not at execution: the point is to fail before
    paying for a compile that was going to be useless."""
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: SimImg, uses: std.DataItem}
        tasks:
        - name: img
          strategy:
            select:
              axes: {build: [opt, prof]}
            body:
            - shell: bash
              run: touch ${{ rundir }}/../BUILT-${{ this.build }}
              produces:
              - type: p.SimImg
                profile: "${{ this.build == 'prof' }}"
        - root: Analyze
          uses: std.Message
          with: {msg: a}
          requires:
          - {std.check.Needs: {produces: {type: p.SimImg, profile: true}}}
    ''')
    proc = _dfm(d, "Analyze", "--needs", "img.opt")
    assert proc.returncode != 0
    assert not os.path.exists(os.path.join(d, "rundir", "BUILT-opt"))


def test_a_missing_input_is_reported(tmp_path):
    d = _write(tmp_path, TYPED)
    proc = _dfm(d, "Analyze")
    assert proc.returncode != 0
    assert "needs at least 1 input" in proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# std.check.Needs -- named and counts
# ---------------------------------------------------------------------------

def test_named_needs_are_checked(tmp_path):
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - {name: a, uses: std.Message, with: {msg: a}}
        - {name: b, uses: std.Message, with: {msg: b}}
        - root: t
          uses: std.Message
          needs: [a]
          with: {msg: t}
          requires:
          - {std.check.Needs: {named: [b]}}
    ''')
    msgs = _build(d, "p.t")
    assert any("must depend on 'b'" in m for m in msgs)


def test_a_max_is_checked(tmp_path):
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - {name: a, uses: std.Message, with: {msg: a}}
        - {name: b, uses: std.Message, with: {msg: b}}
        - root: t
          uses: std.Message
          needs: [a, b]
          with: {msg: t}
          requires:
          - {std.check.Needs: {max: 1}}
    ''')
    assert any("too many inputs" in m for m in _build(d, "p.t"))


# ---------------------------------------------------------------------------
# Severity and inheritance
# ---------------------------------------------------------------------------

def test_severity_warning_reports_without_failing(tmp_path):
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - root: t
          requires:
          - {std.check.Implemented: {severity: warning}}
    ''')
    proc = _dfm(d, "t")
    assert proc.returncode == 0, proc.stderr
    assert "not implemented" in proc.stdout + proc.stderr


def test_severity_off_disables_the_check(tmp_path):
    """The documented escape hatch: a project that cannot satisfy an inherited
    requirement restates it `off`, leaving an auditable record in the flow file
    -- strictly better than a silent pass or a flag that vanishes from history."""
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - name: base
          requires: [std.check.Implemented]
        - root: t
          uses: base
          requires:
          - {std.check.Implemented: {severity: "off"}}
    ''')
    assert _build(d, "p.t") == []


def test_requirements_accumulate_along_uses(tmp_path):
    """A leaf using a capability that uses an archetype is subject to all of
    them -- the union is what makes a base contract enforceable."""
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - {name: dep, uses: std.Message, with: {msg: d}}
        - name: archetype
          requires:
          - {std.check.Needs: {id: one, named: [dep]}}
        - name: capability
          uses: archetype
          requires:
          - {std.check.Needs: {id: two, min: 2}}
        - root: t
          uses: capability
          needs: [dep]
    ''')
    msgs = _build(d, "p.t")
    # The `dep` requirement is satisfied; the min-2 one from the middle layer
    # is not, and both were collected.
    assert any("at least 2 inputs" in m for m in msgs)
    assert not any("must depend on" in m for m in msgs)


def test_a_nearer_declaration_replaces_the_same_check(tmp_path):
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - {name: a, uses: std.Message, with: {msg: a}}
        - name: base
          requires:
          - {std.check.Needs: {min: 5}}
        - root: t
          uses: base
          needs: [a]
          requires:
          - {std.check.Needs: {min: 1}}
    ''')
    assert _build(d, "p.t") == []


# ---------------------------------------------------------------------------
# Load-time validation
# ---------------------------------------------------------------------------

def _errors(tmp_path, flow):
    msgs = []
    loadProjPkgDef(str(_write(tmp_path, flow)),
                   listener=lambda m: msgs.append(m.msg))
    return msgs


def test_an_unknown_check_type_is_a_load_error(tmp_path):
    msgs = _errors(tmp_path, '''\
    package:
        name: p
        tasks:
        - {root: t, requires: [std.check.NoSuch], uses: std.Message, with: {msg: x}}
    ''')
    assert any("does not exist" in m for m in msgs)


def test_a_non_check_type_is_a_load_error(tmp_path):
    """A requirement naming something that is not a check would never be
    evaluated -- silently, which is the failure mode to avoid."""
    msgs = _errors(tmp_path, '''\
    package:
        name: p
        tasks:
        - {root: t, requires: [std.Test], uses: std.Message, with: {msg: x}}
    ''')
    assert any("is not a check" in m for m in msgs)


# ---------------------------------------------------------------------------
# A fragment-declared type is reachable across packages
# ---------------------------------------------------------------------------

def test_a_fragment_declared_type_resolves_from_another_package(tmp_path):
    """`std.check.Implemented` lives in package `std` under the `check`
    fragment namespace. Resolution used to split a type name on its LAST dot,
    look for a package called `std.check`, and find nothing -- so any type
    declared in a fragment was unreachable from outside its own package."""
    loader, pkg = loadProjPkgDef(str(_write(tmp_path, UNFILLED)))
    assert loader.findType("std.check.Implemented") is not None
    assert loader.findType("std.check.Needs") is not None
    assert loader.findType("std.Check") is not None


def test_a_static_contract_does_not_replace_a_runtime_check(tmp_path):
    """The boundary, pinned deliberately.

    A task whose need declares the required type passes the static gate even
    though it emits nothing at runtime. That is correct: the gate is over
    declarations, and it is cheap and early precisely because it does not wait
    for data. A consumer that cares whether the data is really there checks
    that itself, when it has the data -- and this test exists so nobody
    "fixes" the static check into pretending otherwise.
    """
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: SimRun, uses: std.DataItem}
        tasks:
        - name: run
          shell: bash
          run: "true"          # declares a SimRun, emits nothing
          produces:
          - {type: p.SimRun}
        - root: AnalyzeProfile
          uses: std.Message
          with: {msg: analyzing}
          requires:
          - {std.check.Needs: {produces: {type: p.SimRun}}}
    ''')
    proc = _dfm(d, "AnalyzeProfile", "--needs", "run")
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# Matching semantics: is-a on `type`, and effective produces
# ---------------------------------------------------------------------------

def test_a_derived_item_type_satisfies_a_base_requirement(tmp_path):
    """`std.PubSet` derives from `std.FileSet`, so a consumer asking for a
    FileSet must accept a PubSet. Exact-string matching rejected it, and the
    rejection looked like a miswired flow rather than a matching bug -- the
    worst way to be wrong."""
    d = _write(tmp_path, '''\
    package:
        name: p
        tasks:
        - name: pubs
          uses: std.PubSet
          needs: [src]
          produces: [{type: std.PubSet, filetype: systemVerilogSource}]
        - name: src
          uses: std.FileSet
          with: {type: systemVerilogSource, base: ".", include: ["*.sv"]}
        - root: t
          uses: std.Message
          needs: [pubs]
          with: {msg: ok}
          requires: [{std.check.Needs: {produces: {type: std.FileSet}}}]
    ''')
    (tmp_path / "a.sv").write_text("")
    proc = _dfm(d, "t")
    assert proc.returncode == 0, proc.stdout + proc.stderr


PASSTHROUGH = '''\
package:
    name: p
    types:
    - {name: Marker, uses: std.DataItem}
    tasks:
    - name: producer
      uses: std.Message
      with: {msg: p}
      produces: [{type: p.Marker}]
    - {name: forwards, uses: std.Message, needs: [producer], passthrough: all, with: {msg: f}}
    - {name: absorbs,  uses: std.Message, needs: [producer], passthrough: none, with: {msg: a}}
    - root: via-forwarder
      uses: std.Message
      needs: [forwards]
      with: {msg: v}
      requires: [{std.check.Needs: {produces: {type: p.Marker}}}]
    - root: via-absorber
      uses: std.Message
      needs: [absorbs]
      with: {msg: v}
      requires: [{std.check.Needs: {produces: {type: p.Marker}}}]
'''


def test_an_item_reaches_a_consumer_through_a_passthrough_task(tmp_path):
    """Effective outputs are what a task DECLARES plus what it PASSES THROUGH.
    Declaring only what a task adds is what keeps declarations maintainable;
    following passthrough is what makes those partial declarations add up to
    the truth at the consumer."""
    d = _write(tmp_path, PASSTHROUGH)
    assert _dfm(d, "via-forwarder").returncode == 0


def test_a_task_that_does_not_forward_is_a_boundary(tmp_path):
    """The other half of the same rule, and the reason it is not just a
    transitive walk: what a non-forwarding task consumed does not reach ITS
    consumer, so a requirement must not be satisfied by an item the consumer
    can never see."""
    d = _write(tmp_path, PASSTHROUGH)
    proc = _dfm(d, "via-absorber")
    assert proc.returncode != 0
    assert "p.Marker" in proc.stdout + proc.stderr


def test_an_undeclared_task_is_a_sink_not_a_window(tmp_path):
    """The correctness fix behind the test above.

    `passthrough: unused` with an undeclared `consumes` (which defaults to
    *all*) forwards nothing -- the engine hands every input to the body and
    there is nothing left over. A checker that read `passthrough` alone walked
    straight through such a task and could satisfy a requirement from an item
    the consumer never receives.
    """
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: Marker, uses: std.DataItem}
        tasks:
        - name: producer
          uses: std.Message
          with: {msg: p}
          produces: [{type: p.Marker}]
        # Declares nothing: reads everything, forwards nothing.
        - {name: sink, uses: std.Message, needs: [producer], with: {msg: s}}
        - root: t
          uses: std.Message
          needs: [sink]
          with: {msg: t}
          requires: [{std.check.Needs: {produces: {type: p.Marker}}}]
    ''')
    proc = _dfm(d, "t")
    assert proc.returncode != 0
    assert "p.Marker" in proc.stdout + proc.stderr


def test_a_compound_forwards_what_its_interior_produced(tmp_path):
    """A compound is not governed by the leaf passthrough rules.

    Its output is assembled from its needs, which for a compound are its
    terminal interior tasks -- so what a consumer receives from a compound is
    what the task inside it produced. Applying leaf rules made every compound
    look like a sink, which is the shape most real image/library tasks have.
    """
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: Marker, uses: std.DataItem}
        tasks:
        - name: wrapper
          tasks:
          - name: inner
            uses: std.Message
            with: {msg: i}
            produces: [{type: p.Marker, kind: real}]
        - root: t
          uses: std.Message
          needs: [wrapper]
          with: {msg: t}
          requires: [{std.check.Needs: {produces: {type: p.Marker, kind: real}}}]
    ''')
    proc = _dfm(d, "t")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_compound_does_not_satisfy_an_unrelated_requirement(tmp_path):
    """The other half: forwarding is not a blank cheque."""
    d = _write(tmp_path, '''\
    package:
        name: p
        types:
        - {name: Marker, uses: std.DataItem}
        tasks:
        - name: wrapper
          tasks:
          - name: inner
            uses: std.Message
            with: {msg: i}
            produces: [{type: p.Marker, kind: real}]
        - root: t
          uses: std.Message
          needs: [wrapper]
          with: {msg: t}
          requires: [{std.check.Needs: {produces: {type: p.Marker, kind: other}}}]
    ''')
    proc = _dfm(d, "t")
    assert proc.returncode != 0
    assert "kind: other" in proc.stdout + proc.stderr
