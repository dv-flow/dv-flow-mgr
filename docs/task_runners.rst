############
Task Runners
############

Task graphs defined by DV Flow can be run in many ways. Because the topology 
of task graphs is known before execution, task graphs can be evaluated 
both statically and dynamically. 

DV Flow Manager defines the TaskRunner interface to enable support for 
multiple mechanisms to dynamically execute task graphs.

Currently, DV Flow Manager implements a single-machine runner that
schedules tasks across the available cores.

.. autoclass:: dv_flow.mgr.TaskRunner
   :members:
   :exclude-members: model_config

DV Flow Manager may provide the following runner options in the future:

* Statically split the task graph such that the sub-graphs can be run
  by another graph-execution tools
* Dynamically distribute nodes in the task graph across multiple machines
  in a SLURM- or LSF-like cluster.
