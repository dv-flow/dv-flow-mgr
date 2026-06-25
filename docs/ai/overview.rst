########
Overview
########

DV Flow Manager has three distinct AI-related capabilities. They serve
different audiences, and this page helps you find the right one.

The three capabilities
======================

**Driving DFM from an external agent.**
    You use an external coding agent (Claude, GitHub Copilot, and others) and
    want it to discover, understand, and run your DFM project. The agent calls
    ``dfm`` commands, reads ``AGENTS.md``, and consumes JSON discovery output.
    → :doc:`using_with_agents`

**Authoring agent resources in a package.**
    You are building a package and want to ship *resources* -- Skills,
    Personas, Tools, and References -- so that any agent working with your
    package starts with the right context. → :doc:`agent_resources`

**Using the built-in native agent.**
    You want DFM's own ``dfm agent`` TUI, which runs an LLM-driven assistant
    against your project with a configurable provider. → :doc:`native_agent`

Which page do I want?
=====================

.. list-table::
   :header-rows: 1
   :widths: 55 45

   * - If you want to...
     - Go to
   * - Expose your project to Claude/Copilot/etc.
     - :doc:`using_with_agents`
   * - Discover tasks and skills as JSON (``dfm show ... --json``)
     - :doc:`using_with_agents`
   * - Override parameters from an agent (``-D`` / ``-P``)
     - :doc:`using_with_agents`
   * - Ship Skills / Personas / Tools / References with a package
     - :doc:`agent_resources`
   * - Define a reusable skill document (``std.AgentSkill``)
     - :doc:`agent_resources`
   * - Run DFM's built-in ``dfm agent`` assistant
     - :doc:`native_agent`

Key concepts
============

* **Skill** -- a Markdown document (and optional examples) that teaches an agent
  how to use a package or project. Defined with ``std.AgentSkill`` and
  discoverable via ``dfm show skills``.
* **Persona** -- a behavioral profile that shapes how the agent responds.
* **Tool** -- an external tool or MCP server the agent may invoke.
* **Reference** -- supplementary files or URLs the agent should consult.

Skills, personas, tools, and references are all *agent resources*; see
:doc:`agent_resources` for how to author them.
