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
merge: per-value merging has no answer for "how do I remove an inherited
value?".

Command-Line Surfaces
~~~~~~~~~~~~~~~~~~~~~

Declaring a value set is what populates:

* the ``(quiet, normal, full)`` annotation and the per-value descriptions in
  ``dfm show task <name> --usage`` and ``dfm run <task> --help``;
* ``choices`` in the ``--usage --json`` document, alongside ``choices_doc`` and
  ``choices_open``;
* ``argparse`` validation for a scalar flag (see `Exposing a Parameter on the
  Command Line`_);
* value completion -- ``dfm complete --task tests --flag detail`` lists the
  accepted values.

The parameter's ``values`` is the *only* place the accepted set is declared, so
the flag, ``-D``, and a ``with:`` override are all checked against the same set.
To narrow what a task accepts, re-declare ``values:`` on the derived task --
that narrows every path at once, not just the flag.

Exposing a Parameter on the Command Line
========================================

A parameter is settable from the command line when its declaration says so:

.. code-block:: YAML

    - name: sim-img
      scope: root
      with:
        build:
          type: str
          value: opt
          cli: true                        # -> --build
          desc: Build variant
          values: [opt, dbg, prof, cov]

.. code-block:: bash

    dfm run sim-img --build prof

``cli: true`` is the whole declaration for the common case: the flag takes the
parameter's own name, and its type, default, help text and accepted values come
from the parameter. There is nothing to restate, and so nothing that can drift.

Use the map form when the flag needs more than its name:

.. code-block:: YAML

    with:
      tests:         { type: list, value: [], cli: {short: t} }
      build_variant: { type: str,  value: opt, cli: {name: build} }
      internal:      { type: str,  value: "",  cli: {hidden: true} }

``short`` adds a single-character option, ``name`` renames the flag (the
parameter it sets is unchanged), and ``hidden`` accepts the option but keeps it
out of help and completion.

How the Type Shapes the Flag
----------------------------

The parameter's declared type decides how the option behaves:

.. list-table::
   :header-rows: 1
   :widths: 15 85

   * - Type
     - Flag
   * - ``str``, ``int``, ``float``
     - takes a value, converted to the declared type
   * - ``bool``
     - a switch: ``--fast`` sets it true, absence leaves the default alone
   * - ``list``
     - repeatable and comma-splitting: ``--views rtl --views tlm`` and
       ``--views rtl,tlm`` are equivalent

Inheritance
-----------

``cli:`` is inherited along ``uses:`` **per parameter**, like ``values:``. A
task that re-declares a parameter to change its default keeps the base's flag.
To remove an inherited flag, re-declare the parameter with ``cli: false``:

.. code-block:: YAML

    - name: quiet-tests
      uses: std.TestRunner
      with:
        detail: { type: str, value: quiet, cli: false }

Project-Wide Flags
------------------

A **package** variable takes the same declaration, and means a project-wide
knob rather than one task's argument -- so its flag applies to whatever task is
being run:

.. code-block:: YAML

    package:
      name: my-proj
      with:
        build:
          type: str
          value: opt
          cli: true
          desc: Build variant for every image and run in this project
          values: [opt, dbg, cov, prof]

.. code-block:: bash

    dfm run tests --build dbg          # the whole project
    dfm run sim-img --build dbg        # ...and any other task in it

``cli:`` on a package variable is collected along the package ``uses:`` chain,
so a **base project can define a command-line interface its leaves inherit** --
which is how a family of projects gets the same flags without restating them.

``dfm run <task> --help`` lists these under **Project options**, because from
the command line they are indistinguishable from the task's own.

If a task parameter and a package variable claim the same flag, the **task
parameter wins** and a warning names both. Neither declaration can see the
other, so the rule is stated once rather than resolved silently; the package
variable stays reachable as ``-D <name>=<value>``.

Scope and Precedence
--------------------

A flag applies **only when its task is the invoked root**. It is inert when the
task is reached as a dependency, so exposing a parameter never changes how a
flow composes.

``-D`` remains the universal escape hatch: it reaches any parameter, exposed or
not. When both are given for the same parameter, the flag wins:

.. code-block:: text

    declared default  <  -P param-file  <  -D  <  --flag

Note the two mechanisms scope differently, deliberately. ``--seed 42`` sets only
the invoked root, while a bare ``-D seed=42`` reaches every task in the graph
with a ``seed`` parameter.

A flag that would collide with one of ``dfm``'s own options is a load-time
error naming both, rather than a flag that silently never reaches the task.

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





