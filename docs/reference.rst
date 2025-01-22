###################
Flow-Spec Reference
###################

File Root Elements
==================

Each `flow.yaml` file either defines a package or a package fragment.
Each package is defined by the content in its root `flow.yaml` file 
and that in any `fragment` files that are specified in the root 
package file or its fragments.

.. jsonschema:: ../src/dv_flow/mgr/share/flow.json#/defs/package-def

.. code-block:: yaml

    package:
        name: proj1

        # ...

        fragments:
            - src/rtl/flow.yaml
            - src/verif


.. jsonschema:: ../src/dv_flow/mgr/share/flow.json#/defs/fragment-def

A fragment has similar content to a root-package file.

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

.. jsonschema:: ../src/dv_flow/mgr/share/flow.json#/defs/import-def

.. jsonschema:: ../src/dv_flow/mgr/share/flow.json#/defs/param

.. jsonschema:: ../src/dv_flow/mgr/share/flow.json#/defs/task-def

.. jsonschema:: ../src/dv_flow/mgr/share/flow.json#/defs/task-dep

And, now, after
