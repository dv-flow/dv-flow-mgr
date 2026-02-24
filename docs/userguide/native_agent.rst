######################
Native AI Agent (dfm agent)
######################

DV Flow Manager ships a fully-embedded, native AI agent that runs entirely
within the ``dfm`` process — no external CLI tools required.  It is the
default when no subprocess assistant (GitHub Copilot CLI, Codex CLI) is
detected in ``PATH``, and can also be selected explicitly with
``-a native``.

The native agent is powered by `openai-agents`_ + `LiteLLM`_, which means
it supports every model provider that LiteLLM supports, including GitHub
Copilot, OpenAI, Anthropic, Google, Azure, Ollama, and any
OpenAI-compatible endpoint.

.. _openai-agents: https://github.com/openai/openai-agents-python
.. _LiteLLM: https://docs.litellm.ai/

Quick Start
===========

.. code-block:: bash

    # Auto-detect: uses native agent when no subprocess CLI is found
    dfm agent

    # Explicitly use the native agent
    dfm agent -a native

    # Specify a model
    dfm agent -a native -m openai/gpt-4o

    # With project context
    dfm agent -a native MySkill MyPersona

Installing the Agent Dependencies
==================================

The agent dependencies are an optional extra that must be installed:

.. code-block:: bash

    pip install dv-flow-mgr[agent]

Or, in a project managed by ``ivpm``:

.. code-block:: bash

    # Add to ivpm.yaml agent dep-set, then:
    ivpm update

Provider Configuration
======================

The native agent uses LiteLLM to talk to the underlying model provider.
The model is selected in this priority order:

1. ``-m`` / ``--model`` CLI flag
2. ``model:`` key in config file (``~/.dfm/agent.yaml`` or ``.dfm/agent.yaml``)
3. ``DFM_MODEL`` environment variable
4. ``DFM_PROVIDER`` environment variable (uses ``<provider>/gpt-4.1``)
5. **Auto-detected from well-known API-key environment variables** (see table below)
6. Built-in default: ``github_copilot/gpt-4.1``

In most cases you only need to export the right key and the agent will figure
out the provider automatically:

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Environment variable
     - Auto-selected model
   * - ``GITHUB_TOKEN``
     - ``github_copilot/gpt-4.1``
   * - ``OPENAI_API_KEY``
     - ``openai/gpt-4.1``
   * - ``ANTHROPIC_API_KEY``
     - ``anthropic/claude-3-5-sonnet-20241022``
   * - ``GEMINI_API_KEY``
     - ``gemini/gemini-2.0-flash``
   * - ``AZURE_API_KEY`` + ``AZURE_API_BASE``
     - ``azure/gpt-4o``
   * - ``OLLAMA_HOST``
     - ``ollama/llama3.2``

Model names follow the LiteLLM convention ``<provider>/<model-name>``.

GitHub Copilot
--------------

GitHub Copilot is the default provider. It uses your existing Copilot
subscription — no separate API key is required.

**Authentication** is handled via the GitHub CLI token or a ``GITHUB_TOKEN``
environment variable.  The first time you use a Copilot model, LiteLLM may
trigger an OAuth device-flow prompt in the terminal.

.. code-block:: bash

    # Export a GitHub personal access token (recommended for headless use)
    export GITHUB_TOKEN=ghp_...

    # Default Copilot model
    dfm agent -a native

    # Specific Copilot model
    dfm agent -a native -m github_copilot/gpt-4.1
    dfm agent -a native -m github_copilot/claude-3.7-sonnet
    dfm agent -a native -m github_copilot/o3-mini

Available Copilot model names depend on your subscription; ``gpt-4.1``,
``gpt-4o``, ``claude-3.7-sonnet``, and ``o3-mini`` are common options.

**Config file shorthand:**

.. code-block:: yaml

    # ~/.dfm/agent.yaml
    model: github_copilot/gpt-4.1

OpenAI
------

.. code-block:: bash

    export OPENAI_API_KEY=sk-...

    # GPT-4o (recommended)
    dfm agent -a native -m openai/gpt-4o

    # GPT-4o-mini (faster, cheaper)
    dfm agent -a native -m openai/gpt-4o-mini

    # o1 reasoning model
    dfm agent -a native -m openai/o1

**Config file:**

.. code-block:: yaml

    # ~/.dfm/agent.yaml
    model: openai/gpt-4o

Anthropic Claude
----------------

.. code-block:: bash

    export ANTHROPIC_API_KEY=sk-ant-...

    dfm agent -a native -m anthropic/claude-3-5-sonnet-20241022
    dfm agent -a native -m anthropic/claude-3-opus-20240229

**Config file:**

.. code-block:: yaml

    model: anthropic/claude-3-5-sonnet-20241022

Azure OpenAI
------------

.. code-block:: bash

    export AZURE_API_KEY=...
    export AZURE_API_BASE=https://your-resource.openai.azure.com/
    export AZURE_API_VERSION=2024-02-01

    dfm agent -a native -m azure/your-deployment-name

**Config file:**

.. code-block:: yaml

    model: azure/your-deployment-name

Custom HTTP Headers and API Gateway Authentication
--------------------------------------------------

Some organisations route model requests through a proxy or API gateway that
requires an auth token or subscription key in a custom HTTP header.  Use
``model_settings.headers`` in the config file:

.. code-block:: yaml

    # .dfm/agent.yaml
    model: openai/gpt-4o
    model_settings:
      api_base:    https://llm-proxy.example.com
      api_key:     "${{ env.LLM_API_KEY }}"
      api_version: "2024-06-01"
      ssl_verify:  false
      headers:
        X-Auth-Token: "${{ env.LLM_AUTH_TOKEN }}"

The ``${{ env.VAR }}`` syntax expands the named environment variable at
config-load time, so the key never has to be stored in plain text:

.. code-block:: bash

    export LLM_AUTH_TOKEN=my-secret-token
    dfm agent -a native

All entries under ``model_settings`` are passed directly to the underlying
LiteLLM ``acompletion()`` call:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Key
     - Description
   * - ``api_base``
     - Override the endpoint URL
   * - ``api_key``
     - Override the API key (can use ``${{ env.VAR }}``)
   * - ``api_version``
     - API version string (required for Azure)
   * - ``ssl_verify``
     - Set to ``false`` to disable TLS certificate verification
   * - ``headers``
     - Dict of custom HTTP headers added to every request

Google Gemini
-------------

.. code-block:: bash

    export GEMINI_API_KEY=...

    dfm agent -a native -m gemini/gemini-1.5-pro
    dfm agent -a native -m gemini/gemini-1.5-flash

OpenAI-Compatible Endpoints (vLLM, LM Studio, etc.)
----------------------------------------------------

Any server that implements the OpenAI chat-completions API can be used.
Set ``OPENAI_API_BASE`` (or ``OPENAI_BASE_URL``) to point at your server:

.. code-block:: bash

    export OPENAI_API_BASE=http://my-server:8000/v1
    export OPENAI_API_KEY=dummy          # required by LiteLLM even if unused

    dfm agent -a native -m openai/my-deployed-model

Ollama (Local Models)
---------------------

`Ollama`_ runs open-weight models locally.  Install Ollama and pull a model,
then point LiteLLM at it:

.. _Ollama: https://ollama.com

.. code-block:: bash

    # Start Ollama (it runs on http://localhost:11434 by default)
    ollama pull llama3.2
    ollama pull qwen2.5-coder:7b

    # Run via LiteLLM's ollama provider
    dfm agent -a native -m ollama/llama3.2
    dfm agent -a native -m ollama/qwen2.5-coder:7b

    # Or set DFM_MODEL to avoid typing it every time
    export DFM_MODEL=ollama/qwen2.5-coder:7b
    dfm agent

.. note::

   Smaller models (7 B parameters and below) may struggle with complex
   multi-tool workflows.  ``qwen2.5-coder:14b``, ``llama3.1:8b``, or
   ``mistral-nemo`` are reasonable minimum sizes for productive sessions.

Ollama on a remote host:

.. code-block:: bash

    export OLLAMA_API_BASE=http://gpu-server:11434
    dfm agent -a native -m ollama/llama3.2

Environment Variables Summary
==============================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``DFM_MODEL``
     - Full LiteLLM model name, e.g. ``openai/gpt-4o``
   * - ``DFM_PROVIDER``
     - Provider prefix only; model defaults to ``<provider>/gpt-4.1``
   * - ``GITHUB_TOKEN``
     - GitHub personal-access-token; **auto-selects** ``github_copilot/gpt-4.1``
   * - ``OPENAI_API_KEY``
     - OpenAI (or OpenAI-compatible) API key; **auto-selects** ``openai/gpt-4.1``
   * - ``OPENAI_API_BASE``
     - Override base URL for OpenAI-compatible servers
   * - ``ANTHROPIC_API_KEY``
     - Anthropic API key; **auto-selects** ``anthropic/claude-3-5-sonnet-20241022``
   * - ``AZURE_API_KEY``
     - Azure OpenAI key; combined with ``AZURE_API_BASE`` **auto-selects** ``azure/gpt-4o``
   * - ``AZURE_API_BASE``
     - Azure OpenAI endpoint URL
   * - ``AZURE_API_VERSION``
     - Azure OpenAI API version string
   * - ``GEMINI_API_KEY``
     - Google Gemini API key; **auto-selects** ``gemini/gemini-2.0-flash``
   * - ``OLLAMA_HOST``
     - Ollama server URL; **auto-selects** ``ollama/llama3.2``
   * - ``OLLAMA_API_BASE``
     - Alternative Ollama server URL (used by LiteLLM directly)

Config File
===========

Create ``~/.dfm/agent.yaml`` (user-wide) and/or ``.dfm/agent.yaml``
(project-local, takes precedence) to set persistent defaults:

.. code-block:: yaml

    # ~/.dfm/agent.yaml  or  .dfm/agent.yaml
    model: github_copilot/gpt-4.1

    # Tool approval mode: never | auto | write
    #   never  – run all tools automatically (default)
    #   auto   – prompt before shell/write tools
    #   write  – alias for auto
    approval_mode: never

    # Enable agent tracing (writes JSONL to trace_dir)
    trace: false
    trace_dir: ~/.dfm/traces/

    # Extra text appended to the generated system prompt
    system_prompt_extra: |
        Always prefer minimal, targeted code changes.

    # LiteLLM model-level settings (all optional)
    model_settings:
      api_base:    https://llm-proxy.example.com  # override endpoint
      api_key:     "${{ env.LLM_API_KEY }}"       # or plain string
      api_version: "2024-06-01"                   # e.g. Azure API version
      ssl_verify:  false                           # disable TLS verification
      headers:                                    # custom HTTP request headers
        X-Auth-Token: "${{ env.LLM_AUTH_TOKEN }}"
        X-Custom-Header: some-value

    # Additional MCP servers to start (advanced)
    mcp_servers:
      - name: my-tool
        command: uvx
        args: [mcp-my-tool]

CLI flags always override config-file values.

Environment Variable References
--------------------------------

Any string value in the config file can reference an environment variable
using ``${{ env.VAR_NAME }}`` syntax.  This is evaluated at load time:

.. code-block:: yaml

    model_settings:
      api_key: "${{ env.OPENAI_API_KEY }}"
      headers:
        X-Auth-Token: "${{ env.LLM_AUTH_TOKEN }}"
        Authorization: "Bearer ${{ env.MY_BEARER_TOKEN }}"

If the referenced variable is not set, the value expands to an empty string
and a warning is logged.

TUI Interaction
===============

The native agent presents a Rich + prompt_toolkit terminal UI with streaming
Markdown output and colour-coded tool-call panels.

Slash Commands
--------------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Command
     - Description
   * - ``/help``
     - Show all slash commands
   * - ``/model``
     - Display the active model name
   * - ``/tools``
     - List all registered tools
   * - ``/skills``
     - List skills and personas defined in the project
   * - ``/personas``
     - Alias for ``/skills``
   * - ``/skill add <Name>``
     - Hot-load a skill into the current session
   * - ``/persona add <Name>``
     - Hot-load a persona into the current session
   * - ``/cost``
     - Show cumulative token usage for the session
   * - ``/approval [mode]``
     - Show or set tool approval mode (``never`` / ``auto`` / ``write``)
   * - ``/clear``
     - Clear conversation history
   * - ``/exit``, ``/quit``
     - Exit the agent

Keyboard Shortcuts
------------------

* **Ctrl+D** — exit immediately (same as ``/exit``)
* **Ctrl+C** — cancel the current response; press again within 1 second to exit
* **Up / Down** — navigate input history

Approval Mode
-------------

By default (``never``), all tool calls execute automatically.  Set
``approval_mode: auto`` (or use ``--approval-mode auto``) to be prompted
before any ``shell_exec``, ``write_file``, or ``apply_patch`` call:

.. code-block:: bash

    dfm agent --approval-mode auto

You can also change the mode mid-session:

.. code-block:: text

    > /approval auto
    Approval mode set to: auto

    > /approval never
    Approval mode set to: never

Tracing
-------

Enable detailed span tracing for debugging or auditing:

.. code-block:: bash

    dfm agent --trace

Traces are written as JSONL to ``~/.dfm/traces/trace_<timestamp>.jsonl``.

Available Tools
===============

The native agent has access to two sets of built-in tools.

DFM Tools (blue panels)
-----------------------

These tools give the agent direct access to DV Flow Manager:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Tool
     - Description
   * - ``dfm_show_tasks``
     - List all tasks in the loaded project
   * - ``dfm_show_task``
     - Get detailed information about a specific task
   * - ``dfm_show_packages``
     - List imported packages
   * - ``dfm_show_types``
     - List available task types
   * - ``dfm_show_skills``
     - List skills and personas
   * - ``dfm_context``
     - Return complete project context as JSON
   * - ``dfm_validate``
     - Validate the current flow definition
   * - ``dfm_run_tasks``
     - Execute one or more tasks

Coding Tools (yellow / green panels)
-------------------------------------

These general-purpose tools let the agent read and modify files:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Tool
     - Description
   * - ``shell_exec``
     - Run a shell command *(yellow — requires approval in auto mode)*
   * - ``write_file``
     - Write content to a file *(yellow — requires approval in auto mode)*
   * - ``apply_patch``
     - Apply a unified diff *(yellow — requires approval in auto mode)*
   * - ``read_file``
     - Read a file *(green)*
   * - ``list_directory``
     - List directory contents *(green)*
   * - ``grep_search``
     - Search file contents with a regex *(green)*

Subprocess Agents (Legacy)
===========================

The original subprocess-based agents (GitHub Copilot CLI, OpenAI Codex CLI)
are still supported via ``--assistant``:

.. code-block:: bash

    # GitHub Copilot CLI (must be installed separately)
    dfm agent -a copilot

    # OpenAI Codex CLI (must be installed separately)
    dfm agent -a codex

These agents communicate with DFM through a JSON result-file protocol and do
not have the streaming TUI or direct tool access.  They remain available for
environments where the native agent dependencies cannot be installed.

Troubleshooting
===============

``No module named 'agents'``
-----------------------------

The agent optional dependencies are not installed.

.. code-block:: bash

    pip install dv-flow-mgr[agent]

Authentication errors / ``401 Unauthorized``
--------------------------------------------

Verify your API key is exported in the current shell:

.. code-block:: bash

    echo $OPENAI_API_KEY      # should print your key
    echo $GITHUB_TOKEN        # for Copilot

For GitHub Copilot, re-run ``gh auth login`` if the token has expired.

``Rate limit reached``
----------------------

The agent will display a user-friendly message and the ``run_once`` path
automatically retries with exponential backoff.  In the TUI, wait a moment
and re-submit your message.

Copilot OAuth prompt in headless environments
---------------------------------------------

Set ``GITHUB_TOKEN`` explicitly to avoid the interactive OAuth device flow:

.. code-block:: bash

    export GITHUB_TOKEN=$(gh auth token)
    dfm agent -a native

Ollama model not responding
---------------------------

Ensure the Ollama server is running:

.. code-block:: bash

    ollama serve &
    ollama list           # confirm the model is pulled

Small models may time out on complex prompts.  Try a larger model or simplify
the query.

See Also
========

* :doc:`agent_integration` — Defining skills, personas, tools, and references
* :doc:`llm_integration` — General LLM integration guide
* :doc:`../cmdref` — Full command reference
* :doc:`../llms` — LLM call interface (server mode, parameter overrides)
