
# Task Dependencies

Tasks operate on input datasets (eg FileSets), parameters specified to the
task, and sometimes external files. For example, a Fileset accepts a 
glob pattern for identifying file paths ; the set of paths is only
known after applying the glob.

It's advantageous to only evaluate tasks when one of the three input
sources have changed.

## Dependency Check Process
A task records its inputs and outputs in an exec.json file in its
run directory. (TODO: the task must also record its parameter values).
If this exec record does not exist, then the task is not up-to-date
and must be run.

If the exec record does exist:
- The task is not up-to-date if the recorded parameter values differ
  from the new parameter values
- The task is not up-to-date if any of the current input datasets are
  marked as 'changed' (ie their source is a task that was evaluated)
- The task is not up-to-date if any aspect of the recorded task
  inputs differs from the current task inputs: number, position, or elements

If the task is still deemed up-to-date, there is one final check. Tasks
that reference files not explicitly listed in a fileset must supply as
'up-to-date' method. This method must be async to allow parallel execution.
If the task supplies an 'up-to-date' method, this method must be invoked
as final confirmation that the task is up-to-date. Note: the up-to-date
task is specified in the YAML in much the same way that a 'run' method
is specified. The up-to-date method must receive a context object like
the TaskRunCtxt to allow the method to run sub-processes 
(like the TaskRunCtxt 'exec' method).

The 'up-to-date' YAML entry supports one of three values:
- 'false' -- always run the task
- non-empty string -- Python method to evaluate
- empty string -- null case. Consider no up-to-date to have been provided.

## Runtime Behavior
Task up-to-date status is checked in the task runner. As each task 
becomes available to run, the runner must perform the checks above.
If the up-to-date method must be checked, the up-to-date method
must be scheduled using asyncio.

If a task is up-to-date, the previous output data is loaded from
its exec.json data.

## Listener
Task runners support listeners. When a task is determined to be
up-to-date, the listener must be informed that the task has been 
evaluated, and was determined to be up-to-date.

## CLI

A command-line option must be provided to force all tasks to be
evaluated (ie ignore up-to-date status).

By default, all CLI user interfaces (log, progress, etc) must 
only display not-up-to-date tasks. When verbose mode is enabled,
all tasks must be displayed. Up-to-date tasks must be marked as such.

---

# Implementation Plan

## Overview

This implementation adds incremental build support by tracking task execution
state and skipping tasks that are already up-to-date. The implementation
touches several layers: task definition/parsing, task execution, task runner,
CLI, and listeners.

## Phase 1: Exec Data File Enhancement

### 1.2 Add parameter hash to exec.json
- **File**: `src/dv_flow/mgr/task_node.py` (`_save_exec_data` method)
- **Change**: Save the value of parameters

### 1.3 Add input data signatures to exec.json
- **File**: `src/dv_flow/mgr/task_node.py` (`_save_exec_data` method)
- **Change**: Add `inputs_signature` field containing:
  - Number of input items
  - List of `(src, seq, type)` tuples for each input
- **Rationale**: Allows detecting if input structure changed

## Phase 2: TaskDef Schema Changes

### 2.1 Add `uptodate` field to TaskDef
- **File**: `src/dv_flow/mgr/task_def.py`
- **Change**: Add new field to `TaskDef` class:
  ```python
  uptodate : Union[bool, str, None] = dc.Field(
      default=None,
      description="Up-to-date check: false=always run, string=Python method, None=use default check")
  ```

## Phase 3: Up-to-date Check Infrastructure

### 3.1 Create UpToDateCtxt class
- **File**: Create new file `src/dv_flow/mgr/uptodate_ctxt.py`
- **Purpose**: Context passed to custom up-to-date methods
- **Contents**:
  ```python
  @dc.dataclass
  class UpToDateCtxt:
      rundir: str
      params: Any
      inputs: List[Any]
      exec_data: dict  # Previous exec.json contents
      
      async def exec(self, cmd: List[str], ...) -> int:
          """Run subprocess for dependency checking"""
  ```

### 3.2 Create uptodate_callable module
- **File**: Create new file `src/dv_flow/mgr/uptodate_callable.py`
- **Purpose**: Factory for creating up-to-date check callables (similar to `exec_callable.py`)
- **Implementation**: Load and invoke Python methods specified in `uptodate` field

### 3.3 Add up-to-date check function
- **File**: `src/dv_flow/mgr/task_node_leaf.py`
- **Change**: Add new async method `_check_uptodate`:
  ```python
  async def _check_uptodate(self, rundir: str, inputs: List[Any]) -> Tuple[bool, Optional[dict]]:
      """
      Returns (is_uptodate, exec_data) tuple.
      exec_data is loaded from exec.json if uptodate, None otherwise.
      """
  ```
- **Logic**:
  1. Check if `exec.json` exists in rundir → if not, return `(False, None)`
     Note: this file still retains its name that incorporates the task name
  2. Load exec.json
  3. Compare parameter values and return (False,None) if different
  4. Compare `inputs_signature` → if different, return `(False, None)`
  5. Check if any input has `changed=True` → if so, return `(False, None)`
  6. If custom `uptodate` method specified:
     - If `uptodate == False`, return `(False, None)`
     - If string, invoke the method and return its result
  7. Return `(True, exec_data)`

## Phase 4: Task Runner Integration

### 4.1 Add force_run option to TaskSetRunner
- **File**: `src/dv_flow/mgr/task_runner.py`
- **Change**: Add `force_run: bool = False` field to `TaskSetRunner`
- **Purpose**: Allow bypassing up-to-date checks

### 4.2 Integrate up-to-date check into task execution
- **File**: `src/dv_flow/mgr/task_node_leaf.py` (`_do_run` method)
- **Change**: Before calling task implementation:
  1. Call `_check_uptodate()`
  2. If up-to-date and not `force_run`:
     - Load output from exec.json
     - Set `self.result.changed = False`
     - Skip task implementation call
     - Return early
  3. If not up-to-date, proceed with normal execution

### 4.3 Update TaskNodeCompound for up-to-date support
- **File**: `src/dv_flow/mgr/task_node_compound.py`
- **Change**: Add similar up-to-date check logic for compound tasks
- **Note**: Compound tasks are up-to-date if all their subtasks are up-to-date

### 4.4 Propagate force_run through runner
- **File**: `src/dv_flow/mgr/task_runner.py`
- **Change**: Pass `force_run` to task nodes via `do_run` parameters or context

## Phase 5: Listener Updates

### 5.1 Add `skipped` event reason
- **File**: `src/dv_flow/mgr/task_listener_log.py`
- **Change**: Handle new `'skipped'` reason in `event()` method
- **Display**: Show "(up-to-date)" or "(skipped)" indicator

### 5.2 Update TaskListenerProgress
- **File**: `src/dv_flow/mgr/task_listener_progress.py`
- **Change**: Handle skipped tasks in progress display

### 5.3 Update TaskListenerTui
- **File**: `src/dv_flow/mgr/task_listener_tui.py`
- **Change**: Handle skipped tasks in TUI display

### 5.4 Update TaskListenerTrace
- **File**: `src/dv_flow/mgr/task_listener_trace.py`
- **Change**: Add `skipped: true` to trace events for up-to-date tasks

### 5.5 Add verbose mode to listeners
- **Files**: All listener files
- **Change**: Add `verbose: bool` parameter
- **Behavior**: When `verbose=False` (default), skip displaying up-to-date tasks

## Phase 6: CLI Updates

### 6.1 Add `--force` / `-f` option to run command
- **File**: `src/dv_flow/mgr/__main__.py`
- **Change**: Add argument to `run_parser`:
  ```python
  run_parser.add_argument("-f", "--force",
      action="store_true",
      help="Force all tasks to run, ignoring up-to-date status")
  ```

### 6.2 Add `--verbose` / `-v` option to run command
- **File**: `src/dv_flow/mgr/__main__.py`
- **Change**: Add argument:
  ```python
  run_parser.add_argument("-v", "--verbose",
      action="store_true",
      help="Show all tasks including up-to-date ones")
  ```

### 6.3 Wire CLI options to runner
- **File**: `src/dv_flow/mgr/cmds/cmd_run.py`
- **Change**: Pass `force_run=args.force` to `TaskSetRunner`
- **Change**: Pass `verbose=args.verbose` to listener constructor

## Phase 7: Documentation Updates

### 7.1 Update cmdref.rst
- **File**: `docs/cmdref.rst`
- **Change**: Document new `--force` and `--verbose` options
- **Note**: argparse autodoc should pick these up automatically

### 7.2 Update pytask_api.rst
- **File**: `docs/pytask_api.rst`
- **Change**: Add section on implementing custom `uptodate` methods
- **Content**:
  - Signature: `async def check_uptodate(ctxt: UpToDateCtxt) -> bool`
  - Document `UpToDateCtxt` class and its methods
  - Provide example use case (e.g., checking file timestamps)

### 7.3 Add uptodate examples
- **File**: `docs/Tasks.md` or new `docs/Incremental.md`
- **Content**: Examples of using `uptodate` field in task definitions

## Phase 8: Testing

### 8.1 Unit tests for up-to-date checking
- **File**: Create `tests/unit/test_uptodate.py`
- **Tests**:
  - Task runs on first execution
  - Task skipped when parameters unchanged
  - Task runs when parameters change
  - Task runs when input data changes
  - Task runs when `uptodate: false`
  - Custom `uptodate` method is called
  - `--force` flag bypasses up-to-date check

### 8.2 Integration tests
- **File**: Extend `tests/unit/test_deps.py`
- **Tests**:
  - Multi-task graph with incremental updates
  - Compound task up-to-date behavior
  - Listener receives correct events

## Implementation Order

1. **Phase 1** - Exec data file enhancement (foundation)
2. **Phase 2** - TaskDef schema changes (required for custom uptodate)
3. **Phase 3** - Up-to-date check infrastructure (core logic)
4. **Phase 4** - Task runner integration (wire it together)
5. **Phase 5** - Listener updates (user visibility)
6. **Phase 6** - CLI updates (user control)
7. **Phase 7** - Documentation (user guidance)
8. **Phase 8** - Testing (validation)

## Key Files Summary

| File | Changes |
|------|---------|
| `task_node.py` | `_save_exec_data` enhancements, `_check_uptodate` method |
| `task_node_leaf.py` | Up-to-date check integration in `_do_run` |
| `task_node_compound.py` | Up-to-date check for compound tasks |
| `task_def.py` | Add `uptodate` field |
| `task_runner.py` | Add `force_run` field, propagate to tasks |
| `task_listener_*.py` | Handle skipped tasks, verbose mode |
| `__main__.py` | Add `--force` and `--verbose` CLI options |
| `cmd_run.py` | Wire CLI options to runner/listeners |
| `uptodate_ctxt.py` | New file - context for custom methods |
| `uptodate_callable.py` | New file - callable factory |

## Risks and Mitigations

1. **Risk**: Parameter serialization may be non-deterministic
   - **Mitigation**: Use `model_dump_json(sort_keys=True)` for consistent hashing

2. **Risk**: Large exec.json files for tasks with many outputs
   - **Mitigation**: Consider storing only signatures/hashes of outputs

3. **Risk**: File system race conditions on exec.json
   - **Mitigation**: Use atomic writes (write to temp, then rename)

4. **Risk**: Breaking existing workflows
   - **Mitigation**: Default behavior matches current (always run), opt-in via exec.json existence



