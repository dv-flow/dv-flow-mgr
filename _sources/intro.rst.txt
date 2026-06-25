############
Introduction
############

DV Flow Manager (``dfm``) is an execution engine for the DV Flow build
specification -- a YAML-based format that captures design-and-verification (DV)
tasks and the dataflow between them in a way that enables concurrent execution
and efficient avoidance of redundant work.

When to use it
==============

When starting a hardware project it is common to write a small shell script to
compile the HDL sources. Over time that script grows to cover the testbench,
multiple simulators, synthesis, regressions, and more. DV Flow Manager is meant
to be lightweight enough to start with instead of that script, and to keep
scaling as the project grows -- without a rewrite.

Reach for DFM when you want:

* reproducible, incremental builds that skip work that is already up to date;
* concurrent execution of independent steps, derived automatically from
  declared dependencies;
* reusable, shareable task libraries (packages) for tools and methodologies;
* variant management -- debug vs. release, alternate tools, deployment targets --
  via :doc:`configurations <guide/configurations>` selected with ``-c``;
* a flow that AI agents can discover and drive (see :doc:`ai/index`).

Mental model: packages, tasks, dataflow
=======================================

A DV Flow specification is built from three concepts:

* **Package** -- a parameterized namespace that defines tasks and types. A
  package is described by a ``flow.yaml`` file (plus any fragments it
  includes).
* **Task** -- a processing step in a flow. A task can be as simple as gathering
  a list of files or as involved as building a hardened macro from several
  source collections.
* **Dataflow dependencies** -- tasks are related by dataflow. A task runs once
  the data from all of its dependencies is available, and it produces data
  items that downstream tasks consume.

The *structure* of the graph (which tasks depend on which) is known statically,
before execution. The *data* conveyed between tasks is only known at runtime.

A small example
===============

.. code-block:: yaml

    package:
      name: my_ip
      tasks:
        - name: rtl
          uses: std.FileSet
          with:
            base: "rtl"
            include: "*.sv"

        - name: tb
          uses: std.FileSet
          needs: [rtl]
          with:
            base: "tb"
            include: "*.sv"

        - name: sim
          uses: hdlsim.vlt.SimImage
          needs: [rtl, tb]

        - name: test1
          uses: hdlsim.vlt.RunSim
          needs: [sim]

This flow gathers two collections of source code -- one for the design and one
for the testbench -- compiles them into a simulation image with the predefined
``hdlsim.vlt.SimImage`` task, and then runs the image.

.. mermaid::

    flowchart TD
      A[rtl] --> E[sim]
      B[tb] --> E[sim]
      E --> F[test1]

Because the graph topology is known up front, independent steps run
concurrently. If we add several tests that each depend only on ``sim``, they
all run in parallel once the simulation image is up to date:

.. mermaid::

    flowchart TD
      A[rtl] --> E[sim]
      B[tb] --> E[sim]
      E --> F[test1]
      E --> G[test2]
      E --> H[test3]

Where to go next
================

* :doc:`install` -- install ``dfm`` and tool plug-ins.
* :doc:`quickstart` -- build and run your first flow.
* :doc:`guide/index` -- the full user guide.
