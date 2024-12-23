
System built on three fundamental datatypes:
- Flow -- Flows supported by a given body of work (ie it's not about the code, it's about how we operate on the code)
- Package    -- represents a static body of source/functionality in the system
  - A package is a type, and supports inheritance and extension
  - A package supports type parameterization
  - A package's parameterization must be expressed in terms of a schema
  - The schema is, effectively, the union of all base schema and that of extensions
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
