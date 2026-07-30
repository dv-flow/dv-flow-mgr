##################
Artifact Variants
##################

Useful artifacts are often a **cross product**. In a verification project there
is one simulation image per testbench top, and for each of those one image per
build variant -- optimized, debug, coverage, profiling. Three tops and four
variants is twelve images that differ in predictable, parameterized ways.

That is what a cross product is for, but a cross product can mean two different
things, and DV Flow spells them differently:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Strategy
     - Meaning
   * - ``matrix:``
     - **Fan out.** Running the task runs every cell. A regression suite *is*
       all of its cases, so a suite is a matrix.
   * - ``select:``
     - **A catalog.** Each cell is a separately named artifact, built only when
       something asks for it. Twelve images are not one thing.

Choosing wrong is the likeliest mistake here, and the test is simple: *if
running the task should run everything in it, use* ``matrix:``. If asking for
one thing must not build the others, use ``select:``.

The rest of this chapter is about ``select:``.

A Family of Variants
====================

.. code-block:: YAML

    - root: sim-img
      desc: Simulation images
      with:
        view:  {type: str, value: tlm, cli: true, values: [tlm, wb, rtl]}
        build: {type: str, value: opt, cli: true, values: [opt, dbg, cov, prof]}
      strategy:
        select:
          axes:
            view:  [tlm, wb, rtl]
            build: [opt, dbg, cov, prof]
          default: {view: "${{ view }}", build: "${{ build }}"}
        body:
        - uses: hdlsim.vlt.SimImage
          needs:
          - env-lib
          - "flags-comp-${{ this.build }}"
          with:
            top: "${{ views[this.view].top }}"

This declares twelve **cells**, each a first-class task:

.. code-block:: text

    my-proj.sim-img.tlm.opt   my-proj.sim-img.tlm.dbg   ...
    my-proj.sim-img.wb.opt    ...
    my-proj.sim-img.rtl.opt   ...

Cells are ordinary tasks, which is the whole point. They can be depended on,
run, shown, and completed with no special handling:

.. code-block:: YAML

    needs: [sim-img.rtl.cov]

.. code-block:: bash

    dfm run sim-img.rtl.cov
    dfm show task my-proj.sim-img.rtl.cov

The body is written once. ``${{ this.<axis> }}`` is bound per cell, in
parameters and in ``needs:`` alike -- so ``needs: ["flags-comp-${{ this.build }}"]``
picks up a different flag-holder task in each cell without a hand-written task
per variant.

Only What Is Asked For
======================

A cell that nothing addresses is **never built** -- not built-and-skipped. Since
a deselected cell is never generated, nothing reachable only through it is
generated either.

.. code-block:: bash

    dfm run sim-img.rtl.cov      # compiles one image; the other eleven do not exist

And a cell that two things address is built **once**. Both properties come from
the same fact: a cell has a stable name, so it is memoized like any other task.
A regression running six cases over three views compiles three images, not six.

Naming a Cell
=============

By default a cell's key is its axis values joined with ``.``, in declaration
order -- ``sim-img.rtl.cov``. Use ``key:`` when that reads badly:

.. code-block:: YAML

    select:
      axes:
        view:  [tlm, rtl]
        build: [opt, cov]
      key: "${{ this.build }}-${{ this.view }}"     # -> sim-img.cov-rtl

What the Family Name Means
==========================

A family is never a unit of work; the cells are. What the bare family name
denotes is **declared**:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - ``default:``
     - Meaning
   * - a binding map *(default)*
     - The family is an **alias** for one cell. ``needs: [sim-img]`` and
       ``needs: [sim-img.tlm.opt]`` reach the same build.
   * - ``all``
     - A **gate** over every cell.
   * - ``none``
     - Only cells are addressable. Naming the family is an error that lists the
       cells -- appropriate when "the" image is meaningless.

Omitting ``default:`` means the first value of each axis. A binding may name
several values (``{build: [opt, cov]}``), which gates that sub-family.

Selecting From the Command Line
===============================

The ``default:`` binding is an expression over the family's **own parameters**,
which is what connects a project-wide knob to which artifact gets built:

.. code-block:: YAML

    package:
      name: my-proj
      with:
        build: {type: str, value: opt}      # the project-wide control

      tasks:
      - root: sim-img
        with:
          # the task-level variable, defaulting from the package variable
          build: {type: str, value: "${{ build }}", cli: true,
                  values: [opt, dbg, cov, prof]}
        strategy:
          select:
            axes: {build: [opt, dbg, cov, prof]}
            default: {build: "${{ build }}"}
          ...

.. code-block:: bash

    dfm run sim-img                  # the default -- opt
    dfm run sim-img --build prof     # this invocation
    dfm run tests -D build=cov       # the whole project, every family at once
    dfm run sim-img.prof             # by name

Precedence runs low to high:

.. code-block:: text

    declared default  <  -P  <  -D  <  --flag  <  an explicit cell name

See :doc:`parameters` for how ``cli: true`` exposes a parameter as a flag.

Partial Keys
------------

``sim-img.prof`` names only the ``build`` axis; the rest come from the family's
default, which ``-D`` and ``--flag`` can move.

**This works on the command line only.** A ``needs:`` must name a cell in full,
and a partial key there is a load error listing the cells it could have meant.
The reason is that a partial key is not stable: it denotes different cells as
defaults move. That is fine for something you type and wrong for something a
build file declares.

A partial key that could bind two axes, or the same axis twice, is an error
rather than a guess.

Finding Out What Exists
=======================

Cells are runnable tasks, so a 3x4 family would be twelve lines in every task
listing. The listing therefore shows the **family**, with its axes standing in
for the cells:

.. code-block:: text

    $ dfm run
    No task specified. Available Tasks:
    my-proj.sim-img  - Simulation images [view: tlm,wb,rtl x build: opt,dbg,cov,prof]
    my-proj.tests    - Run the regression

``dfm show task`` is where the cells themselves live:

.. code-block:: text

    $ dfm show task my-proj.sim-img
    Variant axes:
      - view: tlm, wb, rtl
      - build: opt, dbg, cov, prof

    Cells (default: view=tlm, build=opt):
      - my-proj.sim-img.tlm.opt
      ...

and asking about a cell tells you which family it belongs to and what it is
bound to:

.. code-block:: text

    $ dfm show task my-proj.sim-img.rtl.cov
    Variant of my-proj.sim-img:
      - view = rtl
      - build = cov

Both views are available as ``--json``, and tab completion offers cell names
without any extra wiring -- a cell is an ordinary entry in the task namespace.

Constraint: a Family's Shape Is Fixed at Load
=============================================

Cells are declared tasks, so they must exist before anything can reference one.
An axis is therefore resolved when the flow loads: it is a literal list, or an
expression over **package variables**.

.. code-block:: YAML

    package:
      with:
        builds: {type: list, value: [opt, dbg, cov, prof]}
      tasks:
      - name: sim-img
        strategy:
          select:
            axes: {build: "${{ builds }}"}       # fine -- and -D can change it

An axis may **not** depend on a ``set:``/``let`` rebind, which exists only
inside a subtree at graph build. A family whose shape varied by instantiation
site could not have stable cell names. An axis that cannot be resolved at load
is reported there, naming the axis.

This is the one way ``select:`` axes are more restricted than ``matrix:`` axes,
which are expanded at graph build.

Variants and Configurations
===========================

A :doc:`configuration <configurations>` is a global switch: it swaps task
overrides for the whole run. That makes it the wrong tool for a per-artifact
build variant, because two artifacts cannot then differ -- there is no way to
say "the RTL image in debug, the TLM image optimized" in one run.

As an axis, that is just two cells:

.. code-block:: bash

    dfm run tests --views rtl -D build=dbg

Use a configuration for genuinely global switches, and an axis for anything an
individual artifact should be able to differ in.
