# DV Flow Manager CLI Reference

## Commands Overview

```
dfm [OPTIONS] COMMAND [ARGS]
```

Global options:
- `--log-level {NONE,INFO,DEBUG}` - Set logging level
- `-D NAME=VALUE` - Parameter override (can be repeated)

## dfm run

Execute one or more tasks.

### Usage

```bash
dfm run [OPTIONS] [TASKS...]
```

If no tasks specified, lists available tasks.

### Options

| Option | Description |
|--------|-------------|
| `-j N` | Parallel jobs (default: all cores) |
| `--clean` | Clean rundir before running |
| `-f, --force` | Force all tasks to run |
| `-v, --verbose` | Show all tasks including up-to-date |
| `--root PATH` | Root directory for flow |
| `-c, --config NAME` | Select configuration |
| `-u, --ui {log,progress,tui}` | UI mode |
| `-D NAME=VALUE` | Parameter override |

### Examples

```bash
# Run single task
dfm run sim-image

# Run multiple tasks
dfm run compile test lint

# Parallel with 4 jobs
dfm run build -j 4

# Force clean rebuild
dfm run build --clean -f

# Use debug configuration
dfm run build -c debug

# Override parameters
dfm run build -D debug=true -D opt_level=0

# Use specific root directory
dfm run build --root /path/to/project

# Log mode for CI
dfm run build -u log

# TUI mode for monitoring
dfm run build -u tui
```

## dfm show

Discovery and inspection of packages, tasks, types, and tags.
Supports both human-readable and JSON output for Agent consumption.

### Sub-Commands

| Command | Description |
|---------|-------------|
| `show packages` | List and search available packages |
| `show tasks` | List and search tasks |
| `show task <name>` | Detailed task information |
| `show types` | List data types |
| `show tags` | List tag types and usage |
| `show package <name>` | Detailed package information |
| `show project` | Current project structure |

### Common Options

| Option | Description |
|--------|-------------|
| `--search KEYWORD` | Search by keyword in name/desc/doc |
| `--regex PATTERN` | Search by regex pattern |
| `--tag TAG` | Filter by tag |
| `--json` | JSON output for Agents |
| `-v, --verbose` | Show additional details |
| `-c, --config NAME` | Select configuration |
| `-D NAME=VALUE` | Parameter override |

### dfm show packages

List and search available packages.

```bash
# List all packages
dfm show packages

# Search packages
dfm show packages --search verification

# JSON output
dfm show packages --json
```

### dfm show tasks

List and search tasks across packages.

```bash
# List all tasks
dfm show tasks

# Search by keyword
dfm show tasks --search file

# Filter by package
dfm show tasks --package std

# Filter by scope
dfm show tasks --scope root

# JSON output
dfm show tasks --json
```

### dfm show task <name>

Display detailed information about a specific task.

```bash
# Show task details
dfm show task std.FileSet

# Show with full needs chain
dfm show task myproject.build --needs

# Show needs chain limited to 2 levels
dfm show task myproject.build --needs 2

# JSON output
dfm show task std.FileSet --json
```

### dfm show types

List data types and tag types.

```bash
# List all types
dfm show types

# Show only tags
dfm show types --tags-only

# Show only data items
dfm show types --data-items-only
```

### dfm show tags

List tag types and their usage counts.

```bash
dfm show tags
dfm show tags --json
```

### dfm show package <name>

Display detailed information about a package.

```bash
dfm show package std
dfm show package std --json -v
```

### dfm show project

Display current project structure.

```bash
# Basic project info
dfm show project

# With imports and configs
dfm show project --imports --configs

# JSON output
dfm show project --json
```

### Legacy Mode

For backward compatibility:

```bash
# List project tasks
dfm show

# Show task dependencies (legacy)
dfm show <task> -a
```

## dfm graph

Generate task dependency graph.

### Usage

```bash
dfm graph [OPTIONS] [TASK]
```

### Options

| Option | Description |
|--------|-------------|
| `-f, --format {dot}` | Output format (default: dot) |
| `-o, --output FILE` | Output file (default: stdout) |
| `--root PATH` | Root directory for flow |
| `-c, --config NAME` | Select configuration |
| `-D NAME=VALUE` | Parameter override |
| `--show-params` | Show parameters in node labels |

### Examples

```bash
# Generate DOT graph to stdout
dfm graph build

# Save to file
dfm graph build -o build.dot

# Generate and view with GraphViz
dfm graph build -o build.dot && dot -Tpng build.dot -o build.png

# One-liner with display
dfm graph build | dot -Tpng | display
```

## dfm cache

Cache management commands.

### Usage

```bash
dfm cache SUBCOMMAND [OPTIONS]
```

### Subcommands

#### dfm cache init

Initialize a cache directory.

```bash
dfm cache init [OPTIONS] CACHE_DIR
```

Options:
- `--shared` - Create shared cache with group permissions

Examples:
```bash
# Initialize local cache
dfm cache init .cache

# Initialize shared team cache
dfm cache init --shared /shared/cache/dfm
```

## dfm skill

Display skill information for LLM consumption.

### Usage

```bash
dfm skill
```

Displays a short description of DV Flow Manager and path to detailed skill documentation.

## UI Modes

### log

Plain text output, best for:
- CI/CD pipelines
- Log file capture
- Non-interactive environments

Output format:
```
>> [1] Task my_pkg.compile
Compiling 10 files...
<< [1] Task my_pkg.compile (success) 2.45s
```

### progress

Live progress bars, best for:
- Interactive terminals
- Monitoring long builds
- Parallel visualization

### tui

Full-screen TUI, best for:
- Complex flows
- Detailed monitoring
- Interactive navigation

## Parameter Overrides

Override parameters from command line using `-D`:

```bash
# Boolean
dfm run build -D debug=true

# Integer
dfm run build -D opt_level=3

# String
dfm run build -D mode=release

# Multiple overrides
dfm run build -D debug=true -D trace=true -D seed=42
```

## Configuration Selection

Select package configuration with `-c`:

```bash
# Use 'debug' configuration
dfm run build -c debug

# Use 'release' configuration
dfm run build -c release
```

Configuration in flow.yaml:
```yaml
package:
  name: my_pkg
  
  configs:
    - name: debug
      with:
        debug:
          value: true
    - name: release
      with:
        debug:
          value: false
```

## Common Patterns

### Quick Incremental Build

```bash
dfm run
```

### Clean Release Build

```bash
dfm run all --clean -c release
```

### Debug Single Task

```bash
dfm run problem_task -f -j 1 -u log
```

### Monitor Long Build

```bash
dfm run all -u tui
```

### Check What Would Run

```bash
dfm show target_task -a
```

### CI/CD Pipeline

```bash
dfm run test --clean -u log -c ci
```

### Generate Documentation

```bash
dfm graph all -o project.dot
dot -Tsvg project.dot -o project.svg
```

## Execution Traces

DFM automatically generates execution traces in Google Event Trace format.

Location: `rundir/log/<task>.trace.json`

View with:
1. **Perfetto**: https://ui.perfetto.dev/
2. **Chrome**: chrome://tracing

Traces show:
- Task execution timeline
- Parallel execution
- Task duration
- Dependencies and dataflow
- Status and results

## Output Directory Structure

```
rundir/
├── cache/                  # Task mementos
├── log/                    # Execution traces
│   └── <task>.trace.json
├── <task>/                 # Task output directory
│   ├── <task>.exec_data.json  # Task execution data
│   └── ...                 # Task-specific outputs
└── <compound_task>/
    └── <subtask>/
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Task failure |
| 2 | Configuration error |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DFM_ROOT` | Default root directory |
| `DFM_CONFIG` | Default configuration |
| `DFM_CACHE_DIR` | Cache directory location |
