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

Strategy Definition
-------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/StrategyDef

Generate Specification
----------------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/GenerateSpec

Cache Definition
----------------

.. jsonschema:: ../../src/dv_flow/mgr/share/dv.flow.schema.json#/defs/CacheDef

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
