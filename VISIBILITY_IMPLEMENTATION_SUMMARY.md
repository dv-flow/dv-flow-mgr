# Task Visibility Implementation Summary

## Overview
Implemented task visibility control scheme as specified in `docs/visibility.md`. Tasks can now be marked with visibility scopes to control their accessibility and listing behavior.

## Changes Made

### 1. Schema Updates (`schema/flow.dv.schema.json`)
- Added `scope` property to `task-def` definition
- Accepts string or array of strings: `["root", "export", "local"]`
- Validates scope values at schema level

### 2. Data Model Updates

#### TaskDef (`src/dv_flow/mgr/task_def.py`)
- Added `scope` field (Union[str, List[str], None])
- Field accepts single scope or list of scopes
- Default is None (package-visible)

#### Task (`src/dv_flow/mgr/task.py`)
- Added three boolean flags:
  - `is_root`: Task is an executable entry point
  - `is_export`: Task is visible outside the package
  - `is_local`: Task is only visible within its declaration fragment
- Default values are False

### 3. Package Loader Updates (`src/dv_flow/mgr/package_provider_yaml.py`)

#### Task Loading (`_loadTasks` method)
- Process scope attribute from TaskDef
- Set visibility flags (is_root, is_export, is_local) on Task objects
- Applied to both top-level tasks and subtasks

#### Subtask Creation (`_mkTaskBody` method)
- Process scope for subtasks created within task bodies
- Ensures visibility flags are set consistently

#### Task Elaboration (`_elabTask` method)
- Added visibility check when resolving task dependencies
- Issues warning if task references non-export task from another package
- Warning includes task names, package names, and source location

#### Alias Creation (base package inheritance)
- Copy visibility flags when creating task aliases from base packages
- Ensures inherited tasks maintain their visibility scope

### 4. Run Command Updates (`src/dv_flow/mgr/cmds/cmd_run.py`)
- Modified task listing to show only `is_root` tasks when no task specified
- Provides clean list of intended entry points
- Non-root tasks remain executable but aren't listed

### 5. Tests (`tests/unit/test_visibility.py`)
Created comprehensive test suite covering:
- Root scope filtering in task listings
- Export scope visibility across packages
- Local scope visibility within fragments
- Scope as string vs. list
- Default behavior (no scope specified)
- Task execution not affected by visibility
- Cross-package reference warnings

### 6. Updated Existing Tests
- `test_load_package.py`: Updated `test_dup_import` and `test_dup_import_subpkg` to expect warnings for non-export task references
- `test_run_task_listing_overrides.py`: Added `scope: root` to tasks that should appear in listings

## Behavior

### Task Visibility Rules
1. **root**: Listed in `run` command when no task specified; marks entry points
2. **export**: Visible to other packages; can be referenced in their needs lists
3. **local**: Only visible within declaration fragment
4. **No scope**: Visible within package only (default)

### Warnings
The loader issues a warning (not an error) when:
- A task references a task from another package
- AND that referenced task is not marked with `scope: export`

This is a soft enforcement - the task graph still builds, but users are informed of potential API boundary violations.

### Backward Compatibility
- Existing tasks without scope continue to work
- They are package-visible but not listed as root tasks
- To appear in task listings, add `scope: root`

## Testing Results
- All 172 unit tests pass
- 7 new visibility-specific tests added
- 2 existing tests updated to handle new warnings
- Tests cover all visibility scenarios and edge cases

## Documentation
Updated `docs/visibility.md` with:
- Complete visibility scheme documentation
- Usage examples for each scope type
- Combining scopes example
- Schema reference
- Implementation details
- Task listing behavior explanation
