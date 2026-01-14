
# Task Visibility

Tasks can control their visibility using the `scope` attribute. This allows package authors to:
- Mark which tasks are intended as entry points
- Control which tasks are visible across package boundaries
- Hide implementation details within fragments

## Visibility Scopes

### root
Tasks marked with `scope: root` are executable entry points. When the `run` command is invoked without specifying a task, only root tasks are listed.

```yaml
tasks:
- name: build
  scope: root
  desc: "Build the project"
  run: make build
```

### export
Tasks marked with `scope: export` are visible outside the package. Other packages can reference these tasks in their `needs` lists.

```yaml
tasks:
- name: compile
  scope: export
  run: gcc -o output main.c
```

### local
Tasks marked with `scope: local` are only visible within their declaration fragment (e.g., within a task body or fragment file).

```yaml
tasks:
- name: parent
  body:
  - name: helper
    scope: local
    run: echo "internal helper"
  - name: child
    needs: [helper]  # OK - within same fragment
```

### Default (no scope)
Tasks without a scope specifier are visible within the package where they are declared. They can be referenced by other tasks in the same package, but not from outside the package.

```yaml
tasks:
- name: internal_task
  run: echo "package-visible only"
```

## Combining Scopes

Multiple scopes can be specified as a list:

```yaml
tasks:
- name: public_entry
  scope: [root, export]
  desc: "Public entry point"
  run: ./run.sh
```

## Visibility Enforcement

The package loader issues a **warning** when a task references a task in another package that is not marked `export`. This helps identify potential API boundaries and dependencies.

Example warning:
```
Warning: Task 'myapp.main' references task 'utils.internal_helper' in package 'utils' that is not marked 'export'
```

## Task Listing Behavior

When the `run` command is invoked without specifying a task:
- Only tasks with `scope: root` are displayed
- Tasks without scope are not shown (they are internal to the package)
- This provides a clean list of intended entry points

```bash
$ dv-flow run
No task specified. Available Tasks:
build       - Build the project
test        - Run tests
deploy      - Deploy to production
```

## Schema Updates

The task definition schema now includes:

```json
{
  "scope": {
    "oneOf": [
      {
        "type": "string",
        "enum": ["root", "export", "local"]
      },
      {
        "type": "array",
        "items": {
          "type": "string",
          "enum": ["root", "export", "local"]
        }
      }
    ]
  }
}
```

## Implementation Details

Tasks have three boolean flags:
- `is_root`: Task is an executable entry point
- `is_export`: Task is visible outside the package
- `is_local`: Task is only visible within its declaration fragment

The schema and data model support specifying scope, and visibility flags are set during task elaboration. The run command filters tasks by the `is_root` flag when no task is specified. 
