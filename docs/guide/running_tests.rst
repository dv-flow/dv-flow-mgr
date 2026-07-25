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

The field names are configurable, because a project may already have its own:
``test_key`` (default ``name``) is the cell field holding the case name, and
``view_axis`` (default ``view``) is the axis holding the configuration.

**Anything the runner does not recognize as a test is always kept.** Selecting
tests must never break the build, so an image or a helper wired into ``tests``
is untouched by a selection.

Selection is strict
===================

Every way this feature can go wrong ends in the same place: a **green run that
tested less than you asked for**. So the failure modes are errors, not
warnings:

.. code-block:: text

    $ dfm run tests --tests arbb
    Error: no test matches 'arbb'. Available: arb, arb_eq, err, hol, hw_hs, sw_copy

A selection that matches nothing is likewise an error, as is a run whose suite
produced no results at all -- zero failures out of zero tests would otherwise
satisfy every other check and report success.

Where a matrix axis is written as an expression (``view: "${{ views }}"``) the
runner resolves it so its values can still be validated. If it genuinely cannot
be resolved, validation stays quiet: rejecting a working flow is worse than
missing a typo.

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
