###########
Run Results
###########

Every ``dfm run`` writes a **run record**: one tree of ``std.Result`` nodes
that says whether the run succeeded, what went wrong and why, and where the
evidence is. The format is the same for every domain -- a test regression, a
synthesis run, a formal proof, a firmware build -- so the console summary,
``dfm show results``, CI renderers, editors and agents all read one thing.

This page is the format reference. For using it day to day, see
:ref:`run-results` in :doc:`/guide/running`.

Where the record goes
=====================

.. code-block:: text

    rundir/out/<run-id>/
      results.json       # the record: {schema, run, summary, result}
      summary.md         # the same data, as markdown
      results/           # the same data, as a link tree (FAILED/, STATUS, log ...)
      logs/              # copies of the logs, with results.copy_logs
    rundir/out/latest -> <run-id>

``<run-id>`` is a local timestamp, ``YYYYMMDD-HHMMSS``, with ``-2``, ``-3`` ...
appended when two runs start in the same second. ``dfm run`` creates the
directory before the first task runs, so ``$DFM_OUT_DIR`` always exists, and
``std.Publish`` outputs land in the same directory. ``--run-id ID`` pins the id
(a CI build number, say); ``--no-results`` turns the record off.

The JSON Schema is ``src/dv_flow/mgr/share/dvflow-results.schema.json``
(``$id`` ``https://dv-flow.github.io/dvflow-results.schema.json``); print it
with ``dfm util schema --results``. It is generated from the pydantic models
in ``dv_flow.mgr.results.model``, and a unit test keeps the checked-in copy
current.

The file
========

.. code-block:: text

    {
      "schema": "dvflow-results/1",
      "run": {"id": "20261031-142210", "root": "wb-dma-example.tests",
              "argv": ["dfm", "run", "tests"], "cwd": "...", "rundir": "...",
              "start_time": "...", "end_time": "...", "exit_status": 1,
              "host": "...", "dfm_version": "..."},
      "summary": { "status": "error", "msg": "...", "counts": {...},
                   "metrics": {...}, "failures": [...] },
      "result":  { "name": "tests", "type": "std.TestRunResult", "...": "..." }
    }

``run``
    What was run, where and when. ``exit_status`` is the run's exit status
    (``runner.status``); writing the record never changes it.

``summary``
    The part an agent or a CI step reads. It is redundant by design and computed
    the same way for every domain -- see `The summary`_.

``result``
    The full tree, for renderers.

Nodes
=====

Each node is a ``std.Result`` (or a subtype). In ``results.json`` a node has:

.. list-table::
   :header-rows: 1
   :widths: 18 82

   * - Field
     - Meaning
   * - ``name``
     - Display name, unique among siblings.
   * - ``type``, ``types``
     - The node's type and its is-a lineage, most derived first, ending at
       ``std.Result``: ``["hdlsim.TestResult", "std.TestResult", "std.Result"]``.
       A renderer that doesn't know the first entry falls back along the list.
   * - ``status``
     - The verdict: ``pass``, ``fail``, ``error``, ``timeout``, ``skip``,
       ``notrun`` (see `Status`_).
   * - ``passed``
     - ``status == "pass"``. Derived; kept for older readers.
   * - ``msg``
     - The headline: ``"UVM_ERROR x2: ch1 dst mismatch"``,
       ``"timing not met: WNS -0.12 ns"``.
   * - ``task``, ``rundir``
     - The producing task (fully qualified) and its run directory.
   * - ``tool``
     - ``{name, version}`` of the tool that produced the verdict.
   * - ``attrs``
     - Identity and configuration that is not a quantity: ``testname``,
       ``seed``, ``top``, ``part``, ``strategy`` ...
   * - ``metrics``
     - ``name -> {value, unit, better, label}``. ``better`` is ``higher``,
       ``lower`` or ``none``: the direction a run-to-run compare treats as an
       improvement.
   * - ``checks``
     - Named success criteria, ``{name, status, metric, op, goal, value, msg}``:
       ``timing: wns_ns >= 0``, ``uvm_errors == 0``. ``value`` is the observed
       metric value.
   * - ``counts``
     - True totals. Diagnostics by severity (``errors``, ``warnings``,
       ``fatals``, ``infos``), and for a node with children, leaf statuses
       (``total``, ``pass``, ``fail``, ``error``, ``timeout``, ``skip``,
       ``notrun``).
   * - ``diagnostics``
     - The first N messages (10), most severe first. Each is
       ``{severity, msg, category, loc, src_loc, time, hier}``: ``loc`` is where
       to look (usually the log, with a line), ``src_loc`` the source line the
       message is about.
   * - ``artifacts``
     - FileSets with a role (see `Artifacts`_).
   * - ``children``
     - Nested Results: the cases of a suite, the stages of a synthesis run.
   * - ``start_time``, ``end_time``
     - ISO 8601.
   * - ``reused``
     - ``true`` when the producing task was up to date or a cache hit: the
       artifacts come from an earlier run.

A node keeps any other field its producer set (``testname``, ``seed``, hdlsim's
``errors``/``sim_errors`` ...). Empty containers and ``reused: false`` are left
out of the file.

Status
------

``status`` is the verdict, and ``checks`` explain it.

``pass``
    The work ran and every check passed.
``fail``
    The work ran and a check failed. This is a *verdict*: a task that reports a
    failing verdict still exits with status 0. Failure is data.
``error``
    No clean verdict: a crash, a tool error, a non-zero exit with a clean log, a
    flow failure.
``timeout``
    The work didn't finish in time.
``skip``
    Deliberately not run.
``notrun``
    Selected but not run, because something it depends on failed. Its ``msg``
    names the blocker: ``blocked: wb-dma-example.fw-build failed``.

When statuses combine (a parent over its children, a node over its checks), the
worst wins: error > timeout > fail > notrun > skip > pass.

Types
=====

The std library defines the core and the test profile. Other domains add thin
subtypes in their own libraries (``FormalResult`` in libformal, a synthesis
library's ``SynthResult``).

``std.Result``
    The domain-neutral node (fields above). ``uses: std.DataItem``.
``std.TaskResult``
    What dfm makes for a task that produced no Result (see `How dfm builds the
    record`_).
``std.TestResult``
    One test case. Adds ``testname`` and ``seed``.
``std.SuiteResult``
    A suite; children are TestResult and SuiteResult nodes. Adds ``total``,
    ``failed``, ``errored``. ``passed`` is a bool like every Result; the pass
    count is ``counts.pass``.
``std.TestRunResult``
    The root of a test run. ``uses: std.SuiteResult``.
``std.Diagnostic``, ``std.Metric``, ``std.ResultCheck``
    The shapes of a diagnostic, a metric and a check. They travel as maps
    inside a Result; the types document them. (The check type is
    ``ResultCheck`` because ``std.Check`` is the graph-build requirement type.)

Artifacts
=========

Artifacts are ordinary ``std.FileSet`` items with a ``role=<role>`` attribute,
so consumers that filter on ``filetype`` keep working. ``filetype`` stays
tool-specific; ``role`` is the vocabulary renderers understand. A
``label=<text>`` attribute gives a display name ("Timing (setup)").

.. list-table::
   :header-rows: 1
   :widths: 14 56 30

   * - role
     - meaning
     - renderer action
   * - ``log``
     - primary log, which ``diagnostics[].loc`` points into
     - open at line
   * - ``report``
     - human-readable report: timing, utilization, power, html summary
     - open
   * - ``waves``
     - waveform (fst, vcd, fsdb) or a formal counterexample trace
     - open in a wave viewer
   * - ``cov``
     - coverage DB; ``format=`` says which
     - open / merge
   * - ``netlist``
     - synthesized netlist
     - open
   * - ``checkpoint``
     - tool database to reopen in the tool's GUI
     - "open in tool"
   * - ``image``
     - built binary: bitstream, firmware elf/hex, sim image
     - reveal
   * - ``data``
     - machine data already folded into ``metrics``
     - none
   * - ``profile``
     - profiler output
     - open
   * - ``other``
     - anything else worth surfacing
     - open

The older hdlsim names are accepted: ``trace`` reads as ``waves`` and
``stats`` as ``data``. In ``results.json`` each artifact also carries ``role``,
``label`` and ``stamps``: ``[{path, mtime, size}]`` for each file when the run
ended. A reader compares them with the file now (task rundirs are reused, so a
later run may have overwritten the waves) and shows a changed file as ``stale``
and a deleted one as ``missing``; ``dfm show results --json`` adds ``state`` to
each stamp and ``stale`` to each artifact. The record itself is never
rewritten.

How dfm builds the record
=========================

At the end of the run:

1. **The root Result.** dfm takes the root task's output and keeps the items
   that are ``std.Result`` (by is-a). One item is the root; several are wrapped
   in a ``std.Result`` named after the task. If there are none, dfm
   **synthesizes** a ``std.TaskResult``: ``pass`` if the task succeeded,
   ``error`` (with the first error marker as ``msg``) if it failed, ``notrun``
   (naming the blocker) if it was skipped; its markers become diagnostics; its
   own output FileSets become artifacts, with a role guessed from the filetype
   when they don't carry one; and its log becomes the ``log`` artifact.
2. **Unaccounted failures.** Every task in the root's subgraph that failed
   (non-zero status, not merely skipped) is checked against the tree. A failure
   is *accounted for* when some node names that task, or a compound that
   contains it, in ``task``, or has a ``rundir`` inside the failed task's. The
   rest -- a compile error, a failed code generator, a lab ``todo`` gate --
   become ``std.TaskResult`` children of a ``_tasks`` node under the root. A
   compound that failed only because a task inside it failed is reported
   through that task. If any are attached, the root is raised to ``error``
   (keeping its own verdict in ``own_status``), so the record agrees with the
   run's exit status.
3. **Stamps.** Each artifact file's mtime and size is recorded; nodes from
   up-to-date or cache-hit tasks are marked ``reused``.
4. **Write.** ``results.json`` (atomically), then ``summary.md``, then
   ``out/latest``. A failure anywhere here is a warning; it never changes the
   run's exit status.

The summary
===========

``summary`` is computed from the tree:

* ``status``, ``msg`` and ``metrics`` are the root's, plus ``walltime_s`` for
  the whole run. When the root has no ``msg``, it is a count line
  (``all 6 passed``, ``1 of 6 failed, 1 not run``).
* ``counts`` tallies the statuses of the **leaf** nodes. A root that gained
  ``_tasks`` still counts as itself, and each attached task counts as a leaf.
* ``failures`` lists every non-passing leaf, every non-passing
  ``std.TaskResult``, and every non-passing parent that no non-passing child
  explains (a synthesis run whose timing check failed while its stages all
  passed). Each entry has the node's ``path`` from the root (by name), its
  ``status``, ``msg``, ``type`` and ``task``, its failing ``checks``, the
  first ``log`` with the line of the first diagnostic that points into it, and
  the first ``waves``.

So a single-node run -- a synthesis run with no stages -- has
``counts.total == 1``, and ``failures`` holds the root itself with its failed
check. A reader needs no special case.

Examples
========

A failing UVM test (``tests/unit/data/results/test-suite-fail.json``), as
``dfm show results`` prints it:

.. code-block:: text

    tests  FAIL  1 of 2 failed
    └─ uvm-tests  FAIL
       ├─ smoke  pass  (uvm_errors=0  walltime_s=12.5 s)
       └─ two-ch  FAIL  UVM_ERROR x2: ch1 dst mismatch @ 0x40  (uvm_errors=2  walltime_s=12.5 s)
             check uvm_errors: fail (uvm_errors=2, want == 0)
             error: UVM_ERROR ch1 dst mismatch @ 0x40 (line 1873)
             log: /abs/rundir/wb-dma-example.two-ch/sim.log:1873
             waves: /abs/rundir/wb-dma-example.two-ch/waves.fst

and its summary failure entry:

.. code-block:: json

    {"path": "tests/uvm-tests/two-ch", "status": "fail",
     "msg": "UVM_ERROR x2: ch1 dst mismatch @ 0x40",
     "type": "hdlsim.TestResult", "task": "wb-dma-example.two-ch",
     "checks": [{"name": "uvm_errors", "status": "fail", "metric": "uvm_errors",
                 "op": "==", "goal": 0, "value": 2.0}],
     "log": {"path": "/abs/rundir/wb-dma-example.two-ch/sim.log", "line": 1873},
     "waves": "/abs/rundir/wb-dma-example.two-ch/waves.fst"}

A synthesis run that missed timing (``synth-timing-fail.json``). The tool
exited 0; the failing check makes the run fail:

.. code-block:: json

    {"name": "synth", "type": "yosys.SynthResult",
     "types": ["yosys.SynthResult", "std.Result"], "status": "fail",
     "msg": "timing not met: WNS -0.12 ns on clk_sys (target 100 MHz)",
     "attrs": {"top": "soc_top", "part": "ice40-up5k"},
     "metrics": {"fmax_mhz": {"value": 98.8, "unit": "MHz", "better": "higher"},
                 "wns_ns":   {"value": -0.12, "unit": "ns", "better": "higher"},
                 "luts":     {"value": 4211, "unit": "cells", "better": "lower"}},
     "checks": [{"name": "timing", "status": "fail", "metric": "wns_ns",
                 "op": ">=", "goal": 0, "value": -0.12},
                {"name": "area", "status": "pass", "metric": "luts",
                 "op": "<=", "goal": 5280, "value": 4211}],
     "children": [{"name": "synth", "...": "..."}, {"name": "pnr", "...": "..."}]}

A build failure (``build-failure.json``): the firmware didn't compile, so two SoC
tests never ran. The compile error is in the record, not only in the console
scroll:

.. code-block:: text

    tests  ERROR  1 of 4 errored, 2 not run
    ├─ uvm-tests  pass  [1 passed]
    ├─ soc-tests  NOTRUN
    │  ├─ soc-dma-copy  NOTRUN  blocked: wb-dma-example.fw-build failed
    │  └─ soc-dma-copy-two  NOTRUN  blocked: wb-dma-example.fw-build failed
    └─ _tasks  ERROR  1 task(s) failed outside any result
       └─ fw-build  ERROR  dma.c:41: error: 'DMA_CSR' undeclared
             log: /abs/rundir/wb-dma-example.fw-build/wb-dma-example.fw-build.log

The fixtures in ``tests/unit/data/results/`` (a passing and a failing test
suite, a build failure, a synthesis timing failure, a formal counterexample and
a mixed root) are the format's contract: the schema test validates each one,
and checks that its ``summary`` is what dfm computes from its tree.

Roll-up
=======

A parent over its children (``std.ResultCollect``, ``std.TestSuite``,
``std.TestRunner``, ``dv_flow.mgr.results.rollup``):

* **status** is the worst child status; with no children it is ``notrun``
  ("no results").
* **counts** tally the leaf statuses.
* **metrics** roll up per name by a rule: ``sum``, ``max``, ``min``,
  ``mean`` or ``none``. The rule comes from the std metric registry
  (``src/dv_flow/mgr/std/result_metrics.yaml``), which also gives each common
  name its unit, direction and label -- ``walltime_s`` (s, lower, sum),
  ``maxrss_mb`` (MB, lower, max), ``cov_*_pct`` (%, higher, max), ``fmax_mhz``
  (MHz, higher, min), ``wns_ns``, ``luts``, ``cells``, ``area_um2``,
  ``power_mw``, ``depth``, ``proven`` and more. A name the registry doesn't
  know rolls up by its ``better``: ``lower`` sums (times and counts),
  ``higher`` takes the minimum (the conservative choice), ``none`` is not
  rolled up. ``api.metric(value, name="walltime_s")`` fills in the unit and
  direction from the registry.

``std.ResultCollect`` takes ``name``, ``type`` (default ``std.Result``) and
``checks`` (``[{name, metric, op, goal}]``, where ``metric`` may also be a leaf
count such as ``fail`` or ``total``). It outputs only its node; other inputs
are not passed through. ``std.TestSuite`` and ``std.TestRunner`` emit a
``std.SuiteResult`` / ``std.TestRunResult`` over the Results among their
inputs, and still pass everything through.

Renderings
==========

========  ==========================================================
format    what
========  ==========================================================
text      ``dfm show results``: the tree, passing subtrees collapsed
md        ``summary.md``, written with every record
junit     JUnit XML (``junit.xml``)
ctrf      CTRF JSON (``ctrf.json``, spec version 0.0.0)
========  ==========================================================

``junit`` and ``ctrf`` are written next to ``results.json`` when
``results.formats`` asks for them (or ``--results-format``), and ``dfm show
results --format FMT [-o FILE]`` renders any record. Both map the tree the
same way:

* a ``std.TestResult`` node is a test case; its scalar ``attrs`` and metric
  values are JUnit ``<properties>`` (with units: ``simtime=608us``) and CTRF
  ``extra``;
* a ``std.SuiteResult`` groups the cases under it (one JUnit ``testsuite``
  per suite, named by its path);
* any other node with checks is a suite with **one test case per check** --
  a synthesis run's ``timing`` check fails in CI next to the test failures --
  and its children are not repeated;
* any other leaf is a suite with one case; other parents (``_tasks``, a
  ``std.ResultCollect`` group) are walked through.

``fail`` is a JUnit ``<failure>`` whose message is the headline and whose text
is the failing checks; ``error`` and ``timeout`` are ``<error>``; ``skip`` and
``notrun`` are ``<skipped>``, with ``notrun``'s message naming the blocker. In
CTRF they are ``passed``/``failed``/``skipped``, with the node's own status in
``rawStatus``.

Configuration
=============

The ``results:`` section of the dfm config (installation, site, then the
project's ``.dfm/config.yaml``; later wins):

.. code-block:: yaml

    results:
      keep_previous: 1    # earlier runs kept besides this one; 0 = only this
                          # run, all = never prune
      copy_logs: false    # copy role=log artifacts into out/<run-id>/logs/
      tree: true          # build the out/<run-id>/results/ link tree
      formats: []         # renderings next to results.json: junit, ctrf
      strict_roots: false # a root without a Result in produces: is an error

``DFM_RESULTS_FORMATS`` and ``dfm run --results-format`` override
``formats`` for one run.

Producing a Result
==================

A task produces a Result by returning one in its output, built with
``dv_flow.mgr.results.api``:

.. code-block:: python

    from dv_flow.mgr import TaskDataResult
    from dv_flow.mgr.results import api as R

    async def Lint(ctxt, input):
        n = run_lint_and_count_warnings(ctxt)
        res = R.mk_result(ctxt, name="lint", metrics={"warnings": R.metric(n)})
        res.checks.append(R.eval_check(res.metrics, "clean", "warnings", "<=", 0))
        res.artifacts.append(R.artifact(ctxt, "lint.log", role="log"))
        R.finish(res)                        # status from the checks
        return TaskDataResult(output=[res])  # status 0: failure is data

``mk_result(ctxt, type, name, **fields)``
    A Result data item of ``type`` (any ``std.Result`` subtype), with ``task``
    and ``rundir`` set from the calling task.
``metric(value, unit, better, label)``
    A Metric map.
``check(name, status, ...)`` / ``eval_check(metrics, name, metric, op, goal)``
    A check with a status you decide, or one computed as ``metrics[metric] op
    goal`` (``>=``, ``<=``, ``==``, ``!=``, ``>``, ``<``). A metric that was not
    reported gives ``error``.
``artifact(ctxt, path, role, filetype, label)``
    A one-file FileSet with ``role=``/``label=`` attributes.
``diagnostic_from_marker(marker)``
    A ``TaskMarker`` as a Diagnostic.
``finish(result)``
    The status is the worst of the status you set (``pass`` if none), the
    non-skipped checks and the children; then ``passed``, ``counts`` and, for a
    failing node with no ``msg``, a headline naming the first failing check.
