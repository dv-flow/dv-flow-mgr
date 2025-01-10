
System built on three fundamental datatypes:
- Flow -- Flows supported by a given body of work (ie it's not about the code, it's about how we operate on the code)
- Package    -- represents a static body of source/functionality in the system
  - A package is a type, and supports inheritance and extension
  - A package supports type parameterization
  - A package's parameterization must be expressed in terms of a schema
  - A package's schema is the union of all base schemas and that of extensions
  - Different static parameterizations are different, and may have different functionality
  - A Package specifies its dependencies in terms of other packages
  - 
  - A package contains
    - Task type definitions
    - Imports of other packages (restrict to top level?)
    - Tasks (flows)
- Task       -- represents an operation
  - Tasks are types that are a cross between classes and functions
    - Each invocation is unique. No shared state
  - 
  - Much of the time, we will use the same task many times with different
  - Each task type supports defining instance parameters
  - 
  - A task has a Task Type
- TaskParams -- data connecting tasks

- FileSet -- 

# Task vs Task Template
- Tasks have a name
- Tasks have a 

Like to only have one.

export rtl : Fileset
- Question: can we later use 'rtl' as a type to extend?

Specfy dataflow as part of 

# Required Capabilities
- Capture the output of a flow and publish it for use in place of the original flow
  - <RTL> -> <RTL2GDS> -> <GDS>
  - Package such that <GDS> flow is available
- Incremental builds with dependencies (likely depends more in the lower-level tools than dv-flow-mgr)
- 

flow:
  name: wb_dma
  parameters:
    - name: variant
      type: string
      restrictions:
      - A
      - B
  import:
    - std
    - 
  super:
    - std::SimFlow # Defines top-level available tasks

?? Build things like type extension into core library ??

  A task is a type
  Type has data that can be 

  tasks:
    - name: fs_sim
      type: std::CompoundTask
      parameters:
      - name: abc
        type: int
      - 
      # Schema here is type-dependent
      body:
        - task: abc
          type: 

    - name: fs_synth
              
    ...

Note: prefer composition over inheritance


# Data
- Possible for fileset / fileset collection to specify a clean-up function?
- Decouple data transfer from computation?
  - Queue 'failed-sim' data directory for transfer back to central, while new simulation proceeds


# Built-in Tasks

- package: 
    name: hdl.sim
    abstract: True

    tasks:
    - name: library
      - Depends on a fileset or filesets (require all to be source)

    - name: precomp_ip
      - Depends on a fileset or filesets (might have other pre-comp-ip libraries, in addition to source)
      - Must specify root module
      - Outputs a single PreCompIP Fileset

    - name: sim_image
      - Depends on a fileset or filesets
      - Outputs a fileset containing d

    - name: sim_run
      - Depends on an HdlSimImage fileset
      - May also depend on data filesets
      - Outputs fileset containing simulation data

- package: 
    name: util
    
    tasks:
      - name: cache
        - Inputs a fileset or filesets
        - Outputs the same fileset or filesets, optionally with a redirect to a temporary directory
        - TODO: need a way to determine required lifetime for cached data. Valid at least for subtree to which cached fileset is passed?


# Package Structure
- Packages are structural (single root defininition per)
- Sub-content can be defined in separate files
- It is an error to include a package file (ie package P1 includes a file that defines package P2)
  - We want a sub-IP to still exist in its own dedicated namespace
  - Referencing a package is different from including it

- A package can be defined to be abstract
- A package can be defined to implement an abstract package

- Sub-package files always exist 

- A package can be defined to extend a package
  - This allows some tasks to provide default implementations

- package: hdl.sim.vlt
    implements: hdl.sim

    tasks:
      - name: 



package:
  name: fwperiph_dma
  type: 

  tasks:

# Package import
- Packages and package variants can be imported

# Differences
- Goal is to build data packages to pass to a task, or tasks, instead of building a single global data structure


# DV Flow Manager 1.0.0
- Packages and Fragments
- Package Import
- Python implementation of YAML-defined tasks
- Parameters and Properties
- Modifying the value of input parameters
- Strategy for tool-specific options
- Tasks for reusable sim-image components (sim-image, library, ip)
- Work-avoidance schemes for SV

## Use Cases
- Compile simulation image (debug, optimized)
- Run user-specified simulations

# DV Flow Manager 2.0.0
- Package inheritance ("project templates")
- VSCode log browser - visualize task graph ; navigate / view individual task logs
  - See execution times
  - See which tasks performed real work (output of 'changed')
- Task/sub-graph execution delegation interface (implementation for LSF, SLURM, etc)
- 

# DV Flow Manager 3.0.0

# DV Flow Manager 4.0.0
- VSCode flow-file development support (error checking, completion, navigation)
- VSCode run integration (launch run from VSCode ; monitor execution/completion)

# DV Flow Manager 5.0.0
- VSCode debug support (step through task graph ; inspect variable values)





