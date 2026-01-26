#####################
LLM Agent Integration
#####################

DV Flow Manager provides built-in support for Large Language Model (LLM) agents,
enabling AI assistants to discover, understand, and work with DFM flows effectively.

Overview
========

The goal of LLM integration is to enable AI agents to:

1. **Discover** available DFM capabilities, packages, tasks, and types
2. **Understand** DFM's dataflow-based build system paradigm
3. **Generate** correct flow.yaml/flow.yaml configurations
4. **Debug** and **modify** existing flows with minimal hallucination
5. **Execute** builds and simulations via the dfm CLI
6. **Run tasks dynamically** from within LLM-driven Prompt tasks

The ``dfm --help`` Output
=========================

The ``dfm --help`` command displays a short description of DFM and an absolute
path to the root skill.md file. This enables LLM agents to immediately locate
the comprehensive documentation:

.. code-block:: bash

    $ dfm --help
    usage: dfm [-h] [--log-level {NONE,INFO,DEBUG}] [-D NAME=VALUE] {graph,run,show,...} ...

    DV Flow Manager (dfm) - A dataflow-based build system for silicon design and verification.

    positional arguments:
      {graph,run,show,...}
        graph               Generates the graph of a task
        run                 run a flow
        show                Display and search packages, tasks, types, and tags
        ...

    options:
      -h, --help            show this help message and exit
      --log-level {NONE,INFO,DEBUG}
                            Configures debug level [INFO, DEBUG]
      -D NAME=VALUE         Parameter override; may be used multiple times

    For LLM agents: See the skill file at: /absolute/path/to/site-packages/dv_flow/mgr/share/skill.md

The skill path is always an absolute path to ensure LLM agents can reliably
locate and read the file regardless of the current working directory.

The ``dfm show skills`` Command
===============================

The ``dfm show skills`` command lists and queries skills defined as DataSet types
tagged with ``std.AgentSkillTag``. This provides programmatic access to package
capabilities for LLM agents.

Basic Usage
-----------

.. code-block:: bash

    # List all skills from loaded packages
    dfm show skills

    # JSON output for programmatic use
    dfm show skills --json

    # Filter by package
    dfm show skills --package hdlsim.vlt

    # Show full skill documentation for a specific skill
    dfm show skills hdlsim.vlt.AgentSkill --full

    # Search skills by keyword
    dfm show skills --search verilator

Example Output
--------------

.. code-block:: bash

    $ dfm show skills
    hdlsim.AgentSkill              - Configure and run HDL simulations with various simulators
    hdlsim.vlt.AgentSkill          - Compile and run simulations with Verilator
    hdlsim.vlt.VerilatorTraceSkill - Configure FST/VCD waveform tracing in Verilator
    hdlsim.vcs.AgentSkill          - Compile and run simulations with Synopsys VCS

    $ dfm show skills --json
    {
      "skills": [
        {
          "name": "hdlsim.AgentSkill",
          "package": "hdlsim",
          "skill_name": "hdl-simulation",
          "desc": "Configure and run HDL simulations with various simulators",
          "is_default": true
        },
        {
          "name": "hdlsim.vlt.AgentSkill",
          "package": "hdlsim.vlt",
          "skill_name": "verilator-simulation",
          "desc": "Compile and run simulations with Verilator",
          "is_default": true
        }
      ]
    }

Skill Definition
----------------

Skills are defined as DataSet types tagged with ``std.AgentSkillTag``:

.. code-block:: yaml

    package:
      name: hdlsim.vlt

      types:
        - name: AgentSkill
          uses: std.DataSet
          tags:
            - std.AgentSkillTag
          with:
            name:
              type: str
              value: "verilator-simulation"
            desc:
              type: str
              value: "Compile and run simulations with Verilator"
            skill_doc:
              type: str
              value: |
                # Verilator Simulation
                
                ## Quick Start
                ```yaml
                imports:
                  - name: hdlsim.vlt
                    as: sim
                tasks:
                  - name: build
                    uses: sim.SimImage
                    needs: [rtl]
                    with:
                      top: [my_module]
                ```

LLM Call Interface (Server Mode)
================================

When running inside an LLM-driven ``std.Prompt`` task, the ``dfm`` command
automatically connects to the parent DFM session via a Unix socket server.
This enables LLMs to execute tasks that share resources with the parent session.

How It Works
------------

1. When ``dfm run`` starts, a command server is created on a Unix socket
2. The socket path is set in ``DFM_SERVER_SOCKET`` environment variable
3. Child processes (like LLM assistants) detect this variable
4. The ``dfm`` command runs in client mode, forwarding requests to the server
5. Tasks execute within the parent session's context

Benefits
--------

* **Resource Sharing**: Respects parent session's parallelism limits (``-j``)
* **State Consistency**: Sees outputs from tasks already completed in the session
* **Cache Sharing**: Uses the same memento cache for incremental builds
* **Unified Logging**: All task output appears in the parent session's logs

Commands Available in Server Mode
---------------------------------

When ``DFM_SERVER_SOCKET`` is set, the following commands work:

.. code-block:: bash

    # Execute tasks via parent session
    dfm run task1 task2
    dfm run task1 -D param=value
    dfm run task1 --timeout 300

    # Query project state
    dfm show tasks
    dfm show task my_project.build
    dfm context --json

    # Validate configuration
    dfm validate

    # Health check
    dfm ping

Example: LLM Generating and Compiling RTL
-----------------------------------------

When an LLM running inside a ``std.Prompt`` task needs to compile generated code:

.. code-block:: bash

    # 1. LLM creates RTL files
    cat > counter.sv << 'EOF'
    module counter(input clk, rst_n, output logic [7:0] count);
      always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) count <= 0;
        else count <= count + 1;
    endmodule
    EOF

    # 2. Run compilation via parent DFM session
    dfm run hdlsim.vlt.SimImage \
      -D hdlsim.vlt.SimImage.top=counter

    # 3. Output is JSON with status, outputs, and markers
    # {"status": 0, "outputs": [...], "markers": []}

JSON Response Format
--------------------

All server mode commands return JSON responses:

**Success Response:**

.. code-block:: json

    {
      "status": 0,
      "outputs": [
        {
          "task": "hdlsim.vlt.SimImage",
          "changed": true,
          "output": [
            {
              "type": "hdlsim.SimImage",
              "exe_path": "/path/to/rundir/Vtop"
            }
          ]
        }
      ],
      "markers": []
    }

**Error Response:**

.. code-block:: json

    {
      "status": 1,
      "outputs": [],
      "markers": [
        {
          "task": "hdlsim.vlt.SimImage",
          "msg": "Compilation failed: syntax error",
          "severity": "error"
        }
      ]
    }

Agent-Friendly Discovery
========================

JSON Output for ``dfm show``
----------------------------

The ``dfm show`` commands support ``--json`` output for programmatic consumption:

.. code-block:: bash

    # List packages as JSON
    dfm show packages --json

    # Get task details as JSON
    dfm show task std.FileSet --json

    # Show project structure as JSON
    dfm show project --json

    # List available skills
    dfm show skills --json

    # Get full project context
    dfm context --json

This enables agents to query DFM metadata and construct correct configurations.

The ``dfm context`` Command
---------------------------

The ``dfm context`` command provides comprehensive project information in a
single JSON output, ideal for LLM consumption:

.. code-block:: bash

    $ dfm context --json
    {
      "project": {
        "name": "my_project",
        "root_dir": "/path/to/project",
        "rundir": "/path/to/rundir"
      },
      "tasks": [
        {"name": "my_project.build", "scope": "root", "uses": "hdlsim.vlt.SimImage"},
        {"name": "my_project.rtl", "scope": "local", "uses": "std.FileSet"}
      ],
      "types": [...],
      "skills": [...]
    }

Integration with AI Assistants
==============================

GitHub Copilot CLI
------------------

.. code-block:: bash

    # Get skill path and read documentation
    dfm --help
    # Then read the skill.md file at the displayed path

    # Use show commands for discovery
    dfm show skills --json
    dfm show packages --json

    # Inside a Prompt task, execute tasks via server
    dfm run build_task

ChatGPT / Claude
----------------

When working with conversational AI:

1. Run ``dfm --help`` and share the skill.md content
2. Use ``dfm show skills`` to list available capabilities
3. Use ``dfm show task <name> --json`` for specific task details

Example Agent Workflows
=======================

Project Initialization
----------------------

**User prompt**: "Create a DFM flow for simulating my counter.sv with Verilator"

**Agent workflow**:

.. code-block:: bash

    # 1. Get DFM skill path from help
    dfm --help
    # Read the skill.md file at the absolute path shown

    # 2. Find Verilator package
    dfm show packages --search vlt --json

    # 3. Get SimImage details
    dfm show task hdlsim.vlt.SimImage --json

    # 4. Generate flow.yaml
    # (Agent creates file)

    # 5. Validate
    dfm validate flow.yaml

    # 6. Run
    dfm run build

**Generated flow.yaml**:

.. code-block:: yaml

    package:
      name: counter_sim
      
      imports:
        - name: hdlsim.vlt
          as: sim
      
      tasks:
        - name: rtl
          uses: std.FileSet
          with:
            type: systemVerilogSource
            include: "counter.sv"
        
        - name: build
          uses: sim.SimImage
          needs: [rtl]
          with:
            top: [counter]
        
        - name: run
          uses: sim.SimRun
          needs: [build]

Dynamic Code Generation and Verification
----------------------------------------

**User prompt**: "Generate a counter module and verify it compiles"

**Agent workflow** (inside a Prompt task):

.. code-block:: bash

    # 1. Generate the RTL
    cat > counter.sv << 'EOF'
    module counter #(parameter WIDTH=8) (
      input  logic clk,
      input  logic rst_n,
      output logic [WIDTH-1:0] count
    );
      always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) count <= '0;
        else count <= count + 1'b1;
    endmodule
    EOF

    # 2. Run compilation through parent session
    dfm run hdlsim.vlt.SimImage -D top=counter

    # 3. Check if compilation succeeded
    # (Parse JSON response)

    # 4. Write result file for Prompt task
    cat > result.json << 'EOF'
    {
      "status": 0,
      "changed": true,
      "output": [
        {"type": "std.FileSet", "basedir": ".", "files": ["counter.sv"]}
      ],
      "markers": []
    }
    EOF

Adding UVM Support
------------------

**User prompt**: "Add UVM support to my simulation"

**Agent workflow**:

.. code-block:: bash

    # 1. Understand current project
    dfm show project --json

    # 2. Identify current simulator
    # (Parse output to find hdlsim.vlt)

    # 3. Get SimLibUVM info
    dfm show task hdlsim.vlt.SimLibUVM --json

    # 4. Modify flow.yaml to add SimLibUVM

    # 5. Validate changes
    dfm validate flow.yaml

Debugging Build Failures
------------------------

**User prompt**: "My build is failing with 'module not found'"

**Agent workflow**:

.. code-block:: bash

    # 1. Get project structure
    dfm show project --json

    # 2. Get build task with dependencies
    dfm show task build --needs --json

    # 3. List files in rtl task
    dfm show task rtl --json

    # 4. Diagnose and fix

Best Practices
==============

1. **Start with help**: Run ``dfm --help`` to get the skill.md path
2. **Use skills for discovery**: ``dfm show skills`` lists package capabilities
3. **Use JSON output**: ``--json`` flag enables programmatic parsing
4. **Use context command**: ``dfm context --json`` provides complete project state
5. **Verify suggestions**: Always review AI-generated configurations
6. **Report issues**: If AI consistently misunderstands, the skill docs may need updates

Without proper context, AI assistants may suggest incorrect syntax or non-existent
features. With the skill.md documentation and ``dfm show skills``, assistants can:

* Understand DFM's unique dataflow model
* Suggest appropriate standard library tasks
* Help with package organization
* Debug flow definition issues
* Propose DFM-specific best practices
* **Execute tasks dynamically inside Prompt tasks**

Enabling LLM Support in Your Project
====================================

For detailed instructions on enabling LLM agent support in your own projects,
including creating AGENTS.md files and defining custom skills, see the
:doc:`userguide/llm_integration` guide.
