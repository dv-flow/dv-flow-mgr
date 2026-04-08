############
Task Runners
############

Task graphs defined by DV Flow can be run in many ways. Because the topology
of task graphs is known before execution, task graphs can be evaluated
both statically and dynamically.

DV Flow Manager defines the ``RunnerBackend`` interface to enable support for
multiple mechanisms to dynamically execute task graphs.

Runner Backends
===============

DFM ships with a **local** runner that schedules tasks across the available
cores on a single machine. Additional backends can dispatch tasks to remote
workers on LSF or SLURM clusters.

See the :doc:`userguide/runners` user guide for details on selecting and
configuring runners, and :doc:`reference/runner_config` for the full
configuration reference.

.. autoclass:: dv_flow.mgr.runner_backend.RunnerBackend
   :members:
   :undoc-members:

.. autoclass:: dv_flow.mgr.runner_backend_local.LocalBackend
   :members:
   :undoc-members:
