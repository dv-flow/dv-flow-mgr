===============
Python Task API 
===============

The core implementation for tasks is provided by a Python `async` method. 
This method is passed two parameters:

* `runner` - Services that the task runner provides for the use of tasks
* `input` - The input data for the task

The method must return a `TaskDataResult` object with the execution 
status of the task, result data, markers, and memento data.

TaskDataInput
=============

An object of type `TaskDataInput` is passed as the `input` parameter 
of the runner method. 

.. autoclass:: dv_flow.mgr.TaskDataInput
   :members:
   :exclude-members: model_config

TaskDataItem
=============

Data is passed between tasks via `TaskDataItem`-derived objects. 
Each task may produce 0 or more `TaskDataItem` objects as output. 
A task receives all the `TaskDataItem` objects produced by its
dependencies. 

.. autoclass:: dv_flow.mgr.TaskDataItem
   :members:
   :exclude-members: model_config


TaskDataResult
==============
Task implementation methods must return an object of type 
`TaskDataResult`. This object contains key data about 
task execution.

.. autoclass:: dv_flow.mgr.TaskDataResult
   :members:
   :exclude-members: model_config

TaskMarker
==========
Tasks may produce markers to highlight key information to the
user. A marker is typically a pointer to a file location with
an associated severity level (error, warning, info).


.. autoclass:: dv_flow.mgr.TaskMarker
   :members:
   :exclude-members: model_config

.. autoclass:: dv_flow.mgr.TaskMarkerLoc
   :members:
   :exclude-members: model_config

