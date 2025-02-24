
A task graph is composed of task nodes. A task is defined as the combination
of:
- behavior
- parameters data structure
- rules/process for specifying parameter values

Task behavior must:
- accept input data composed of:
  - parameter data structure with values populated
  - change notification
  - (optional) meta-data
- produce result data composed of:
  - list of parameter sets
  - change notification
  - (optional) meta-data
  - (optional) markers
  - execution status

