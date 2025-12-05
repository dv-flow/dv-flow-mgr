# DV Flow Manager

DV Flow Manager (dfm) is a flow manager designed for hardware design and verification projects. 
It orchestrates tasks connected by data objects, managing dependencies between filesets to 
enable proper ordering and intelligent partitioning.

## Features

- **Package-based organization** - Projects are encapsulated as packages with public and private flows
- **Type inheritance** - Packages, flows, and subflows support inheritance and extension
- **Fileset dependency tracking** - Maintains dependency trees for proper file ordering
- **Flexible UI** - Progress spinner or log-based output modes

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
      type: std.Message
      with:
        msg: "Hello World"
```

### Running Flows

Run the flow using the `dfm run` command:

```bash
% dfm run greet
```
