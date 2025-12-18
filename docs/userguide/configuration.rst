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

Overrides provide the ability to manipulate the value of parameters and
the target of package references. For the most part, overrides control
features that are outside the declaration scope of the override.

Package Overrides
-----------------

The DV Flow `hdlsim` library provides tasks for building HDL simulation
images using a variety of toolchains. The key operations supported by
these tools are sufficiently common that a core set of tasks is defined
to be implemented by each toolchain.

Overrides provide a mechanism by which the user can dynamically select
the appropriate toolchain to use without modifying the flow specification.

.. code-block:: YAML

    package:
      name: proj
      with:
        sim:
          type: str
          value: vlt

      overrides:
       - for: hdlsim
         use: hdlsim.${{ sim }}

      tasks:
      - name: hdlsim.SimImage
        # ...

The override directive changes how the package name `hdlsim` is
resolved. Within the scope of package `proj`, any reference 
to package `hdlsim` will, instead, resolve to the package `hdlsim.vlt`.

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





