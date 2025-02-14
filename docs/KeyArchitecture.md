
# Tasks
- A task has 0..N dependencies (references to tasks whose output
  data must be available prior to execution of the task)
- The input data available to a task includes
  - Output data from its dependencies
  - Memento data from its prior execution (a memento is a record of task execution)
    - Makes sense to include markers here
  - Locally-specified data (ie task parameters)
- The core implementation of a task is invoked with a
  consolidated set of data that is specified in the task definition.
  - Example: select all FileSet that have kind systemVerilog, verilog, or VHDL 
- The output of a task is comprised of (think of this as a filter?)
  - Output data from its dependencies
  - Memento data from the implementation, including marker information

# Types
- Types are named structures

# Task Parameters
- A task may have parameters. Parameters are singletons, and are
  not extensible from outside. 
- If a task needs to accept outside input, it must select that
  by type from input parameter sets
- Direct parameters
- Task parameters are exposed to task implementation via a type with the task name
- Do we really need this?
- Using explicit types results in one extra layer of indirection
- Still may have to deal with ambiguity...

- name: RunSim
  uses: SimRun
  with:
  - name: simargs
    type: 
      list:
        item: SimArgs
    value: ${{ jq in.[]}}
  - uses: SimArgs
    with:
    - append-list

So... Tasks do not have parameters. 
- Tasks can inject parameter sets into the input set
- Tasks can control what emerges from the task

plusargs: .[] select(uses==SimArgs) | 

# Cross-Task Dataflow
- Cross-task dataflow is comprised of a collection of typed objects
  containing typed fields.
- Augmenting data is done by injecting new object instances into
  the dataset. For example:
  - The dataset contains an object for specifying simulation runtime
    arguments. It contains a directive to append "+UVM_TEST=my_test" 
    to the arguments
  - I add a new runtime-arguments object that contains a directive
    to append "+debug" to the arguments
  - The consumer will see [+UVM_TEST=my_test +debug]


# Data-Combination Rules
- In most cases, data must be flattened in order to use it. For example,
  
- 
