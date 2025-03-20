===============
Python Task API 
===============

The core implementation for tasks is provided by a Python `async` method. 
This method is passed two parameters:

* `runner` - Services that the task runner provides for the use of tasks
* `input` - The input data for the task

The method must return a `TaskDataResult` object with the execution 
status of the task, result data, markers, and memento data.

