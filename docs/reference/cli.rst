#################
Command reference
#################

.. argparse::
    :module: dv_flow.mgr.__main__
    :func: get_parser 
    :prog: dfm

Commands Overview
=================

DV Flow Manager provides several commands for working with flows:

* **run**: Execute tasks in a flow
* **show**: Display information about tasks
* **agent**: Launch AI assistants with DV Flow context
* **context**: Output project context for LLM agents
* **graph**: Generate visual task dependency graphs
* **store**: Inspect and manage the rundir store
* **util**: Internal utility commands

Common Options
==============

These options are available across multiple commands:

``-D NAME=VALUE``
    Override parameter values from the command line. Can be specified multiple
    times to override multiple parameters.

    .. code-block:: bash

        dfm run build -D debug=true -D optimization=O3

    ``-D`` (and the ``-P`` JSON parameter file) are explained in full -- syntax,
    targeting, and resolution order -- in :doc:`/guide/parameters`.

``--package-map FILE``
    Resolve imports by name using a package-map file (``name -> flow file``).
    May be specified multiple times; earlier maps take precedence on name
    collisions. A package map can also be supplied via the ``package-map:`` key
    in a flow file or the ``DV_FLOW_PACKAGE_MAP`` environment variable
    (colon-separated paths). See :doc:`/guide/packages` for the file format and
    precedence rules.

    .. code-block:: bash

        dfm --package-map deps/flow-packages.yaml run build

``-c, --config NAME``
    Select a package configuration to use. Configurations allow switching between
    different build modes, tool chains, or deployment targets.
    
    .. code-block:: bash
    
        dfm run build -c debug

``--root PATH``
    Specify the root directory for the flow. By default, dfm searches upward
    from the current directory for a flow.yaml file.
    
    .. code-block:: bash
    
        dfm run build --root /path/to/project

Run Command
===========

Execute one or more tasks in a flow.

.. code-block:: bash

    dfm run [OPTIONS] [TASKS...]

If no tasks are specified, dfm lists available tasks in the package.

Run Options
-----------

``-j N``
    Set the degree of parallelism (number of concurrent tasks). Default is to
    use all available CPU cores. Use ``-j 1`` for sequential execution.
    
    .. code-block:: bash
    
        dfm run build -j 4

``--clean``
    Remove the rundir directory before starting the build. Forces a complete
    rebuild of all tasks.
    
    .. code-block:: bash
    
        dfm run build --clean

``-f, --force``
    Force all tasks to run, ignoring up-to-date checks. Unlike ``--clean``,
    this preserves the rundir but marks all tasks as needing execution.
    
    .. code-block:: bash
    
        dfm run test -f

``-v, --verbose``
    Show all tasks including those that are up-to-date. By default, only tasks
    that execute are shown.
    
    .. code-block:: bash
    
        dfm run build -v

``-u, --ui {log,progress,tui}``
    Select the console user interface style:
    
    * **log**: Plain text output (default for non-terminals)
    * **progress**: Progress bars and live updates (default for terminals)
    * **tui**: Full-screen text user interface
    
    .. code-block:: bash
    
        dfm run build -u tui

``--override TARGET=REPLACEMENT``
    Replace a task in the graph with another task for this run. Can be
    specified multiple times. Overrides applied via ``--override`` take
    precedence over config-level and package-level overrides.
    
    .. code-block:: bash
    
        dfm run build --override sim_pkg.Compile=std.Null
    
    Multiple overrides:
    
    .. code-block:: bash
    
        dfm run build --override pkg.TaskA=std.Null --override pkg.TaskB=std.Null

``--needs TASK``
    Supply an additional input to the task being run, as if it were in that
    task's ``needs:``. May be repeated. Applies only to the invoked task, and
    adds to its declared needs rather than replacing them. The name resolves
    like any task name on the command line, so a partial name or a variant cell
    key works.

    .. code-block:: bash

        dfm run hdlsim.prof.Analyze --needs my-proj.sim-img.prof

    Not supported when running against a daemon (``DFM_SERVER_SOCKET``): the
    server protocol carries only tasks, ``-D`` overrides and ``--timeout``, so
    the option is rejected rather than silently dropped.

``--runner BACKEND``
    Runner backend to use. ``local`` runs tasks in-process. Other backends
    (e.g. ``lsf``) require a running daemon. If omitted, auto-detects
    whether a daemon is running and delegates to it if so, otherwise uses
    local execution.
    
    .. code-block:: bash
    
        dfm run build --runner local


``--base-rundir PATH``
    Reuse compiled artifacts from a previous build's rundir.  Tasks that
    completed successfully in the base-rundir are satisfied without
    re-execution; their output is reconstructed from saved data and
    file paths are rewritten to reference the base-rundir.  The
    base-rundir is treated as read-only and trusted.

    This is essential for regression workflows where a build is performed
    once and many test runs reuse the compiled artifacts.

    .. code-block:: bash

        # Build once
        dfm run build

        # Run tests reusing the build (no recompilation)
        dfm run test_a --base-rundir /path/to/build/rundir
        dfm run test_b --base-rundir /path/to/build/rundir

    The environment variable ``DFM_BASE_RUNDIR`` is exported to child
    processes when this option is set.

    See :doc:`/guide/incremental` for full details on how base-rundir
    satisfaction works.

    The base-rundir may be a symlink (for example a rundir-store link); paths
    recorded through either the link or its resolved target are rewritten.

``--store DIR`` / ``--no-store``
    Place the rundir in the rundir store at ``DIR``, or use a local
    ``<package-root>/rundir``, overriding ``DFM_STORE`` and config files.
    See :doc:`/guide/rundir_store`.

``--store-recreate``
    If the ``rundir`` link is dangling (its store is missing), recreate it
    in the configured store instead of stopping with an error. Also
    ``DFM_STORE_RECREATE=1``.

``--report DIR``
    After the run completes, write a self-contained diagnostics bundle to
    ``DIR`` (per-task logs, markers, and status). This is intended for CI,
    where the rundir is ephemeral: publish ``DIR`` as a build artifact to
    retain diagnostics after the job ends.

    .. code-block:: bash

        dfm run sim.regress --report build/dfm-report

    See `Run Report Bundle`_ for the bundle layout and ``report.json`` schema.

    The report is assembled from the per-task ``exec_data.json`` each task
    writes to the shared rundir, so it works for any execution backend
    (local, daemon, or remote runners such as ``--runner lsf``).

``--run-id ID``
    Identifier for this run's output-data directory (``rundir/out/<ID>``),
    which holds the run record (``results.json``) and everything
    ``std.Publish`` tasks (and ``dfm-out publish`` calls) publish in the run.
    By default it is a local timestamp, ``YYYYMMDD-HHMMSS`` (with ``-2``,
    ``-3`` ... when two runs start in the same second); pin it to a CI build
    number or git SHA to give the run a stable, meaningful location. Re-copies
    of identical content are skipped when a run-id is reused.

    .. code-block:: bash

        dfm run release --run-id ${GITHUB_RUN_NUMBER}

``--no-results``
    Don't write the run record (``rundir/out/<run-id>/results.json`` and
    ``summary.md``). By default every run writes one and prints its path as
    the last line (``Results: rundir/out/<id>/results.json``); the line is left
    out when the task's output is a machine-readable payload
    (``tests-info --json``). See :doc:`results`.

``--no-results-tree``
    Don't build the ``rundir/out/<run-id>/results/`` link tree (the record is
    still written). Same as ``results.tree: false`` in the config.

``--results-format FMT``
    Also write the run record as ``FMT`` next to ``results.json``: ``junit``
    (``junit.xml``), ``ctrf`` (``ctrf.json``), ``md``. Comma-separated or
    repeated. Overrides ``results.formats`` in the config and
    ``DFM_RESULTS_FORMATS``.

    .. code-block:: bash

        dfm run tests --results-format junit,ctrf

Run Examples
------------

**Build a single task:**

.. code-block:: bash

    dfm run sim-image

**Build multiple tasks:**

.. code-block:: bash

    dfm run compile test lint

**Force rebuild with 4 parallel jobs:**

.. code-block:: bash

    dfm run all --clean -j 4

**Run with debug configuration:**

.. code-block:: bash

    dfm run build -c debug -D trace=true

Show Command
============

The show command provides discovery and inspection of packages, tasks, types, and tags.
It supports both human-readable and machine-parseable (JSON) output for Agent consumption.

.. code-block:: bash

    dfm show [SUBCOMMAND] [OPTIONS]

Sub-Commands
------------

The show command supports the following sub-commands:

* **packages** - List and search available packages
* **tasks** - List and search tasks across packages
* **task <name>** - Display detailed information about a specific task
* **types** - List data types and tags
* **tags** - List tag types and their usage
* **package <name>** - Display detailed information about a package
* **project** - Display current project structure
* **results** - Show a run's results (``rundir/out/<run-id>/results.json``)
* **site-config** - Show config files, site-config plugins and the rundir
  store decision (see :doc:`site_config`)

Common Options
--------------

These options are available across most show sub-commands:

``--search KEYWORD``
    Search by keyword in name, description, and documentation fields.
    Case-insensitive substring matching.

``--regex PATTERN``
    Search by Python regex pattern in description and documentation.

``--tag TAG``
    Filter by tag. Format: ``TagType`` or ``TagType:field=value``.

``--json``
    Output in JSON format for programmatic consumption by Agents.

``-v, --verbose``
    Show additional details including full documentation and parameters.

Show Packages
-------------

List and search available packages.

.. code-block:: bash

    dfm show packages [--search KEYWORD] [--json] [-v]

Examples:

.. code-block:: bash

    # List all packages
    dfm show packages
    
    # Search for verification packages
    dfm show packages --search verification
    
    # JSON output for scripting
    dfm show packages --json

Show Tasks
----------

List and search tasks across all packages.

.. code-block:: bash

    dfm show tasks [--package PKG] [--scope SCOPE] [--produces PATTERN] [--search KEYWORD] [--json]

Options:

``--package PKG``
    Filter tasks to a specific package.

``--scope {root,export,local}``
    Filter tasks by visibility scope.

``--produces PATTERN``
    Filter tasks by produces pattern. Use comma-separated key=value pairs
    to specify the pattern. All specified attributes must match (AND logic),
    but tasks can have additional attributes (subset matching).
    
    .. code-block:: bash
    
        # Find tasks that produce std.FileSet
        dfm show tasks --produces "type=std.FileSet"
        
        # Find tasks that produce verilog files
        dfm show tasks --produces "type=std.FileSet,filetype=verilog"
        
        # Find vendor-specific outputs
        dfm show tasks --produces "type=std.FileSet,filetype=verilog,vendor=synopsys"

Examples:

.. code-block:: bash

    # List all tasks
    dfm show tasks
    
    # Search for file-related tasks
    dfm show tasks --search file
    
    # List tasks in std package
    dfm show tasks --package std
    
    # Find tasks that produce FileSet outputs
    dfm show tasks --produces "type=std.FileSet"

Show Task Detail
----------------

Display detailed information about a specific task.

.. code-block:: bash

    dfm show task <name> [--needs [DEPTH]] [--json] [-v]

Options:

``--needs [DEPTH]``
    Show the needs (dependency) chain for this task. Optional DEPTH limits 
    traversal levels (-1 or omitted for unlimited).

Examples:

.. code-block:: bash

    # Show task details
    dfm show task std.FileSet
    
    # Show task with full needs chain
    dfm show task myproject.build --needs
    
    # Show needs chain limited to 2 levels
    dfm show task myproject.build --needs 2
    
    # JSON output with full details
    dfm show task std.FileSet --json

The task detail output includes:

* **Name and Package**: Full task name and containing package
* **Base**: Task inheritance (uses relationship)
* **Scope**: Visibility (root, export, local)
* **Description and Documentation**: Task purpose and usage
* **Parameters**: Task parameters with types and defaults
* **Produces**: Output dataset patterns this task creates (see :doc:`/guide/dataflow`)
* **Consumes**: Input dataset patterns this task accepts
* **Direct Needs**: Immediate dependencies

Example output showing produces:

.. code-block:: text

    Task:        my_flow.VerilogCompiler
    Package:     my_flow
    Base:        -
    Scope:       -
    
    Description:
      Compiles Verilog RTL with optimization
    
    Parameters:
      optimization  str     O2    Optimization level
    
    Produces:
      - type=std.FileSet, filetype=verilog, optimization=O2
    
    Direct Needs:
      - my_flow.SourceFiles

Show Types
----------

List data types and tag types.

.. code-block:: bash

    dfm show types [--tags-only] [--data-items-only] [--search KEYWORD]

Options:

``--tags-only``
    Show only tag types (types deriving from std.Tag).

``--data-items-only``
    Show only data item types (types deriving from std.DataItem).

Show Tags
---------

List tag types and their usage counts.

.. code-block:: bash

    dfm show tags [--search KEYWORD] [--json]

Show Package Detail
-------------------

Display detailed information about a specific package.

.. code-block:: bash

    dfm show package <name> [--json] [-v]

Show Project
------------

Display information about the current project.

.. code-block:: bash

    dfm show project [--imports] [--configs] [--json] [-v]

Options:

``--imports``
    Show detailed import information.

``--configs``
    Show available configurations.

Show Results
------------

Read a run record (see :doc:`results`).

.. code-block:: bash

    dfm show results [--rundir R] [--run ID|latest] [--list] [--failures]
                     [--json] [--depth N] [--all] [--format FMT] [-o FILE]

With no options it prints the latest run as a tree: a status, the name, the
headline and a few metrics per node. Passing subtrees collapse to one line, and
a failing node shows its failing checks, first errors, log location and waves.
A missing record exits with status 1.

``--rundir R``
    The run directory to read (default ``<package-root>/rundir``, as ``dfm run`` uses).

``--run ID``
    The run to show; ``latest`` (the default) follows ``out/latest``, or the
    newest record when the link is missing.

``--list``
    List the recorded runs, newest first: id, status, root and pass count.

``--failures``
    Only the failures: path, status, headline, failing checks, ``log:
    path:line`` and waves.

``--json``
    Print ``results.json``. Artifacts are checked against their recorded
    mtime/size: each stamp gets ``state`` (``ok``, ``stale`` or ``missing``)
    and each artifact ``stale``. With ``--failures``, print only the
    ``summary`` block.

``--depth N``
    Descend at most N levels below the root.

``--all``
    Expand passing subtrees too.

``--format {text,json,junit,ctrf,md}``
    Render the record in another format (``--json`` is ``--format json``).

``-o, --output FILE``
    Write to ``FILE`` instead of stdout.

.. code-block:: bash

    dfm show results --failures
    dfm show results --json --failures | jq '.failures[0].log'

Legacy Mode
-----------

For backward compatibility, the following legacy invocations are supported:

.. code-block:: bash

    # List project tasks (equivalent to: dfm show tasks --package <project>)
    dfm show
    
    # Show task with dependency tree (legacy behavior)
    dfm show <task> -a

Store Command
=============

``dfm store`` inspects and manages the rundir store. See
:doc:`/guide/rundir_store` for concepts and :doc:`site_config` for
configuration.

``dfm store info [--json] [--size] [--store DIR | --no-store]``
    Show the store in effect, every config layer consulted and what it said,
    and the state of the current project's rundir (``none``, ``local``,
    ``ok``, ``dangling``, ``copied``, ``moved``, ``unmanaged-symlink``).
    ``--size`` measures the rundir and shows its largest top-level
    directories.

``dfm store init DIR [--shared | --group]``
    Create a store root and its ``.dfm-store.yaml`` marker. ``--shared``
    sets mode 1777 (sticky, like ``/tmp``); ``--group`` sets 2775.

Selection options shared by ``list``, ``stats``, ``candidates`` and ``gc``:
``--store DIR`` (default: the configured store), ``--user U`` /
``--all-users`` (default: your own entries), ``--larger-than SIZE``,
``--package GLOB``, ``--host GLOB`` and (except ``gc``, where it is a
criterion) ``--older-than AGE``. Sizes accept ``500M``, ``10G``, ``1.5T``;
ages accept ``30d``, ``12h``, ``2w``. Size options: ``--size`` / ``--refresh``
(``list``), ``--no-measure`` / ``--refresh`` (others). All accept ``--json``
(``"schema": 1``; bytes, ISO-8601 UTC times, ages in seconds).

``dfm store list [--status S] [--sort name|size|last-used|created] [--limit N] [-l/--long] [--format table|names|links|paths]``
    One row per entry: status, size and share, last used, created, number of
    sessions, host, package and project. ``--long`` shows a detail block per
    entry (git, last modification, file count, largest directories, paths).

``dfm store stats [--top N] [--stale AGE]``
    Filesystem usage, totals, breakdowns by status, last use, project, user
    and host with bar charts, the largest entries, the reclaimable space and
    suggested commands.

``dfm store candidates [--tier safe|review] [--stale AGE] [--limit N] [--format table|names|links|paths] [--annotate] [--force]``
    Entries worth deleting, biggest first. ``safe``: the project is gone or
    no longer links here. ``review``: unverifiable from this host, or unused
    for ``--stale`` (default 30d). ``--format names --annotate`` produces a
    file for ``gc --from``.

``dfm store gc [ENTRY...] [--from FILE] [--orphans] [--older-than AGE] [--include-unknown] [--reclaim SIZE] [--target-free SIZE] [-n/--dry-run] [-y] [--force]``
    Delete entries. With no criteria, selects orphaned and retargeted
    entries. ``--older-than`` alone selects all entries unused that long;
    with ``--orphans`` both must hold. ``--reclaim`` / ``--target-free`` keep
    only as much of the selection as needed (dead entries first, then least
    recently used). ``ENTRY`` and ``--from`` name entries explicitly (entry
    names, entry paths or project link paths; ``-`` reads stdin). Prints the
    plan and asks for confirmation unless ``-y``; never deletes busy or
    unmanaged entries, nor (without ``--force``) entries used in the last
    hour. Refuses a directory without a store marker.

``dfm store migrate [--store DIR] [-n]``
    Move the project's local rundir into the store and replace it with a
    link.

``dfm store unlink [--local] [--keep]``
    Remove the rundir link; ``--local`` moves the contents back into a local
    directory; ``--keep`` leaves the store entry for ``gc``.

``dfm store relink [--store DIR]``
    Move the project's entry to the configured store (or ``DIR``), or
    recreate a dangling link there.

Validate Command
================

The validate command checks your flow definition for errors and potential issues,
including dataflow compatibility between tasks.

.. code-block:: bash

    dfm validate [--json]

The validator performs the following checks:

1. **Syntax Validation**: YAML/DV parsing and schema validation
2. **Undefined References**: Detects references to non-existent tasks
3. **Circular Dependencies**: Detects circular task dependencies
4. **Dataflow Compatibility**: Checks produces/consumes patterns between connected tasks
5. **Unused Tasks**: Warns about tasks that are defined but never referenced

Validation Output
-----------------

**Errors** prevent the workflow from executing:

* Parse errors in flow definition
* Undefined task references
* Circular dependencies

**Warnings** indicate potential issues but allow execution:

* Dataflow mismatches (produces/consumes incompatibility)
* Unused tasks
* Missing optional declarations

Example output:

.. code-block:: text

    Package: my_flow
      Tasks: 8
      Types: 3
    
    Warnings (1):
      WARNING: Task 'Simulator' consumes [{'type': 'std.FileSet', 'filetype': 'vhdl'}]
               but 'VerilogCompiler' produces [{'type': 'std.FileSet', 'filetype': 'verilog'}].
               No consume pattern matches any produce pattern.
    
    ✓ Validation passed
      (1 warning(s))

JSON Output
-----------

Use ``--json`` for programmatic consumption:

.. code-block:: bash

    dfm validate --json

.. code-block:: json

    {
      "valid": true,
      "errors": [],
      "warnings": [
        {
          "type": "DataflowMismatch",
          "message": "Task 'Simulator' consumes ... but 'VerilogCompiler' produces ...",
          "producer": "my_flow.VerilogCompiler",
          "consumer": "my_flow.Simulator"
        }
      ],
      "info": [
        {
          "type": "PackageInfo",
          "name": "my_flow",
          "task_count": 8,
          "type_count": 3
        }
      ],
      "error_count": 0,
      "warning_count": 1
    }

Dataflow Validation
-------------------

The validator checks that produces patterns from producer tasks match the
consumes patterns of consumer tasks. See :doc:`/guide/dataflow` for details
on compatibility rules.

**Compatibility Rules:**

* Consumer with ``consumes: all`` accepts any produces
* Producer with no produces declared is assumed compatible
* **OR Logic**: If ANY consume pattern matches ANY produce pattern, the dataflow is valid
* Pattern matching uses subset logic (producer can have extra attributes)

**When to fix warnings:**

* The consumer truly needs different data than what's produced
* There's a typo in task names or pattern attributes
* You want strict validation for production workflows

**When to accept warnings:**

* Outputs are dynamic and not known until runtime
* The mismatch is intentional (flexible workflow)
* You're in early development/prototyping

See Also
--------

* :doc:`/guide/dataflow` - Complete dataflow and produces documentation
* ``dfm show task <name>`` - View task produces/consumes patterns

Agent Command
=============

Launch an AI assistant with DV Flow context, including skills, personas, tools, and references.

.. code-block:: bash

    dfm agent [OPTIONS] [TASKS...]

The agent command configures and launches an AI assistant (GitHub Copilot CLI, OpenAI Codex, etc.)
with project-specific context. When you specify task references, dfm evaluates those tasks and
their dependencies to collect agent resources (skills, personas, tools, references), then generates
a comprehensive system prompt for the AI assistant.

Agent Options
-------------

``-a, --assistant {claude,copilot,codex,mock,native}``
    Specify which AI assistant to use. If not specified, dfm auto-detects the available
    assistant by checking for installed tools in this order: claude, copilot, codex.

    .. code-block:: bash

        dfm agent PiratePersona --assistant claude

``-m, --model MODEL``
    Specify the AI model to use. If omitted, the assistant's own default model is
    used -- dfm does not substitute a model of its own. The format depends on the
    assistant:

    * **Claude**: Aliases like ``opus``, ``sonnet``, or a full model name
    * **Copilot**: Model names like ``gpt-4``, ``gpt-3.5-turbo``
    * **Codex**: OpenAI model identifiers

    .. code-block:: bash

        dfm agent PiratePersona --model opus

``--clean``
    Clean the rundir before executing tasks. Useful when you want to ensure
    fresh evaluation of all agent resource tasks.
    
    .. code-block:: bash
    
        dfm agent MyPersona --clean

``--ui {log,progress,tui}``
    Select UI mode for task execution during context building:
    
    * **log**: Plain text output
    * **progress**: Progress bars (default for terminals)
    * **tui**: Full-screen interface
    
    .. code-block:: bash
    
        dfm agent MyPersona --ui progress

``--json``
    Output the collected context as JSON instead of launching the assistant.
    Useful for debugging or integration with custom tools.
    
    .. code-block:: bash
    
        dfm agent PiratePersona --json

``--config-file FILE``
    Write the system prompt to FILE instead of launching the assistant.
    Useful for reviewing what context will be provided to the agent.
    
    .. code-block:: bash
    
        dfm agent PiratePersona --config-file context.md

Agent Resources
---------------

The agent command recognizes four types of agent resources defined in your flow:

**AgentSkill**
    A capability or knowledge domain that the agent should possess. Skills are
    typically documented in markdown files that describe commands, APIs, or 
    domain-specific knowledge.
    
    .. code-block:: yaml
    
        tasks:
        - local: SwordPlaySkill
          uses: std.AgentSkill
          desc: Playbook of sword fighting moves
          with:
            files:
            - "${{ srcdir }}/sword_skill.md"

**AgentPersona**
    A character or role that the agent should adopt. Personas can depend on
    skills to combine capabilities with personality.
    
    .. code-block:: yaml
    
        tasks:
        - local: PiratePersona
          uses: std.AgentPersona
          needs: SwordPlaySkill
          desc: |
            I'm a crusty pirate with a tankard of rum and a 
            parrot on me shoulder. If you're feeling feisty,
            I'll show you my skill at fighting

**AgentTool**
    An MCP (Model Context Protocol) server or external tool that the agent
    can invoke.
    
    .. code-block:: yaml
    
        tasks:
        - local: FileSystemTool
          uses: std.AgentTool
          desc: File system operations
          with:
            command: mcp-server-filesystem
            args: ["--root", "${{ rootdir }}"]

**AgentReference**
    Documentation or reference material that the agent should consult.
    
    .. code-block:: yaml
    
        tasks:
        - local: APIReference
          uses: std.AgentReference
          desc: Project API documentation
          with:
            files:
            - "${{ srcdir }}/api_docs.md"

Agent Examples
--------------

**Launch agent with a persona:**

.. code-block:: bash

    dfm agent PiratePersona

This evaluates the PiratePersona task and all its dependencies (like SwordPlaySkill),
generates a system prompt with the persona description and skill documentation, then
launches the configured AI assistant.

**Launch with multiple contexts:**

.. code-block:: bash

    dfm agent PiratePersona CodingSkill TestingSkill

Combines multiple personas and skills into a single agent session.

**Preview context without launching:**

.. code-block:: bash

    dfm agent PiratePersona --config-file preview.md
    cat preview.md

**Debug context collection:**

.. code-block:: bash

    dfm agent PiratePersona --json | jq

**Use specific model:**

.. code-block:: bash

    dfm agent PiratePersona --model gpt-4 --assistant copilot

**Force fresh evaluation:**

.. code-block:: bash

    dfm agent MyPersona --clean

Agent Workflow
--------------

When you run ``dfm agent``, the following steps occur:

1. **Task Resolution**: Resolve task references to task definitions
2. **Graph Building**: Build dependency graph for all referenced tasks
3. **Task Execution**: Execute tasks to evaluate agent resources
4. **Resource Collection**: Extract skills, personas, tools, and references
5. **Prompt Generation**: Generate comprehensive system prompt with:
   
   * Project information
   * Available dfm commands
   * Skill documentation
   * Persona descriptions
   * Reference materials
   * Tool configurations

6. **Assistant Launch**: Launch AI assistant with context in interactive mode

Context Command
===============

Output project context information for LLM agents.

.. code-block:: bash

    dfm context [OPTIONS]

The context command generates comprehensive information about your DV Flow Manager
project in a format optimized for consumption by AI assistants. This is useful for
providing project awareness to LLM tools.

Context Options
---------------

``--root PATH``
    Specify the root directory for the flow.

Output includes:

* Project name and description
* Package structure and imports
* Available tasks with descriptions
* Type definitions
* Configuration options

Example:

.. code-block:: bash

    dfm context

Graph Command
=============

Generate a visual representation of task dependencies.

.. code-block:: bash

    dfm graph [OPTIONS] [TASK]

The graph command creates a dependency graph in various output formats.

Graph Options
-------------

``-f, --format {dot}``
    Specify the output format. Currently supports:
    
    * **dot**: GraphViz DOT format (default)
    
    .. code-block:: bash
    
        dfm graph build -f dot

``-o, --output FILE``
    Specify the output file. Use ``-`` for stdout (default).
    
    .. code-block:: bash
    
        dfm graph build -o build_graph.dot

Graph Examples
--------------

**Generate a graph and visualize with GraphViz:**

.. code-block:: bash

    dfm graph build -o build.dot
    dot -Tpng build.dot -o build.png

**Generate and display in one command:**

.. code-block:: bash

    dfm graph build | dot -Tpng | display

Util Command
============

Utility commands.

.. code-block:: bash

    dfm util schema [-o FILE] [--generate] [--results]

``schema``
    Print a JSON Schema. By default it is the flow-definition schema
    (``dv.flow.schema.json``; ``--generate`` rebuilds it from the models).
    ``--results`` prints the run-record schema instead
    (``dvflow-results.schema.json``, for ``results.json``; see
    :doc:`results`).

UI Modes
========

DV Flow Manager provides three different console UI modes for the run command:

Log Mode
--------

Plain text output showing task execution. Best for:

* Non-interactive environments (CI/CD)
* Log file capture
* Debugging with verbose logging enabled

Output format:

.. code-block:: text

    >> [1] Task my_pkg.compile
    Compiling 10 files...
    << [1] Task my_pkg.compile (success) 2.45s

Progress Mode
-------------

Live updating progress display with progress bars. Best for:

* Interactive terminal sessions
* Monitoring long-running builds
* Parallel task visualization

Shows:

* Active tasks with progress bars
* Completed task count
* Estimated time remaining
* Real-time task status updates

TUI Mode
--------

Full-screen text user interface. Best for:

* Complex flows with many tasks
* Detailed monitoring of parallel execution
* Interactive navigation of task output

Features:

* Scrollable task list
* Task filtering and search
* Log viewing per task
* Status summaries

Select UI mode with the ``-u`` flag or let dfm auto-select based on terminal
capabilities.

Trace Output
============

DV Flow Manager generates execution traces in Google Event Trace Format,
compatible with the Perfetto trace viewer and Chrome's about:tracing.

Trace files are automatically created in the log directory as:

.. code-block:: text

    log/<root_task>.trace.json

Viewing Traces
--------------

**Using Perfetto UI** (recommended):

1. Visit https://ui.perfetto.dev/
2. Click "Open trace file"
3. Load the .trace.json file

**Using Chrome:**

1. Navigate to chrome://tracing
2. Click "Load" and select the trace file

Trace Information
-----------------

Traces include:

* Task execution timeline
* Parallel execution visualization
* Task duration and scheduling
* Dependencies and dataflow
* Execution status and results

Use traces to:

* Identify bottlenecks
* Optimize parallelism
* Debug scheduling issues
* Understand execution patterns

Run Report Bundle
=================

When ``dfm run`` is invoked with ``--report DIR``, a diagnostics bundle is
written to ``DIR`` after the run completes. Logs and markers are normally
written into the per-task rundir, which is ephemeral in CI; the report bundle
gathers the small, always-useful diagnostic subset into one location that a CI
job can publish as an artifact.

Unlike uploading the whole rundir (which can contain large build/simulation
artifacts), the bundle leads with a structured status/marker manifest and
includes per-task logs as drill-down.

The bundle is assembled from the ``exec_data.json`` that each task writes into
its rundir (status, markers, and the name of its logfile). Because this is the
same on-disk record used for up-to-date checks, the report is backend-agnostic:
it works identically for local, daemon, and remote (e.g. LSF) execution, and a
report can even be regenerated from a preserved rundir after the fact.

Bundle Layout
-------------

.. code-block:: text

    <report-dir>/
      report.json          # machine-readable manifest (primary surface)
      report.md            # human-readable summary (CI job-summary friendly)
      markers.jsonl        # all markers flattened, one JSON object per line
      logs/
        <task-name>.log    # per-task logs, copied from each task's rundir

report.json Schema
------------------

.. code-block:: json

    {
      "schema": "dvflow-report/1",
      "root": "sim.regress",
      "status": 1,
      "generated_unix": 1750464000,
      "counts": {
        "tasks_total": 42,
        "tasks_failed": 1,
        "markers": { "info": 3, "warning": 5, "error": 2 }
      },
      "tasks": [
        {
          "name": "sim.build",
          "status": 0,
          "changed": true,
          "cache_hit": false,
          "rundir": "/abs/path/rundir/sim.build",
          "log": "logs/sim.build.log",
          "markers": [
            { "severity": "error", "msg": "...",
              "loc": { "path": "...", "line": 12, "pos": 4 } }
          ]
        }
      ]
    }

Notes:

* ``status`` is the number of tasks that failed (0 means success).
* ``tasks`` includes every task that ran, including up-to-date and cache-hit
  tasks. The ``log`` field is omitted (``null``) when a task produced no
  logfile (e.g. pure-Python tasks).
* Each task's ``markers`` are also aggregated into ``markers.jsonl`` with an
  added ``"task"`` field, for easy log-style scanning.

CI Usage
--------

Publish the bundle as a build artifact. For GitHub Actions:

.. code-block:: yaml

    - name: Run flow
      run: dfm run sim.regress --report build/dfm-report

    - name: Upload report
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: dfm-report
        path: build/dfm-report

The ``if: always()`` ensures the report is uploaded even when the run fails,
which is exactly when the logs and markers are most useful.

Output Directory Structure
==========================

DV Flow Manager creates an output directory structure that mirrors
the task graph being executed. Each top-level task has a 
directory within the run directory. Compound tasks have a nested
directory structure.

There are two top-level directory that always exist:

* cache - Stores task memento data and other cross-run artifacts
* log - Stores execution trace and log files

Each task directory contains some standard files:

* <task_name>.exec_data.json - Information about the task inputs, outputs, and executed commands.
* logfiles - Command-specific log files


Viewing Task Execution Data
===========================

After a run has completed, the `log` directory will contain a JSON-formatted execution
trace file named <root_task>.trace.json. This file is formatted in 
`Google Event Trace Format <https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU/preview?tab=t.0#heading=h.yr4qxyxotyw>`_,
and can be processed by tools from the `Perfetto <https://perfetto.dev/>`_ project.

An execution is shown in the Perfetto UI below. In addition to seeing information
about how tasks executed with respect to each other, data about individual
tasks can be seen.

.. image:: /imgs/perfetto_trace_view.png

Common Patterns
===============

Here are some common command patterns for typical workflows:

**Quick incremental build:**

.. code-block:: bash

    dfm run

**Clean build for release:**

.. code-block:: bash

    dfm run all --clean -c release

**Debug single task:**

.. code-block:: bash

    dfm run problematic_task -f -j 1 -u log

**Monitor long build:**

.. code-block:: bash

    dfm run all -u tui

**Check what would run:**

.. code-block:: bash

    dfm show target_task -a

**Override parameters for testing:**

.. code-block:: bash

    dfm run test -D test_name=smoke -D seed=42

**Stub out expensive tasks for fast iteration:**

.. code-block:: bash

    dfm run test -c fast
    # or, ad-hoc from the command line:
    dfm run test --override sim_pkg.Compile=std.Null

**Generate documentation graph:**

.. code-block:: bash

    dfm graph all -o project.dot
    dot -Tsvg project.dot -o project.svg
