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

The ``feeds`` field provides a way to inject data into existing tasks from
a configuration without modifying the original task definition.  This is
the recommended approach when a config needs to add arguments, options, or
data files to tasks that are defined elsewhere.

.. code-block:: yaml

    package:
      name: my_project

      tasks:
      - root: build
        uses: sim.SimImage
        needs: [rtl, tb]
        with:
          top: [tb_top]

      - root: run
        uses: sim.SimRun
        needs: [build]

      configs:
      - name: debug
        tasks:
          - name: debug_compile_args
            uses: hdlsim.SimCompileArgs
            with:
              args: ["-debug_access+all"]
            feeds: [my_project.build]

          - name: debug_run_args
            uses: hdlsim.SimRunArgs
            with:
              args: ["-gui"]
            feeds: [my_project.run]

Key points:

* ``feeds`` injects data "from the side" into a task without modifying
  its definition.
* The feed target uses the fully-qualified task name
  (``package_name.task_name``).
* This is equivalent to adding the feeding task to the target's ``needs``
  list, but expressed from the producer's perspective.
* ``feeds`` is particularly useful in configs because the base tasks
  remain unchanged -- the config only adds new tasks that connect to
  existing ones.

The ``feeds`` approach keeps the base flow clean and makes config-specific
additions easy to understand and maintain.

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





