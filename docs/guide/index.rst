##########
User Guide
##########

.. toctree::
   :maxdepth: 1
   :caption: Core Concepts

   concepts
   packages
   tasks
   dataflow

.. toctree::
   :maxdepth: 1
   :caption: Authoring Flows

   parameters
   configurations
   expressions
   control_flow
   filters
   visibility
   error_handling
   stdlib

.. toctree::
   :maxdepth: 1
   :caption: Running Flows

   running
   incremental
   caching
   runners

.. toctree::
   :maxdepth: 1
   :caption: Extending DV Flow

   developing_tasks
   script_io
   python_tasks
   advanced

This User Guide is organized by what you are doing: understanding the
**core concepts**, **authoring** a flow, **running** it, and **extending** DV
Flow with your own tasks.

New to DV Flow Manager? Start with :doc:`/intro` for the mental model
(packages, tasks, and dataflow) and :doc:`/quickstart` to build your first
flow. The chapters below then go deeper on each topic.

* **Core Concepts** -- packages, tasks, and how dataflow ties them together.
* **Authoring Flows** -- parameters, expressions, filters, visibility, error
  handling, and the standard library.
* **Running Flows** -- incremental/up-to-date execution and task runners.
* **Extending DV Flow** -- implementing your own tasks (shell first, then
  Python) and advanced features.

