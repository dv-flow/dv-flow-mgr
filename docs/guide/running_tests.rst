.. _running_tests:

#############
Running Tests
#############

A verification project needs one command that runs its tests, lets the user
choose *which* tests, and reports what happened. ``std.TestRunner`` is the
built-in base task that provides it.

A root ``uses:`` it and wires the available cases and suites as ``needs:``:

.. code-block:: yaml

    - root: tests
      uses: std.TestRunner
      needs: [smoke-suite, regression-suite, formal-cases]

That is the whole of the project-side wiring. The command, its arguments, the
selection behavior, and the end-of-run report all come from the base task.

.. code-block:: bash

    dfm run tests                       # everything
    dfm run tests --tests arb,err       # just those cases
    dfm run tests --tests sanity.       # everything in the `sanity` suite
    dfm run tests -t uart. -x break_det # a suite, minus one test
    dfm run tests --views rtl           # just that configuration
    dfm run tests --tests arb --views rtl
    dfm run tests --detail full         # report every case, not just failures

.. note::

   The same selection is also available as ``-D tests=arb,err``, which is what
   you need where a flag cannot reach -- for example inside a ``needs:``
   chain, or over the daemon protocol.

Selection prunes the graph
==========================

Selection happens **at graph build**, by removing needs before they are
resolved into nodes. A deselected test is not built and skipped -- it is never
built at all, and neither is anything reachable only through it.

That last part is the practical payoff. If three simulation images exist and
you select only cases that run on one of them, the other two images are never
compiled:

.. code-block:: bash

    dfm run tests --views tlm    # only the TLM image is built

This is why selection is not expressed with ``iff:``. A task disabled by
``iff:`` still becomes a (stub) node, and its upstream dependencies are still
built -- so gating the *test* would not save you the cost of building an image
that nothing selected needs.

Declaring what a test is
========================

The runner has to tell a test apart from an image, a flags item, or a helper.
Two ways, matching the two granularities a project actually has.

A single case carries a ``std.Test`` tag
----------------------------------------

.. code-block:: yaml

    - name: smoke
      uses: hdlsim.vlt.SimUVMCase
      tags: [ { std.Test: { case: smoke, view: rtl } } ]

``case`` is the short name the user types; ``view`` is the configuration it
runs on, when a project has more than one.

A suite is a matrix whose cells name their cases
-------------------------------------------------

.. code-block:: yaml

    - name: regression-suite
      strategy:
        matrix:
          view: [tlm, rtl]
          case:
          - { name: arb,    testname: my_arb_test }
          - { name: err,    testname: my_err_test }
      body:
      - name: "${{ this.view }}-${{ this.case.name }}"
        uses: hdlsim.vlt.SimUVMCase
        with:
          testname: "${{ this.case.testname }}"

``--tests arb`` narrows the ``case`` axis and ``--views rtl`` narrows the
``view`` axis, so only the surviving cells are generated. If a suite's cells
are all deselected, the suite itself is dropped.

The suite is named after its task. To give it a different name, tag it:
``tags: [ { std.TestSuite: { name: regression } } ]``.

The field names are configurable, because a project may already have its own:
``test_key`` (default ``name``) is the cell field holding the case name, and
``view_axis`` (default ``view``) is the axis holding the configuration.

Suites of suites
----------------

A task that ``uses: std.TestSuite`` is a suite whose members are its
``needs:`` -- tests, matrix suites, or other suites. A suite that contains
suites is a super-suite; nothing else distinguishes it.

.. code-block:: yaml

    - name: sanity
      uses: std.TestSuite
      needs: [reset, csr-rw]

    - name: regress
      uses: std.TestSuite
      needs: [sanity, regression-suite, long-soak]

    - root: tests
      uses: std.TestRunner
      needs: [regress, formal-cases]

Membership is by reference. A suite reached through two parents is one suite,
and its tests run once.

**Anything the runner does not recognize as a test is always kept.** Selecting
tests must never break the build, so an image or a helper wired into ``tests``
is untouched by a selection.

Test paths and patterns
=======================

A test's **path** is its position in the suite tree, relative to the runner:
``regress.sanity.reset``, ``regress.regression-suite.arb``. The runner's own
name is not part of it. Run ``dfm run tests-info --format list`` to see every
path.

``--tests`` takes patterns over those paths:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Pattern
     - Selects
   * - ``reset``
     - any test **or suite** named ``reset``, anywhere in the tree. Selecting
       a suite selects everything under it.
   * - ``sanity.reset``
     - that trailing path, anywhere in the tree
   * - ``sanity.``
     - everything under a suite named ``sanity`` (a trailing ``.`` means
       suites only)
   * - ``.regress.sanity``
     - a leading ``.`` anchors the pattern at the runner
   * - ``uart.fifo_*``
     - ``*``, ``?`` and ``[...]`` glob within one name
   * - ``regress.**.reset``
     - ``**`` spans any number of names

Patterns are globs, not substrings: ``arb`` does not select ``arb_eq``.
Several patterns (comma-separated or repeated) select the union.

``--exclude`` (``-x``) takes the same patterns and is applied **last**, so an
exclude always wins over a selection. The order is fixed: ``--tests`` selects,
``--views`` filters, ``--exclude`` removes.

Selection prunes at every level. A deselected test deep inside a super-suite is
never built, and a suite left with nothing selected is dropped.

Selection is strict
===================

Every way this feature can go wrong ends in the same place: a **green run that
tested less than you asked for**. So the failure modes are errors, not
warnings:

.. code-block:: text

    $ dfm run tests --tests arbb
    Error: no test matches 'arbb'. Available: suite.arb, suite.arb_eq, suite.err, ...

Each pattern must match something on its own, so one typo in a list cannot
silently shrink the run. An ``--exclude`` that matches nothing only warns,
since excluding too little never tests less than you asked for.

A selection that matches nothing is likewise an error, as is a run whose suite
produced no results at all -- zero failures out of zero tests would otherwise
satisfy every other check and report success.

Where a matrix axis is written as an expression (``view: "${{ views }}"``) the
runner resolves it so its values can still be validated. If it genuinely cannot
be resolved, validation stays quiet: rejecting a working flow is worse than
missing a typo.

Listing what a runner offers
============================

``std.TestInfo`` reports what a runner would run, and builds nothing:

.. code-block:: yaml

    - root: tests-info
      uses: std.TestInfo
      with: { target: tests }

It accepts the runner's selection flags (``--tests``, ``--views``,
``--exclude``) and resolves them with the same code. So
``tests-info --tests sanity.`` lists exactly what ``tests --tests sanity.``
would run, and rejects exactly what it would reject.

.. code-block:: bash

    dfm run tests-info                           # the inventory panel
    dfm run tests-info --tests sanity. --json    # as JSON
    dfm run tests-info --format yaml
    dfm run tests-info -t regress. --format list # one test path per line

``--format list`` prints one ``--tests`` selector per line, anchored with a
leading ``.`` so each selects exactly one test (``x.reset`` alone would also
select ``y.x.reset``).

``--instances`` lists **runs** instead of tests: one entry per test per view,
each with an ``id`` and the exact ``argv`` that runs it alone. This is the
work list for a runner that issues one ``dfm`` command per run:

.. code-block:: json

    { "id": "regress.uart.fifo_full[view=rtl]",
      "test": "regress.uart.fifo_full", "view": "rtl",
      "argv": ["run", "p.tests", "--tests", ".regress.uart.fifo_full",
               "--views", "rtl"] }

``argv`` carries only the selection. Put run options (``--clean``, ``-c``)
after ``run``, and pass ``-D`` and project flags the same way you passed them
to ``tests-info``. With ``--format list``, each line is one run's selection
arguments. Every machine-readable inventory carries ``"schema": 1``.

In a machine format (``json``, ``yaml``, ``list``) the payload is the only
thing written to stdout; progress goes to stderr, so
``dfm run tests-info --json | jq`` works.

Building once, running each test separately
-------------------------------------------

``--requires PATTERN`` adds the **build fan-in** of the selection: which
producers of some data the selected runs depend on. ``PATTERN`` is a produce
pattern, matched the way ``consumes:`` matches: ``std.FileSet:filetype=simDir``,
or just ``filetype=simDir``. It implies ``--instances``.

.. code-block:: bash

    dfm run tests-info --json --requires filetype=simDir -t sanity.

Each run gets ``requires``, the producers its data comes from. ``producers``
lists each producer once, with its rundir relative to the session rundir
(``null`` when that cannot be known) and the runs that need it. ``build.argv``
is the command that builds them all:

.. code-block:: json

    "instances": [
      { "id": "sanity.uart.fifo_full[view=rtl]", "argv": ["..."],
        "requires": ["p.img-rtl"] } ],
    "producers": [
      { "node": "p.img-rtl", "rundir": "p.img-rtl",
        "needed_by": ["sanity.uart.fifo_full[view=rtl]"] } ],
    "build": { "argv": ["run", "p.tests", "--tests", "sanity.",
                        "--build-only", "filetype=simDir"] }

That gives a three-step regression:

1. List the runs and their producers with ``tests-info --requires``.
2. Run ``build.argv`` once, in a shared rundir. ``--build-only PATTERN`` on the
   runner builds exactly those producers and runs no test.
3. Run each instance's ``argv`` in its own rundir, with
   ``--base-rundir <shared rundir>`` after ``run`` (see
   :doc:`incremental`). The builds are found where a normal run would have put
   them, so nothing is rebuilt.

The walk follows dataflow, not just dependencies. It stops at the nearest
matching producer on each path, so an image's own upstream is not reported, and
it does not pass a task that consumes what it receives. Which producer a run
uses is often decided at graph build (``needs: [img-${{ this.view }}]``), so
``--requires`` builds the runner's graph; nothing executes. Producers are found
from ``produces:`` declarations, so one that does not declare its output is
missed. A run with no producer is warned about, and so is a pattern that no
selected run depends on.

The report
==========

``std.TestRunner`` declares a ``summary:``, so the run ends with a test report
rather than the generic task panel:

.. code-block:: text

    ╭──────────── Tests (13/14 passed, 1 failed) ────────────╮
    │ fail  rtl-err   2                                      │
    ╰────────────────────────────────────────────────────────╯

``--detail`` controls how much is shown:

``quiet``
    the headline only

``normal`` (default)
    the headline plus failing cases

``full``
    every case, after the generic task summary

The report is structural, not tied to any one producer: any item exposing
``passed``/``status`` is read as a case verdict and any item exposing
``total``/``passed`` counts as a roll-up. A simulator, a formal engine, and a
lint task can all feed the same report.

Since the report is the invoked root's ``summary:``, it renders for the single
root ``dfm run tests`` invokes. Entry points that can supply several roots at
once fall back to the builtin task summary, because there is no single
declaration to honor.

Gating CI
=========

The root's task status is the gate. What makes that possible is that a failing
test is *data*, not an exception: a case that fails still returns success as a
task, carrying its verdict as an output item, so one failure never aborts the
rest of the suite. The report task then decides the run's exit code from the
collected verdicts.

A producer package supplies the roll-up. With ``hdlsim``:

.. code-block:: yaml

    - root: tests
      uses: hdlsim.SimSuiteReport    # which itself uses std.TestRunner
      needs: [regression-suite]

``hdlsim.SimSuiteReport`` also writes ``junit.xml`` into its rundir (disable
with ``junit: false``), which is what gives GitHub and GitLab a native test
view.
