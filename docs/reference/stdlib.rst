################
Standard Library
################

Every task, data type and filter the ``std`` package publishes. **This page is
generated** from ``src/dv_flow/mgr/std/flow.yaml`` by ``sphinx-dv-flow``, so it
cannot drift from what the package actually declares.

For the narrative -- what the standard library is for, how failures propagate,
which task to reach for -- see :doc:`/guide/stdlib`.

.. dvf:autopackage::
   :types:

Filters
=======

.. note::

   Filters are declared but **not yet resolved by the engine**. See the note on
   each entry below, and ``docs/guide/filters.rst``.

Data flow
=========

What produces each item type, and what accepts one. This is the map that says
which tasks can be wired together.

.. dvf:dataflow::
