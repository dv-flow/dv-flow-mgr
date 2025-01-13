.. DV Flow Manager documentation master file, created by
   sphinx-quickstart on Tue Jan  7 02:06:13 2025.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

DV Flow Manager
===============

DV Flow Manager helps users capture the tasks and dataflow in their
design and verification (DV) flows. You can think of DV Flow Manager as a 
sort of "make for silicon engineering".

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
   reference
