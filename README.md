# DV Flow Manager

DV Flow Manager (dfm) orchestrates data-driven, parameterizable workflows. 
Tasks are connected by dataflow, enabling composable and reusable workflow definitions.

Originally designed for silicon design and verification, DV Flow supports any 
domain requiring complex task orchestration—including agentic AI workflows, 
build automation, and CI/CD pipelines.

## Features

- **Package-based organization** - Projects are encapsulated as packages with public and private flows
- **Type inheritance** - Packages, flows, and subflows support inheritance and extension
- **Fileset dependency tracking** - Maintains dependency trees for proper file ordering
- **Flexible UI** - Progress spinner or log-based output modes
- **Task-artifact caching** - Cache task results for instant reruns
- **AI Agent Integration** - Launch AI assistants with project-specific context, skills, and personas

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

## AI Agent Integration

Launch AI assistants (GitHub Copilot CLI, Codex) with project-specific context:

```bash
# Define a persona in your flow.yaml
tasks:
  - name: DevAssistant
    uses: std.AgentPersona
    desc: |
      I am a helpful development assistant with expertise
      in this project.

# Launch the agent
dfm agent DevAssistant
```

The agent command automatically:
- Evaluates tasks and dependencies
- Collects skills, personas, tools, and references
- Generates comprehensive system prompts
- Launches your AI assistant with full project context

See [docs/userguide/agent_integration.rst](docs/userguide/agent_integration.rst) for detailed documentation and [examples/agent_demo/](examples/agent_demo/) for working examples.

## Documentation

- [AI Agent Integration](docs/userguide/agent_integration.rst) - Launch AI assistants with DFM context
- [Cache Documentation](docs/cache.md) - Task-artifact caching guide
- [Quick Start](docs/quickstart.rst) - Getting started tutorial
- [Command Reference](docs/cmdref.rst) - All available commands
- [Example Workflows](examples/agent_demo/) - AI agent integration examples

## License

Apache License 2.0

