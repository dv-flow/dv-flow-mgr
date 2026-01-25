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
* **graph**: Generate visual task dependency graphs
* **util**: Internal utility commands

Common Options
==============

These options are available across multiple commands:

``-D NAME=VALUE``
    Override parameter values from the command line. Can be specified multiple
    times to override multiple parameters.
    
    .. code-block:: bash
    
        dfm run build -D debug=true -D optimization=O3

``-c, --config NAME``
    Select a package configuration to use. Configurations allow switching between
    different build modes, tool chains, or deployment targets.
    
    .. code-block:: bash
    
        dfm run build -c debug

``--root PATH``
    Specify the root directory for the flow. By default, dfm searches upward
    from the current directory for a flow.dv or flow.yaml file.
    
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

    dfm show tasks [--package PKG] [--scope SCOPE] [--search KEYWORD] [--json]

Options:

``--package PKG``
    Filter tasks to a specific package.

``--scope {root,export,local}``
    Filter tasks by visibility scope.

Examples:

.. code-block:: bash

    # List all tasks
    dfm show tasks
    
    # Search for file-related tasks
    dfm show tasks --search file
    
    # List tasks in std package
    dfm show tasks --package std

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

Legacy Mode
-----------

For backward compatibility, the following legacy invocations are supported:

.. code-block:: bash

    # List project tasks (equivalent to: dfm show tasks --package <project>)
    dfm show
    
    # Show task with dependency tree (legacy behavior)
    dfm show <task> -a

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

.. image:: imgs/perfetto_trace_view.png

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

**Generate documentation graph:**

.. code-block:: bash

    dfm graph all -o project.dot
    dot -Tsvg project.dot -o project.svg

