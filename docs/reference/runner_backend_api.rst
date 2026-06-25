###################
Runner Backend API
###################

The ``RunnerBackend`` interface enables support for multiple mechanisms to
dynamically execute task graphs. DFM ships with a **local** backend that
schedules tasks across the available cores on a single machine; additional
backends can dispatch tasks to remote workers on LSF or SLURM clusters.

See :doc:`/guide/runners` for the user-facing guide on selecting and
configuring runners, and :doc:`/reference/runner_config` for the full
configuration field reference.

.. autoclass:: dv_flow.mgr.runner_backend.RunnerBackend
   :members:
   :undoc-members:

.. autoclass:: dv_flow.mgr.runner_backend_local.LocalBackend
   :members:
   :undoc-members:
