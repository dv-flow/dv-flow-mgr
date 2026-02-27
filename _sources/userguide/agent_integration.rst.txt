#######################
AI Agent Integration
#######################

This guide explains how to define skills, personas, tools, and references in
your DV Flow project to create context-aware AI agent sessions.

.. note::

   DV Flow Manager now includes a **built-in native agent** that requires no
   external CLI tools.  It supports GitHub Copilot, OpenAI, Anthropic, Ollama,
   and any OpenAI-compatible provider.  See :doc:`native_agent` for setup and
   provider configuration.

   The original subprocess-based agents (GitHub Copilot CLI, Codex CLI) remain
   available via ``-a copilot`` / ``-a codex``.

Overview
========

DV Flow Manager's agent integration allows you to:

* Launch the built-in native AI agent or an external subprocess assistant with project-specific context
* Define reusable skills that describe capabilities and knowledge domains
* Create personas that combine skills with specific roles or personalities
* Provide reference documentation directly to the AI
* Configure external tools and MCP servers for the AI to use

The agent command evaluates task definitions to collect these resources, generates
a comprehensive system prompt, and launches the agent in interactive mode.

Quick Start
===========

1. **Define a skill** in your ``flow.yaml``:

.. code-block:: yaml

    tasks:
    - local: DVFlowSkill
      uses: std.AgentSkill
      desc: DV Flow Manager capabilities and commands
      with:
        files:
        - "${{ srcdir }}/skills/dvflow_skill.md"

2. **Create the skill documentation** (``skills/dvflow_skill.md``):

.. code-block:: markdown

    # DV Flow Manager Skill
    
    ## Available Commands
    
    - `dfm run [tasks]` - Execute workflow tasks
    - `dfm show tasks` - List available tasks
    - `dfm show task <name>` - Get task details
    
    ## Common Workflows
    
    ### Building the project
    ```bash
    dfm run build
    ```
    
    ### Running tests
    ```bash
    dfm run test
    ```

3. **Launch the agent** (native agent runs automatically when no subprocess CLI is found):

.. code-block:: bash

    dfm agent DVFlowSkill

    # Or explicitly select the native agent and a specific provider:
    dfm agent -a native -m openai/gpt-4o DVFlowSkill

See :doc:`native_agent` for full provider configuration options.

Agent Resources
===============

DV Flow Manager supports four types of agent resources, each serving a different purpose.

Skills (AgentSkill)
-------------------

Skills define capabilities and knowledge domains. They typically contain:

* Command references
* API documentation
* Best practices
* Domain-specific knowledge

**Definition:**

.. code-block:: yaml

    tasks:
    - local: MySkill
      uses: std.AgentSkill
      desc: Description of what this skill provides
      with:
        files:
        - "${{ srcdir }}/path/to/skill.md"
        - "${{ srcdir }}/path/to/examples.md"

**Skill File Format:**

Skills are typically written in Markdown and should be structured for easy consumption
by AI models:

.. code-block:: markdown

    # Skill Name
    
    Brief overview of what this skill covers.
    
    ## Commands
    
    List of commands with descriptions and examples.
    
    ## Concepts
    
    Key concepts and terminology.
    
    ## Examples
    
    Practical examples of usage.
    
    ## Common Patterns
    
    Frequently used patterns and idioms.

**Best Practices:**

* Keep skill files focused on a single domain
* Use clear, concise language
* Include plenty of examples
* Organize with clear headings
* Keep each skill under 5000 tokens if possible

Personas (AgentPersona)
-----------------------

Personas define the role or character the AI should adopt. They can depend on skills
to combine capabilities with personality.

**Definition:**

.. code-block:: yaml

    tasks:
    - local: ExpertEngineer
      uses: std.AgentPersona
      needs: [DVFlowSkill, PythonSkill, TestingSkill]
      desc: |
        I am an expert verification engineer with deep knowledge of 
        DV Flow Manager. I write clear, well-documented code and 
        comprehensive tests. I prefer incremental development with 
        frequent validation.

**Using Personas:**

.. code-block:: bash

    dfm agent ExpertEngineer

The assistant will:

1. Adopt the persona's role and communication style
2. Have access to all dependent skills
3. Apply the persona's principles to responses

**Example Personas:**

* **Debugger**: Focuses on systematic problem diagnosis
* **Optimizer**: Prioritizes performance and efficiency
* **Teacher**: Explains concepts clearly with examples
* **Reviewer**: Provides constructive code review feedback

Tools (AgentTool)
-----------------

Tools define external programs or MCP servers that the agent can invoke.

**Definition:**

.. code-block:: yaml

    tasks:
    - local: FileSystemTool
      uses: std.AgentTool
      desc: File system operations via MCP
      with:
        command: npx
        args:
        - "-y"
        - "@modelcontextprotocol/server-filesystem"
        - "${{ rootdir }}"

**MCP Server Integration:**

Model Context Protocol (MCP) servers provide structured interfaces for tools.
Popular MCP servers include:

* ``@modelcontextprotocol/server-filesystem`` - File operations
* ``@modelcontextprotocol/server-git`` - Git operations
* ``@modelcontextprotocol/server-sqlite`` - Database queries

**Note:** MCP integration is currently in development. Tools are prepared for
future use but may not be fully functional in all assistants yet.

References (AgentReference)
---------------------------

References provide documentation and reference material to the agent.

**Definition:**

.. code-block:: yaml

    tasks:
    - local: ProjectDocs
      uses: std.AgentReference
      desc: Project architecture and API documentation
      with:
        files:
        - "${{ rootdir }}/docs/architecture.md"
        - "${{ rootdir }}/docs/api_reference.md"
        urls:
        - "https://example.com/external-docs"

**When to Use References:**

* Project-specific documentation
* API specifications
* Architecture diagrams
* Design documents
* External documentation links

Creating Agent-Aware Packages
==============================

To make your package easy to use with AI agents, follow these guidelines.

Package-Level Skills
--------------------

Create a skill that describes your package's capabilities:

.. code-block:: yaml

    # In mypackage/flow.yaml
    package:
      name: mypackage
      desc: Hardware verification utilities
    
    tasks:
    - local: MyPackageSkill
      uses: std.AgentSkill
      desc: Capabilities provided by mypackage
      with:
        files:
        - "${{ pkgdir }}/docs/agent_skill.md"

Discoverable with:

.. code-block:: bash

    dfm show skills
    dfm show skills --package mypackage

Project-Level Personas
----------------------

Create personas for common project roles:

.. code-block:: yaml

    # In project/flow.yaml
    
    imports:
    - pkg: mypackage
    
    tasks:
    # Import skills from packages
    - local: MyPackageSkill
      uses: mypackage.MyPackageSkill
    
    # Define project-specific persona
    - local: ProjectDeveloper
      uses: std.AgentPersona
      needs: [MyPackageSkill]
      desc: |
        I am familiar with this project's structure and conventions.
        I follow the team's coding standards and testing practices.

Composing Contexts
==================

You can combine multiple resources when launching an agent:

**Multiple Skills:**

.. code-block:: bash

    dfm agent PythonSkill TestingSkill DocumentationSkill

**Persona with Extra Skills:**

.. code-block:: bash

    dfm agent ProjectDeveloper DebugSkill ProfilingSkill

**Everything:**

.. code-block:: bash

    dfm agent MainPersona ProjectDocs FileSystemTool

Advanced Usage
==============

Debugging Context
-----------------

Preview what context will be sent to the agent:

.. code-block:: bash

    # Save prompt to file
    dfm agent MyPersona --config-file prompt.md
    
    # View as JSON
    dfm agent MyPersona --json | jq
    
    # Check specific sections
    dfm agent MyPersona --json | jq '.skills'

Custom Models
-------------

The native agent accepts any LiteLLM model name via ``-m``:

.. code-block:: bash

    # GitHub Copilot (default)
    dfm agent -a native -m github_copilot/gpt-4.1

    # OpenAI
    dfm agent -a native -m openai/gpt-4o

    # Anthropic
    dfm agent -a native -m anthropic/claude-3-5-sonnet-20241022

    # Local model via Ollama
    dfm agent -a native -m ollama/llama3.2

See :doc:`native_agent` for environment variable setup and a full provider list.

Subprocess assistants can also specify a model:

.. code-block:: bash

    # With Copilot CLI
    dfm agent -a copilot --model gpt-4

Fresh Context
-------------

Force re-evaluation of all tasks:

.. code-block:: bash

    dfm agent MyPersona --clean

This ensures all skill files and references are read fresh, useful when you've
updated documentation.

Parameterized Resources
-----------------------

Agent resources can use parameters:

.. code-block:: yaml

    params:
    - name: project_phase
      type: str
      default: development
    
    tasks:
    - local: PhaseSpecificSkill
      uses: std.AgentSkill
      desc: Skills for ${{ project_phase }} phase
      with:
        files:
        - "${{ srcdir }}/skills/${{ project_phase }}_skill.md"

Use with:

.. code-block:: bash

    dfm agent PhaseSpecificSkill -D project_phase=testing

Best Practices
==============

Skill Organization
------------------

**Do:**

* Create focused, single-purpose skills
* Use clear, hierarchical structure
* Include practical examples
* Keep skills under 5000 tokens each
* Version control skill documents

**Don't:**

* Create monolithic "everything" skills
* Include outdated information
* Use jargon without explanation
* Forget to update skills when APIs change

Persona Design
--------------

**Effective Personas:**

* Have clear, specific roles
* Include behavioral guidelines
* List explicit do's and don'ts
* Reference relevant skills
* Use natural, conversational language

**Example:**

.. code-block:: yaml

    - local: CarefulReviewer
      uses: std.AgentPersona
      needs: [CodingStandards, SecuritySkill]
      desc: |
        I am a careful code reviewer who:
        - Checks for security vulnerabilities first
        - Validates error handling and edge cases
        - Ensures code follows team standards
        - Provides constructive, actionable feedback
        - Points out both problems and good practices

Testing Agent Resources
-----------------------

Test your agent resources before committing:

1. **Preview context**:

   .. code-block:: bash
   
       dfm agent YourPersona --config-file preview.md

2. **Check for errors**:

   .. code-block:: bash
   
       dfm agent YourPersona --json

3. **Launch and validate**:

   .. code-block:: bash
   
       dfm agent YourPersona

4. **Ask test questions** to verify the agent has correct context

Documentation Updates
---------------------

Keep agent resources synchronized with your code:

* Update skills when commands change
* Revise personas as team practices evolve
* Refresh references when documentation moves
* Review and update quarterly

Common Patterns
===============

Development Assistant
---------------------

.. code-block:: yaml

    tasks:
    - local: ProjectSkill
      uses: std.AgentSkill
      desc: Project commands and structure
      with:
        files: ["${{ srcdir }}/docs/project_skill.md"]
    
    - local: DevAssistant
      uses: std.AgentPersona
      needs: [ProjectSkill]
      desc: |
        I help with day-to-day development tasks.
        I can run builds, execute tests, and explain errors.

**Usage:**

.. code-block:: bash

    dfm agent DevAssistant

Troubleshooting Expert
----------------------

.. code-block:: yaml

    tasks:
    - local: DebugSkill
      uses: std.AgentSkill
      desc: Debugging techniques and tools
      with:
        files: ["${{ srcdir }}/docs/debug_skill.md"]
    
    - local: LogAnalysisSkill
      uses: std.AgentSkill
      desc: Log file analysis patterns
      with:
        files: ["${{ srcdir }}/docs/log_analysis.md"]
    
    - local: Troubleshooter
      uses: std.AgentPersona
      needs: [DebugSkill, LogAnalysisSkill]
      desc: |
        I am a systematic troubleshooter who:
        - Reproduces issues reliably
        - Forms hypotheses before diving into code
        - Uses logging and traces effectively
        - Documents findings for future reference

**Usage:**

.. code-block:: bash

    dfm agent Troubleshooter

Documentation Writer
--------------------

.. code-block:: yaml

    tasks:
    - local: DocStyleSkill
      uses: std.AgentSkill
      desc: Documentation style guide
      with:
        files: ["${{ srcdir }}/docs/style_guide.md"]
    
    - local: APIReference
      uses: std.AgentReference
      desc: Current API documentation
      with:
        files: ["${{ srcdir }}/docs/api/*.md"]
    
    - local: DocWriter
      uses: std.AgentPersona
      needs: [DocStyleSkill]
      desc: |
        I write clear, comprehensive documentation with:
        - Practical examples
        - Clear explanations
        - Proper formatting
        - Accurate cross-references

**Usage:**

.. code-block:: bash

    dfm agent DocWriter APIReference

Examples
========

Complete Example: Verification Project
---------------------------------------

**File: flow.yaml**

.. code-block:: yaml

    package:
      name: myproject
      desc: Hardware verification project
    
    imports:
    - pkg: verification_lib
    
    tasks:
    # Skills
    - local: UVMSkill
      uses: std.AgentSkill
      desc: UVM methodology and patterns
      with:
        files:
        - "${{ srcdir }}/docs/skills/uvm_skill.md"
    
    - local: ProjectSkill
      uses: std.AgentSkill
      desc: Project-specific commands and workflows
      with:
        files:
        - "${{ srcdir }}/docs/skills/project_skill.md"
    
    # References
    - local: DesignSpec
      uses: std.AgentReference
      desc: Design specification documents
      with:
        files:
        - "${{ rootdir }}/specs/design_spec.md"
    
    # Personas
    - local: VerificationEngineer
      uses: std.AgentPersona
      needs: [UVMSkill, ProjectSkill]
      desc: |
        I am a verification engineer working on this project.
        I write UVM testbenches, analyze coverage, and debug failures.
        I follow the project's coding standards and verification plan.
    
    - local: TestDebugger
      uses: std.AgentPersona
      needs: [UVMSkill, ProjectSkill, DesignSpec]
      desc: |
        I specialize in debugging failing tests.
        I systematically analyze waveforms, logs, and assertions.
        I reproduce issues reliably before proposing fixes.

**Usage:**

.. code-block:: bash

    # General development
    dfm agent VerificationEngineer
    
    # Debugging a specific test
    dfm agent TestDebugger
    
    # Quick reference access
    dfm agent ProjectSkill DesignSpec --config-file quick_ref.md

Troubleshooting
===============

Agent Not Launching
-------------------

**Error:** "No module named 'agents'"

The native agent optional dependencies are not installed:

.. code-block:: bash

    pip install dv-flow-mgr[agent]

**Error:** "No AI assistant available" (subprocess path)

A subprocess CLI assistant was requested but is not in PATH.  Either install
it or use the native agent instead:

.. code-block:: bash

    # Use the native agent (no external tools needed)
    dfm agent -a native

    # Or install the Copilot CLI
    npm install -g @github/copilot-cli

See :doc:`native_agent` for native agent authentication and provider
configuration, including troubleshooting common errors such as rate limits,
OAuth prompts, and Ollama connectivity.

Tasks Not Evaluating
--------------------

**Error:** "Task execution failed"

**Solution:** Run tasks directly first to ensure they work:

.. code-block:: bash

    dfm run MySkill
    dfm agent MySkill

Check that all file paths in ``files:`` arrays are valid and accessible.

Context Too Large
-----------------

**Issue:** The generated prompt is too large for the model

**Solution:** 

1. Split large skills into smaller, focused ones
2. Use multiple smaller agent sessions instead of one large one
3. Reference external docs via URLs instead of including full text

Missing Skills
--------------

**Issue:** Skills not appearing in agent context

**Solution:** Verify skills are properly tagged:

.. code-block:: bash

    dfm show skills
    dfm show task MySkill
    dfm agent MySkill --json | jq '.skills'

FAQ
===

**Q: Can I use the agent command in CI/CD?**

A: The agent command is designed for interactive use. For CI/CD, use the standard
``dfm run`` and ``dfm show`` commands.

**Q: How do I share personas across projects?**

A: Define personas in a shared package that projects can import:

.. code-block:: yaml

    imports:
    - pkg: company_agents
    
    tasks:
    - local: CompanyEngineer
      uses: company_agents.StandardEngineerPersona

**Q: Can I create private skills?**

A: Yes, use local scope tasks that won't be exported:

.. code-block:: yaml

    tasks:
    - local: PrivateSkill
      uses: std.AgentSkill
      # Not marked for export

**Q: How often should I update skills?**

A: Update skills whenever:

* Commands or APIs change
* New features are added
* Team practices evolve
* Feedback shows confusion

**Q: Can agents execute dfm commands?**

A: Yes, when launched with the agent command, assistants can execute dfm commands
in the project directory. The system prompt includes available dfm commands and usage.

See Also
========

* :doc:`native_agent` — Native agent setup, provider configuration, and TUI reference
* :doc:`llm_integration` - General LLM integration guide
* :doc:`tasks_developing` - Creating tasks
* :doc:`../cmdref` - Command reference
* :doc:`stdlib` - Standard library reference
