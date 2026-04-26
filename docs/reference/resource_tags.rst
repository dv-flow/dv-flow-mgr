##############
Resource Tags
##############

The ``std.ResourceTag`` type declares compute resource requirements on
individual tasks. Cluster runners (LSF, SLURM) use these tags to select
appropriate worker nodes. The local runner ignores them.

Type Definition
===============

``std.ResourceTag`` extends ``std.Tag`` and adds the following fields:

``cores`` (int, default 1)
    Number of CPU cores required.

``memory`` (str, default ``"1G"``)
    Memory requirement with unit suffix (e.g. ``"512M"``, ``"2G"``,
    ``"32G"``).

``queue`` (str, default ``""``)
    Target queue name. Empty means use the queue from runner config.

``walltime`` (str, default ``"1:00"``)
    Maximum walltime in ``HH:MM`` format.

``resource_class`` (str, default ``""``)
    Named resource class from runner config. When set, overrides
    ``cores`` and ``memory`` with the class definition.

Usage Examples
==============

Explicit resource requirements:

.. code-block:: yaml

    tasks:
      - name: compile_rtl
        uses: hdl.Compile
        tags:
          - std.ResourceTag:
              cores: 4
              memory: "8G"

Named resource class:

.. code-block:: yaml

    tasks:
      - name: run_sim
        uses: hdl.Simulate
        tags:
          - std.ResourceTag:
              resource_class: large
              walltime: "4:00"

Resource Resolution Precedence
==============================

When the runner resolves resource requirements for a task:

1. If ``resource_class`` is set on the tag, the named class is looked up
   from the runner config. The class provides ``cores``, ``memory``, and
   optionally ``queue`` and ``resource_select``.

2. Otherwise, explicit ``cores``, ``memory``, ``queue`` values from the
   tag are used.

3. Any field not set by the tag or resource class falls back to the
   runner config ``defaults`` section.

4. The ``project`` field always comes from ``runner.lsf.project`` in the
   config (not from the tag).

5. ``resource_select`` predicates from the config and the resource class
   are accumulated (combined with ``&&``).

Resource Classes
================

Resource classes are named bundles defined in runner config:

.. code-block:: yaml

    runner:
      resource_classes:
        small:   { cores: 1,  memory: "2G" }
        medium:  { cores: 4,  memory: "8G" }
        large:   { cores: 8,  memory: "32G" }
        gpu:
          cores: 4
          memory: "16G"
          queue: gpu_queue
          resource_select: ["ngpus>0"]

A class may include its own ``queue`` and ``resource_select`` overrides.
See :doc:`runner_config` for the full config reference.
