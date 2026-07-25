############################
Parameters and Configuration
############################

DV Flow specifications provide several mechanisms for statically
configuring the elements of a flow. The two key mechanisms are
*parameters* and *overrides*. 

Parameters
==========

Static parameters appear in multiple places within a DV Flow specification.
Parameters can be declared at the package and task level. 

Parameter-Resolution Order
--------------------------

The value of parameters are resolved during loading and elaboration of
a DV Flow specification in the following order.

* Package-level parameters
* Overrides
* Task-level parameters

Declaring Parameters
--------------------

Parameters can be declared at both the package and task level. The syntax
for declaring and setting the value of a parameter differs in that a 
parameter declaration specifies the `type` of the parameter.

.. code-block:: YAML
    
    package:
      name: proj
      with:
        level:
          type: str
          value: "Package"

      tasks:
      - name: PrintMessages
        with:
            upper:
              type: str
              value: "Compound Task"
        body:
        - name: t1
          uses: std.Message
          with:
            msg: |
              "Hello from ${{ upper }}"
              We're in ${{ level }} scope

        - name: t2 
          uses: PrintMessages
          with:
            value: "t2"

In the example above, we declare package- and task-level parameters.
Tasks can refer to parameters declared in the scope of their 
containing package or use a fully-qualified reference to another package. 
Inner tasks can refer to parameters declared by their containing task,
and call also refer to package-level parameters.

The following parameter types are supported:

* **bool**
* **int**
* **list**
* **map**
* **str**

Value Sets
----------

A parameter can declare the values it accepts with ``values``:

.. code-block:: YAML

    with:
      detail:
        type: str
        value: normal
        values: [quiet, normal, full]

The set is attached to the *parameter*, so it is enforced everywhere the
parameter can be set -- the declaration's own default, a ``with:`` override in
a task that ``uses:`` this one, ``-D task.detail=...``, a first-class
``--detail`` flag, and a package variable. An invalid value is reported where
it was written, with the alternatives and a guess:

.. code-block:: text

    flow.yaml:41: task 'tests' parameter 'detail': 'ful' is not a valid value.
                  Valid values: quiet, normal, full. Did you mean 'full'?

Documenting the values
~~~~~~~~~~~~~~~~~~~~~~

Because the value set replaces prose describing the legal values, each value
can carry its own description. These appear in ``dfm show task <name> --usage``
and ``dfm run <task> --help``:

.. code-block:: YAML

    with:
      detail:
        type: str
        value: normal
        doc: Report verbosity.
        values:
        - {value: quiet,  desc: "the headline only"}
        - {value: normal, desc: "the headline, plus every failing case"}
        - {value: full,   desc: "every case, after the generic task summary"}

The two forms can be mixed: any element that is not a ``{value: ..., desc: ...}``
map is taken as a bare value.

Open Sets
~~~~~~~~~

A plain list is a *closed* set: anything else is an error. Some sets are
instead a list of *known* values that a downstream flow may legitimately extend
-- the simulator backends a library ships with, for instance. Declare those as
open:

.. code-block:: YAML

    with:
      sim:
        type: str
        value: vlt
        values: {of: [vlt, vcs, mti, xcm, xsm, ivl], open: true}

An open set still drives help and shell completion, but an unlisted value
produces a warning rather than an error, so a site that adds a backend is not
blocked by a declaration it does not own.

List Parameters
~~~~~~~~~~~~~~~

On a ``list`` parameter the set constrains the **elements**, which is what a
multi-valued selector needs:

.. code-block:: YAML

    with:
      views:
        type: list
        value: []
        values: [rtl, tlm, gate]

``--views rtl,gate`` is accepted; ``--views rtl,bogus`` fails naming ``bogus``.
Value sets are not supported on ``map`` parameters.

Inheritance
~~~~~~~~~~~

A value set is inherited along ``uses:`` **independently of the value**. A task
that re-declares a parameter only to change its default keeps the base's set
and is checked against it:

.. code-block:: YAML

    - name: quick-tests
      uses: std.TestRunner
      with:
        detail: quiet          # checked against TestRunner's set

A task that re-declares ``values:`` replaces the inherited set outright, either
narrowing or widening it. This is whole-set replacement rather than a per-value
merge, matching how ``cli:`` blocks are inherited.

Command-Line Surfaces
~~~~~~~~~~~~~~~~~~~~~

Declaring a value set is what populates:

* the ``(quiet, normal, full)`` annotation and the per-value descriptions in
  ``dfm show task <name> --usage`` and ``dfm run <task> --help``;
* ``choices`` in the ``--usage --json`` document, alongside ``choices_doc`` and
  ``choices_open``;
* ``argparse`` validation for a scalar flag declared in a ``cli:`` block;
* value completion -- ``dfm complete --task tests --flag detail`` lists the
  accepted values.

A ``cli:`` block may still declare its own ``choices:``, which wins for that
flag. Use it only to *narrow* what a flag accepts relative to the parameter;
the parameter's ``values`` is what every other path enforces.

Overrides
=========

Overrides provide the ability to manipulate the value of parameters.
For the most part, overrides control features that are outside the 
declaration scope of the override.

Parameter Overrides
-------------------

Each task within a DV Flow specification has a unique name that is 
statically known. This allows the value of individual parameters 
to be overridden. Obviously, extreme care should be taken when
doing this, since it is a poor encapsulation practice. That said,
this capability can be very useful when very precise control must
be exercised over a flow specification without physically modifying it.

.. code-block:: YAML

    package:
      name: proj

      overrides:
       - for: hdlsim.debug_level
         use: 1

      tasks:
      - name: hdlsim.SimImage
        # ...

In the example above, the `hdlsim` package exposes a parameter named
`debug_level` that controls the default debug level that tasks within
the package will instruct the HDL simulator tools to use. For example,
setting debug_level to `1` causes the simulator to save waveforms.

The overrides directive changes the value of the `debug_level` parameter
for all tasks under the scope of the root package `proj`.

As described in the `Resolution Order` section, we could also override
this parameter value using an environment variable or command-line argument.



Append and Prepend
==================

When overriding list-type parameters, you often want to add items rather
than replace the entire list.  The ``append`` and ``prepend`` fields
support this:

.. code-block:: yaml

    # In a config or task override
    with:
      args:
        append: ["-extra-flag"]

    # Prepend items to the front of the list
    with:
      incdirs:
        prepend: ["/priority/include"]

The resolution formula is: ``prepend + (value or base_value) + append``.
If ``value`` is also set, it replaces the base value before append/prepend
are applied.  If only ``append`` or ``prepend`` is set, the base value is
preserved.

.. code-block:: yaml

    package:
      name: my_project

      tasks:
      - name: compile
        uses: sim.SimImage
        with:
          args: ["-Wall"]  # Base value

      configs:
      - name: strict
        tasks:
        - name: compile_strict
          override: compile
          with:
            args:
              append: ["-Werror"]
              # Result: ["-Wall", "-Werror"]

Using feeds in Configurations
==============================

The ``feeds`` field lets a configuration inject arguments, options, or data
files into existing tasks without modifying their definitions -- the
recommended way to add config-specific inputs to a flow. This pattern is
covered, with examples, in :doc:`configurations` (see *Injecting Options with
feeds*).

Resolution Order
================

DV Flow specifies the resolution order for parameters and overrides
such that "outer" specifications take precedence over "inner" specifications.

The precedence order is as follows (highest to lowest):

* External controls, such as command-line options
* Specifications in the root package 
* Specifications within non-root packages
  * Later specifications take precedence over earlier ones in the case of conflict.
* Specifications within an outer task
* Specifications within an inner task
* Specifications within an base task





