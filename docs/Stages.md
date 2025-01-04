
# Proof of Life
- Support multiple packages
- Support tasks and compound tasks (share directory and scheduling)
- Support tasks and task templates
- Need a simple directory manager in the session
- Need a simple I/O management system
  - debug
  - verbose
- Need a merge strategy for input data
  - Union of top-level keys
  - Process each value type individually
  - Dict[str,object]: union of key/value pairs. Conflicting key/value is an error
  - 
- No need for conditionals or configuration yet
- Show that we can build sensible flows

- Task:
  - Merges parameters from the inputs to create an 'input' object
  - Can manipulate 'input' object to produce output object
  - Must always return a 'output' object

- Need user-specified operations on output data
  - depends:
    - hdl.sim.RunArgs
  - name: out.sim.args
    append: a

- Built-in Tasks
  - Env
    - Collects the current environment (possibly with filters)
    - Sets as 'env' in the output data
  - FileSet
    - Collects file paths based on a request pattern
    - Saves a memento with identified file paths and timestamps
    - Emits output data with an indication whether the fileset or its files have changed
  - Unix command
    - Has a working dir
    - Accepts a list of command-line options
    - Specify I/O handling (direct to file ; display output)
    - Unconditional action. Always executes and always indicates a change
  - 

- Run a task of a specific type
  - Specifies the task type (technically, enables parameter check)
  - params:
    - operate on default values
    - must apply to created Python object
    - These are ask-local parameters

- 

- Hdl.Sim Tasks
  - Library
    - Takes source FileSets as input
      - Basically a list of root files to compile
    - Creates an incremental library
    - Only runs build if the library sources or other deps changed
      - If one of the inputs changed, then a root file has been added or changed
      - If all deps are unchanged, then perform a local SV dep check
  - IP
    - Takes source FileSets as input
    - Takes top module name as input
    - Creates a fully-linked IP 
    - Only runs build if the sources changed
  - SimImage
    - Takes source FileSets, Library, and IP as input
    - Elaborates a simulation image
    - Outputs output data with the simulation directory
  - SimRunArgs
    - Produces output data with default simulation-run arguments
  - SimRun
    - Takes SimImage as input (enough info to run)
    - Takes additional parameters for plusargs, etc

TaskTemplate only needed to enable checking

# Real World
-> Show running on a UVM example
--> UVM separately compiled (save incr time when nothing changes in UVM)
--> Design / Testbench compiled separately (save incr time building design)



- Session must provide a way to submit an execution request (scheduler)

# Real World 2

Need a snapshot capability to package up the result of one or more runs into
a directory that can be exported

How do we think about hierarchy?
- 'build' should get a chance to specify its working directory
  - push cwd up-stream?

package:
  name: my_design

  tasks:
    - name: export
      type: ExportTask
      depends: build
      params:
        - Spec on what goes where...


What about PSS?
- pre-step to create
  - pre-compiled PSS snapshot
  - SV source files for integration

- RunSim with PSS is:
  - Add SimImage dependency on PSS pre-compile task
  - 'snapshot' directory is a different fileset that passes through to CreatePSSTest
  - Must be able to reach down and set task parameters
  - Test is a compound action
    - 

Compound Task
- Task with a name and (optionally) parameters
- Body section that specifies tasks and their connections

- name: PssTestBase
  tasks: # Runs tasks sequentially, passing task deps to first, output, ...
    - name: GenPssTest
    - name: SimArgs
    - name: RunSim

# Tasks should specify what data they produce
  - filesets

- name: MyPssTestBase
  type: PssTestBase
  params: # Can select tasks based on parameter value without running
    - name: tags
      type: set # Causes it to be created if it doesn't exist
      append: [smoke, precheck]

  tasks:
    - name: SimArgs
      params:
        - name: plusargs
          append:
            - +foo
            - +bar

Note: Cache elaborated tree?
- For a given root (eg test), perform all hard-coded 


  # Need a way to add dependencies to sub-tasks

# Library
- Add in the notion of base packages
-> inherit common settings
-> inherit common tasks
-> fill in details, not whole flow


Basic concept is:
- Task implementation accepts input JSON from 0..N tasks
- Merges that JSON to a single view used within the task
- Task loads a memento (if available) and uses to compute up-to-date status
- Task carries out work
- Optionally produces and saves a memento returned on next execution
- Produces output JSON for downstream tasks to consume

Key: all 


# First step
- verilator simple compile flow
- single file
- StdLib
  - FileSet
  - Exec

- Results:
  - end-to-end system check
  - avoid recompile when primary sources do not change

