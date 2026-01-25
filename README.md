# DV Flow Manager

DV Flow Manager (dfm) is a flow manager designed for hardware design and verification projects. 
It orchestrates tasks connected by data objects, managing dependencies between filesets to 
enable proper ordering and intelligent partitioning.

## Features

- **Package-based organization** - Projects are encapsulated as packages with public and private flows
- **Type inheritance** - Packages, flows, and subflows support inheritance and extension
- **Fileset dependency tracking** - Maintains dependency trees for proper file ordering
- **Flexible UI** - Progress spinner or log-based output modes
- **Task-artifact caching** - Cache task results for instant reruns (NEW!)

## Quick Start

### Installation

Install via pip:

```bash
% pip install dv-flow-mgr
```

### Example Flow

Create a `flow.yaml` file:

```yaml
package:
  name: hello

  tasks:
    - name: greet
      uses: std.Message
      with:
        msg: "Hello World"
```

### Running Flows

Run the flow using the `dfm run` command:

```bash
% dfm run greet
```

## Task Caching

Speed up your workflows with intelligent caching:

### Setup Cache

```bash
# Initialize cache
dfm cache init ~/.cache/dv-flow

# Enable caching
export DV_FLOW_CACHE=~/.cache/dv-flow
```

### Enable in Tasks

```yaml
tasks:
  - name: build
    run: make all
    cache: true  # Cache results for instant reruns
```

**Benefits:**
- 10-100x faster for cached tasks
- Automatic invalidation on input changes
- Team cache sharing support
- Compression options for large artifacts

See [docs/cache.md](docs/cache.md) for comprehensive caching documentation.

## Documentation

- [Cache Documentation](docs/cache.md) - Task-artifact caching guide
- [Quick Start](docs/quickstart.rst) - Getting started tutorial
- [Command Reference](docs/cmdref.rst) - All available commands

## License

Apache License 2.0

