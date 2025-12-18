###################
Flow-Spec Reference
###################

This section provides detailed reference documentation for the DV Flow 
specification format (flow.dv YAML files).

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
then a top-down search is performed for `flow.dv` files in the subdirectory
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

Package Definition
==================

.. jsonschema:: ../../schema/flow.dv.schema.json#/defs/package-def

Fragment Definition
===================

.. jsonschema:: ../../schema/flow.dv.schema.json#/defs/fragment-def

Task Definition
===============

.. jsonschema:: ../../schema/flow.dv.schema.json#/defs/task-def

Import Definition
=================

.. jsonschema:: ../../schema/flow.dv.schema.json#/defs/import-def

Parameter Definition
====================

.. jsonschema:: ../../schema/flow.dv.schema.json#/defs/param

Task Dependency
===============

.. jsonschema:: ../../schema/flow.dv.schema.json#/defs/task-dep
