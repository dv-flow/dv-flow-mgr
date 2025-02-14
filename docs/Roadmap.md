
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
- Define task status. Tasks can have at least two types of failures
  - Pass/Fail: Fail halts successors
    - Fail must come with a message and extra info
  - Status markers/counters
    - errors / warnings / notes 
  - Want known fileset to capture logfiles and related info
  - Central params and datasets?
    - Datasets preserve dependency relationships
    - Datasets are the best way to aggregate settings
  - Typed parameter sets
  - Dependencies provide order in which to evaluate
  - Operations on variables

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
- Support capturing schema for structured task data
- Mark tasks as producing and accepting certain data
  - FileSet task `produces` fileset of `type`
  - SimImage task `accepts` systemVerilogSource, verilogSource, verilogPreCompLib, etc
  => Mostly useful for checking and suggestion
  => As more are marked, can treat as more binding
- 

# Library

## 1.0.0
- Std
  * Null (combine dependencies, set variables). Implements tasks that do not specify 'uses'
  - Exec
  - Make
  * FileSet
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


# TODO
- Need some way to signal rough core consumption. Challenge is to complete
  build as quickly as possible via coarse and fine-grained parallelism
  - Parallelism tends to follow exponential curve. High parallelism early ; Low later
  - Reasoning about curves may guide resource over-subscription
- Each task needs memory hints / requirements as well
- Dependency strategy for Exec/Make
  - Specify dependency file created by task
  - When the timestamp is updated, task is known to have been rebuilt
- 

- Allow each task to emit a series of markers as part of the result
  - Enables users to easily click on first N warnings/errors in each step
    without needing to find and open a logfile
- Allow files to be attached as part of the result
