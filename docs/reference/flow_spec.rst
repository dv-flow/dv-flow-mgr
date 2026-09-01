###################
Flow-Spec Reference
###################

This section provides detailed reference documentation for the DV Flow 
specification format (flow.yaml YAML files).

File Root Elements
==================

Each `flow.yaml` file either defines a package or a package fragment.
Each package is defined by the content in its root `flow.yaml` file 
and that in any `fragment` files that are specified in the root 
package file or its fragments.

.. code-block:: yaml

    package:
        name: proj1

        # ...

        fragments:
        - src/rtl/flow.yaml
        - src/verif

Each package fragment element specifies either a directory or a file.
If a file is specified, then that file is loaded. It is expected that the
content will be a DV-Flow package fragment. If a directory is specified,
then a top-down search is performed for `flow.yaml` files in the subdirectory
tree. 

The structure of a package fragment file is nearly identical to a package
definition. For example:

.. code-block:: yaml

    fragment:
        tasks:
        - name: rtl
          type: std.FileSet
          params:
            include: "*.sv"

Remember that all fragments referenced by a given package contribute to 
the same package namespace. It would be illegal for another flow file
to also define a task named `rtl`.

The schema definitions below are generated from
``dv.flow.schema.json``. They are grouped by role: package structure, tasks,
parameters and types, and enumerations.

Package Structure
=================

Package Definition
------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/PackageDef

.. note::

   ``desc`` and ``doc`` serve different readers. ``desc`` is the one line that
   appears next to the package in a listing, so it has to stand alone.
   ``doc`` is the prose someone reads once they have arrived: what the package
   is for, and which task to run first. Tasks take the same pair.

Fragment Definition
-------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/FragmentDef

Configuration Definition
------------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ConfigDef

Import Definition
-----------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/PackageImportSpec

Override Definition
-------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/OverrideDef

Extend Definition
-----------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ExtendDef

Tasks
=====

Task Definition
---------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/TaskDef

.. note::

   The ``with`` field sets a task's own parameters. The ``set`` field shapes the
   task's *subtree*: a **list** whose items are either assignment maps
   (``{<name>: <value>}``) that rebind a scoped variable read via
   ``${{ pkg.var }}``, or scope items (``{uses?, path?, set: [...]}``) that
   narrow/force by matcher. Outer overrides inner; ``-D`` is the ceiling. See
   :doc:`../guide/scoped_variables`.

   The ``let`` field (scoped variables read via ``resolve()``) is **deprecated**
   in favor of ``set``.

   The ``elaborate`` field names a Python callable (``module:function``,
   signature ``elaborate(ctxt, task, name) -> TaskNode``) that elaborates the
   task type at graph-build time, replacing the default node interior. It is
   bound along the ``uses`` chain (nearest declaration wins), so declaring it on
   an abstract type covers every task that ``uses:`` it -- e.g. hdlsim's
   simulator-backend selector.

.. note::

   ``desc`` and ``doc`` are inherited along ``uses:``, independently of one
   another: a task that leaves either empty takes it from the nearest ancestor
   that sets it. A task that derives from a described base and only narrows it
   is still the thing its base describes, so it should not appear blank in a
   listing. Restate whichever field the derived task genuinely changes; leave
   the other empty to keep the base's wording.

   Note that ``examples`` behave the opposite way -- see below.

Example Definition
------------------

A worked example of using a task: what a reader would actually type. Examples
are documentation, not tests -- nothing runs them, and nothing checks that
``code`` still works.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ExampleDef

.. code-block:: yaml

    tasks:
    - name: sim
      desc: Run the simulation
      examples:
      - title: Run a single test
        caption: Names the test by its `case` tag.
        lang: shell
        code: dfm run sim --tests arb
      - title: Reuse from another package
        code: |
          - name: my-sim
            uses: proj.sim
            with:
              seed: 42

.. note::

   Examples are **not** inherited along ``uses:``. An example is written
   against a specific task name and a specific set of parameters, so
   re-presenting a base task's example under a derived task would show the
   reader something they cannot type. A derived task that deserves an example
   needs its own.

Strategy Definition
-------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/StrategyDef

Select Definition
-----------------

A family of independently-addressable artifact variants. See
:doc:`/guide/variants`.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/SelectDef

Generate Specification
----------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/GenerateSpec

Cache Definition
----------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/CacheDef

Summary Definition
------------------

Selects a framework-provided summary renderer for a task's results.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/SummaryDef

Control Definition
------------------

Runtime control flow -- ``if``, ``match``, ``while``, ``do-while`` and
``repeat``. Mutually exclusive with ``strategy``. See :doc:`/guide/control_flow`.

.. warning::

   ``control:`` is parsed and validated but **not yet executed**: the definition
   does not reach the resolved task, so a task declaring one runs its ``body:``
   unconditionally. See ``tests/unit/test_control_flow_from_flow_file.py``.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ControlDef

Control Case Definition
-----------------------

One case of a ``match`` construct.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ControlCaseDef

Control State Definition
------------------------

Loop state carried between iterations.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ControlStateDef

Filter Definition
-----------------

A reusable transformation usable on the right of a pipe in an expression:
``${{ inputs | name(args) }}``. See :doc:`/guide/filters`.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/FilterDef

Parameters and Types
====================

Parameter Definition
--------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ParamDef

Type Definition
---------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/TypeDef

Complex Type
------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ComplexType

List Type
---------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ListType

Map Type
--------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/MapType

Enumerations
============

Consumes Mode
-------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/ConsumesE

Passthrough Mode
----------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/PassthroughE

Run-Directory Mode
------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/RundirE

Compression Type
----------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/CompressionType

Deprecated
==========

Package Specification
---------------------

.. deprecated:: unreleased

   ``PackageDef.type`` is inert -- nothing reads it, and data types are declared
   with ``types:`` (see `Type Definition`_). It is documented here only because
   the field still exists, so the schema still references this definition.

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/PackageSpec
