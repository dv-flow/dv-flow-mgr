# Task Visibility Example

This example demonstrates the task visibility features.

## Package Structure

```
example/
├── flow.yaml          # Main package
└── utils/
    └── flow.yaml      # Utility package
```

## Utils Package (utils/flow.yaml)

```yaml
package:
  name: utils
  
  tasks:
  # Public API task - visible to other packages
  - name: format
    scope: [root, export]
    desc: "Format source files"
    run: echo "Formatting files..."
  
  # Internal helper - not visible outside package
  - name: check_syntax
    run: echo "Checking syntax..."
  
  # Private implementation detail
  - name: backup_files
    scope: local
    run: echo "Backing up files..."
```

## Main Package (flow.yaml)

```yaml
package:
  name: myapp
  imports:
  - utils/flow.yaml
  
  tasks:
  # Entry point - listed when running without task name
  - name: build
    scope: root
    desc: "Build the application"
    needs:
    - utils.format  # OK - format is marked export
    - compile
    run: echo "Building application..."
  
  # Another entry point
  - name: test
    scope: root
    desc: "Run tests"
    run: echo "Running tests..."
  
  # Internal task - not listed but can be run directly
  - name: compile
    run: echo "Compiling..."
  
  # This would generate a warning (check_syntax not marked export)
  # - name: validate
  #   needs:
  #   - utils.check_syntax
```

## Usage

### List available tasks (only root tasks shown)
```bash
$ dv-flow run
No task specified. Available Tasks:
myapp.build  - Build the application
myapp.test   - Run tests
utils.format - Format source files
```

### Run a specific task (any task can be run)
```bash
$ dv-flow run build
# Runs: utils.format -> compile -> build

$ dv-flow run compile
# Runs: compile (even though not marked root)
```

### Cross-package references
```yaml
# OK - utils.format is marked export
- needs: [utils.format]

# WARNING - utils.check_syntax not marked export
- needs: [utils.check_syntax]
# Warning: Task 'myapp.validate' references task 'utils.check_syntax' 
# in package 'utils' that is not marked 'export'
```

## Scope Combinations

```yaml
tasks:
# Just an entry point (not visible outside package)
- name: local_entry
  scope: root
  run: ...

# Public API but not an entry point
- name: library_function
  scope: export
  run: ...

# Both entry point and public API
- name: main
  scope: [root, export]
  run: ...

# Default - visible within package only
- name: helper
  run: ...
```
