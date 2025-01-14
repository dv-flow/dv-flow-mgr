.. DV Flow Manager documentation master file, created by
   sphinx-quickstart on Tue Jan  7 02:06:13 2025.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

DV Flow Manager
===============

DV Flow Manager provides a "make for silicon engineering": a specification
for capturing design and verification (DV) tasks and dataflow in a way that
enables concurrent execution and efficient avoidance of redundant work.

.. mermaid::

    flowchart TD
      A[IP Fileset] --> B[Testbench]
      C[VIP Fileset] --> D[Precompile]
      D --> B
      B --> E[SimImage]
      E --> F[Test1]
      E --> G[Test2]
      E --> H[Test3]



.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   intro
   reference
