###############
LLM Integration
###############

This guide explains how to enable and optimize LLM (Large Language Model) agent 
support in your DV Flow Manager projects. With proper configuration, AI assistants
like GitHub Copilot CLI, Claude, and OpenAI Codex can effectively discover, 
understand, and generate DFM flows for your projects.

Overview
========

DV Flow Manager provides built-in support for LLM agent integration through:

1. **Skill Discovery** - The ``dfm show skills`` command lists available agent skills
2. **JSON Output** - Machine-readable output for programmatic consumption
3. **Skill Documentation** - Detailed capability documentation accessible to agents
4. **AGENTS.md** - Project-level documentation for AI assistants

Why Enable LLM Support?
-----------------------

Enabling LLM support in your project allows AI assistants to:

* Automatically discover your project's build capabilities
* Generate correct flow.yaml/flow.yaml configurations
* Understand task dependencies and dataflow patterns
* Debug and modify existing flows with minimal hallucination
* Execute builds and simulations via the CLI

Creating AGENTS.md
==================

The recommended way to enable LLM support is to create an ``AGENTS.md`` file in 
your project root. This file is automatically discovered by AI assistants.

Recommended Template
--------------------

.. code-block:: markdown

    # Project Name

    Brief description of what this project does.

    ## DV Flow Manager

    This project uses DV Flow Manager (dfm) for build automation.

    ### Getting Started

    ```bash
    # Get DFM documentation path
    dfm --help

    # List available package capabilities  
    dfm show skills

    # List available tasks
    dfm show tasks

    # Show project structure
    dfm show project --json
    ```

    ### Skill Documentation

    Run `dfm --help` to get the absolute path to the comprehensive skill.md 
    documentation file.

    ## Project Structure

    ```
    project-root/
    ├── flow.yaml          # Main flow definition
    ├── AGENTS.md          # This file
    ├── src/
    │   └── rtl/           # RTL source files
    └── tb/                # Testbench files
    ```

    ## Key Tasks

    | Task | Description | Usage |
    |------|-------------|-------|
    | `build` | Compile RTL and testbench | `dfm run build` |
    | `sim` | Run simulation | `dfm run sim` |
    | `test` | Run all tests | `dfm run test` |

    ## Configurations

    | Config | Description | Usage |
    |--------|-------------|-------|
    | `debug` | Debug build with tracing | `dfm run build -c debug` |
    | `release` | Optimized build | `dfm run build -c release` |

    ## Common Workflows

    ### Build and Run Simulation

    ```bash
    dfm run sim
    ```

    ### Run Specific Test

    ```bash
    dfm run test -D test_name=smoke_test
    ```

    ## Package Dependencies

    This project uses the following DFM packages:

    - `hdlsim.vlt` - Verilator simulation support

    To discover capabilities of these packages:

    ```bash
    dfm show skills --package hdlsim.vlt
    dfm show tasks --package hdlsim.vlt
    ```

Best Practices
--------------

1. **Keep it Concise** - LLM context windows are limited, so focus on essential information
2. **Include Examples** - Show common command patterns and task usage
3. **Document Configurations** - List available configurations and their purposes
4. **Reference dfm Commands** - Point agents to ``dfm show`` commands for detailed info

Defining Custom Skills
======================

For packages that want to expose their capabilities to LLM agents, define skills 
as DataSet types tagged with ``std.AgentSkillTag``.

Basic Skill Definition
----------------------

.. code-block:: yaml

    package:
      name: my_package

      types:
        # Default skill for the package (recommended name: AgentSkill)
        - name: AgentSkill
          uses: std.DataSet
          tags:
            - std.AgentSkillTag
          doc: My package agent skill
          with:
            name:
              type: str
              value: "my-package-skill"
            desc:
              type: str
              value: "Build and test MyPackage components"
            skill_doc:
              type: str
              value: |
                # MyPackage Skill

                ## Quick Start
                ```yaml
                imports:
                  - name: my_package
                    as: mp
                tasks:
                  - name: build
                    uses: mp.Build
                    with:
                      target: [my_module]
                ```

                ## Available Tasks
                - `Build` - Compiles the design
                - `Test` - Runs test suite
                - `Lint` - Code linting

Skill Fields
------------

The ``std.AgentSkill`` type supports the following fields:

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Field
     - Type
     - Description
   * - ``name``
     - str
     - Unique skill identifier (e.g., "hdl-simulation")
   * - ``desc``
     - str
     - One-line description for listing
   * - ``skill_doc``
     - str
     - Full markdown documentation with examples
   * - ``examples``
     - list
     - List of YAML example snippets
   * - ``related_tasks``
     - list
     - List of related task names
   * - ``path``
     - str
     - Optional path to detailed documentation file

Discovering Skills
==================

Use the ``dfm show skills`` command to discover available skills:

.. code-block:: bash

    # List all skills
    dfm show skills

    # Filter by package
    dfm show skills --package hdlsim.vlt

    # Search by keyword
    dfm show skills --search verilator

    # Show full documentation for a specific skill
    dfm show skills hdlsim.vlt.AgentSkill --full

    # JSON output for programmatic use
    dfm show skills --json

Verifying Agent Compatibility
=============================

To verify your project is properly configured for LLM agents:

1. **Check skill discovery**:

   .. code-block:: bash

       dfm show skills

2. **Verify JSON output**:

   .. code-block:: bash

       dfm show project --json
       dfm show tasks --json

3. **Test agent workflow**:

   Try the sequence of commands an agent would use:

   .. code-block:: bash

       dfm --help                    # Get skill.md path
       dfm show skills              # Discover capabilities
       dfm show tasks --package std # List available tasks
       dfm show task std.FileSet    # Get task details

Example: Complete Project Setup
===============================

Here's a complete example of a project with LLM support enabled:

Project Structure
-----------------

.. code-block:: text

    my_project/
    ├── AGENTS.md           # Agent documentation
    ├── flow.yaml             # Main flow definition
    ├── src/
    │   └── rtl/
    │       └── counter.sv
    └── tb/
        └── counter_tb.sv

flow.yaml
-------

.. code-block:: yaml

    package:
      name: my_project

      types:
        # Custom project skill
        - name: AgentSkill
          uses: std.DataItem
          tags:
            - std.AgentSkillTag
          with:
            name:
              type: str
              value: "my-project-build"
            desc:
              type: str
              value: "Build and simulate the counter design"
            skill_doc:
              type: str
              value: |
                # Counter Project
                
                ## Quick Start
                ```bash
                dfm run sim     # Build and run simulation
                dfm run test    # Run tests
                ```
                
                ## Tasks
                - `rtl` - RTL source files
                - `tb` - Testbench files  
                - `build` - Compile simulation
                - `sim` - Run simulation

      tasks:
        - name: rtl
          uses: std.FileSet
          with:
            base: src/rtl
            type: systemVerilogSource
            include: "*.sv"

        - name: tb
          uses: std.FileSet
          needs: [rtl]
          with:
            base: tb
            type: systemVerilogSource
            include: "*.sv"

        - name: build
          uses: hdlsim.vlt.SimImage
          needs: [rtl, tb]
          with:
            top: [counter_tb]

        - name: sim
          uses: hdlsim.vlt.SimRun
          needs: [build]

AGENTS.md
---------

.. code-block:: markdown

    # Counter Project

    A simple counter design with Verilator simulation.

    ## Quick Start

    ```bash
    dfm run sim    # Build and run simulation
    ```

    ## Tasks

    | Task | Description |
    |------|-------------|
    | `build` | Compile counter RTL and testbench |
    | `sim` | Run simulation |

    ## DFM Commands

    ```bash
    dfm show skills           # List project capabilities
    dfm show tasks            # List available tasks
    dfm show project --json   # Get project structure
    ```
