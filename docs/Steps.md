
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
- 