
# Flow Specification
The Flow Specification is comprised of the Flow YAML Schema and the 
semantic definition of how task graphs defined using the flow specification
are evaluated.

## 1.0.0
- Package definition
- Package import
- Task definition
  - "with" variable usage
  - Operations on input and output data
  - Operations on task parameters
- Package fragments

## 2.0.0
- Parameterized package definition and use
- Package "uses" (type/inheritance)
- Task "with"-data definition (tasks can add their own parameters)
- Task Groups / Sub-DAG

## 3.0.0
- JQ-based data extraction
- YAML task templates / expansions
- Support for annotating job requirements 

# Library

## 1.0.0
- Std
  - Null (combine dependencies, set variables). Implements tasks that do not specify 'uses'
  - Exec
  - FileSet
  - PyClass - implement a task as a Python class (load from a module)

- HdlSim
  - Library  - creates a reusable simulator-specific library
  - IP       - create a reusable single-module IP library
  - SimImage - creates a simulation image 
  - SimRun


## 2.0.0
- Std
  - DefineData (Declares a data structure to pass)
  - Export   - Captures the result of some task in a dedicated directory

## 3.0.0
- Std
  - 

# DV Flow Manager

## 1.0.0
- Simple 'max-jobs' process scheduler

## 2.0.0
- Progress meter and status line to monitor builds (non-verbose)
- Multi-level mechanism for monitoring jobs
  - High-level with a progress bar
  - 
- Log-creation feature that assembles a total log from per-task logs

## 3.0.0
- Provide link to source for error messages
- Improve debug logging

## 4.0.0
- Improve status display by allowing actions to signal count-like information (+pass, +fail)
- OpenTelemetry support


## 5.0.0
- Need some form of site settings

