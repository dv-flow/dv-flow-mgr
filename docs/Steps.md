
# Tasks and Types
- Load type definitions from YAML
- Load task definitions from YAML

# Data Selection and Extraction
- Sort and select data
- Need to support expressions
- 

# Task Implementation Source/Result Data

Source Data
- Task parameters
- Upstream-change indication
- Memento

Result Data
- List of output parameter sets
- Change indication
- Memento

# Data Combination
-

# Day in the Life
- Task Runner receives outputs from dependent tasks
- ORs input changed' input flags to determine 'changed' flag to pass to task
- Task Runner orders parameters using dependency information
- Task Runner evaluates task-parameter creation code. Uses input data in this process
  - Creates object of appropriate type
  - Evalutes base-up to assign and augment parameter values
- Retrieves memento (if available)
- Passes accumulated data to task
  - changed
  - parameters
  - 
- Receives output from task
  - list of parameter sets
  - changed
  - memento
  - list of markers
  - exit status (?)
- Saves memento and markers for later inspection (central dir?)
- Sets 'self' as source of parameter sets
- Forms output data from
  - changed
  - list of parameter sets

# Creating Task Parameters
- 

# Need execution support for tasks
- Create parameters given the current inputs
  - Need to follow inheritance
  - Last (bottom-up) "value" wins
  - Appends act bottom-up

- Task holds handles to input data from dependencies
  - 
  - Make Task as simple as possible: scheduling item and place to store data

- Something needs to prepare inputs (likely runner)
  - Locate 
- Something needs to process result
  - Save memento in central store (map of task-execution records)
    - Organize with start/finish times, etc

# 
- Create a task type from YAML
  - Taskdef
- Create a task and parameter changes
  - Params are given a value (most-common)
  - Or, a mutator class instance to append/prepend/etc

files = factory.mkTask("std.FileSet", 
  srcdir=os.path.join(os.path.abspath(__file__)),
  params=dict(
    basedir="foo",
    fileType="systemVerilog",
    include="*.sv"
  ))

simImg = factory.mkTask("hdlsim.SimImg", needs=[files])

runner.run(simImg)

## Task constructor 
- Creates the parameter-type data structure
- Creates the parameter-evaluation stack (stack of param-type structs)
- Creates the task (holding eval stack)



- Python layer than can be used with or wihout YAML meta-data
  - Define Task, Define Params
  - Maybe decorator to wrap Task as a Ctor?
  - Must be able to work with YAML-defined content
- YAML layer simply populates Python layer

  @Task.ctor(MyParams)
  class MyTask(Task):
    # Creates an inner static method ctor that can be passed as the constructor

factory.addTaskType(MyTask.ctor)

# Proper values
* Show that can pass individual values
- Need to test append/prepend/path-append/path-prepend
* Need to process and expand expressions
- 

with:
  args: <value>
  # List-of 
  - append-list: 

# Why PSS?
- Key usecases

# Open Source and PSS

# YAML basics
- Load packages and create TaskNodeCtor objects from a YAML file
- Define types in YAML
- Implement a 'task factory'
  - Support package overrides (config setting?)
  - 

# TaskNode, TaskNodeCtor
- TaskNodeCtor exists for each node type
  - Every node declaration in a YAML file
  - Node types accessed via the Python API
- A new node -- likely with different parameter values -- can be created via the API
- A node created via the YAML spec has a dedicated node ctor

When created via the 

# Early Differentiators
- Library of tools with aggressive work avoidance (faster turnaround)
- Cross-tool support (strategy for category support)
- Extract and display markers (easier identification of failures)



