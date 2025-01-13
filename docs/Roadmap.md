
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
- Coarse/fine-grained dependency management
  - Mark task dependency as having a "coarse" requirement. Causes 
    the task to be run if it hasn't been run already. Doesn't perform
    exhaustive analysis.
  - Maybe allow subtree dependency analysis? Single analysis point to
    determine up-to-date status on a whole collection of source

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


# Core Principles
- Relevant DAG can be constructed statically
  - Tasks are not inferred based on dataflow content
  - Tasks may be created based on statically-available data
- Dataflow is dynamically typed (union of content)
- Tasks pass-through filesets that are not relevant for them
  - Enables injecting new data when convenient, even if it won't be used until later
  - Can have 'filter' tasks if there is a need to clean-up
- Dependency analysis is not delegated 
  - Allows static DAG construction
- Extensible -- by users and organizations
- Implementation independent (not tied to a specific implementation language)

