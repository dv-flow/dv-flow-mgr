##############
Configurations
##############

Real projects rarely have a single build. You need a *debug* build and a
*release* build; you switch between simulator vendors; you target different
platforms; you run a quick smoke test or a full regression. **Configurations**
let you capture these variants in one package -- selecting them at run time with
``-c`` -- instead of duplicating the flow or hand-editing parameters.

A configuration is a named overlay on the base package: it can set parameter
values, override tasks, inject new tasks into existing ones, extend tasks, and
add imports, fragments, types, or tasks -- all without touching the base
definition.

.. code-block:: bash

    dfm run build              # default
    dfm run build -c debug     # the 'debug' variant
    dfm run build -c release   # the 'release' variant

Defining a Configuration
========================

Configurations are declared in the package's ``configs`` field. Each entry
adjusts the base package for one variant:

.. code-block:: yaml

    package:
      name: my_project

      with:
        debug:
          type: bool
          value: false

      tasks:
      - name: build
        uses: std.Message
        with:
          msg: "Building in default mode"

      configs:
      - name: debug
        with:
          debug:
            value: true
        tasks:
        - name: build
          override: build
          with:
            msg: "Building in debug mode"

      - name: release
        with:
          debug:
            value: false
        overrides:
        - override: hdlsim
          with: hdlsim.xcelium

A configuration can specify:

* **with** -- parameter values for this configuration.
* **uses** -- a base configuration to inherit from (see `Inheriting
  Configurations`_).
* **overrides** -- package/parameter overrides.
* **extensions** -- task extensions (see `Modifying Tasks with Extensions`_).
* **tasks** -- additional or overriding tasks (including tasks that inject data
  via ``feeds`` -- see `Injecting Options with feeds`_).
* **types** -- additional or overriding types.
* **imports** / **fragments** -- additional imports or fragments for this
  configuration.

Selecting a Configuration
=========================

Choose a configuration on the command line with ``-c`` / ``--config``:

.. code-block:: bash

    dfm run build -c debug

When a configuration is selected, the merged definition is built in this order:

1. The base package is loaded.
2. Configuration parameters override package parameters.
3. Configuration overrides are applied.
4. Configuration tasks, types, imports, and fragments are merged.
5. The task graph is built from the merged definition.

Configuration values participate in the normal :doc:`parameter resolution
order <parameters>`, and command-line ``-D`` overrides still take precedence
over the selected configuration.

Inheriting Configurations
=========================

A configuration can build on another with ``uses``. This lets you layer
variants -- for example a ``debug`` configuration that starts from a shared
``instrumented`` base:

.. code-block:: yaml

    configs:
    - name: instrumented
      with:
        trace:
          type: bool
          value: true

    - name: debug
      uses: instrumented
      with:
        opt_level:
          value: 0

``debug`` inherits everything from ``instrumented`` (here, ``trace: true``) and
adds its own settings.

Injecting Options with ``feeds``
================================

A configuration often needs to add arguments, options, or data files to tasks
that are defined elsewhere (in the base package or an imported package). The
cleanest way to do this is the ``feeds`` field: a config adds a *new* task whose
output is injected into an existing task, **without modifying that task's
definition**.

``feeds`` is the inverse of ``needs`` -- where ``needs`` names a task's
dependencies, ``feeds`` declares "my output is an input to that task." Expressed
from a config, it connects a config-specific task into the base flow:

.. code-block:: yaml

    package:
      name: my_project

      tasks:
      - root: build
        uses: sim.SimImage
        needs: [rtl, tb]
        with:
          top: [tb_top]

      - root: run
        uses: sim.SimRun
        needs: [build]

      configs:
      - name: debug
        tasks:
          - name: debug_compile_args
            uses: hdlsim.SimCompileArgs
            with:
              args: ["-debug_access+all"]
            feeds: [my_project.build]

          - name: debug_run_args
            uses: hdlsim.SimRunArgs
            with:
              args: ["-gui"]
            feeds: [my_project.run]

With ``-c debug``, the ``build`` task additionally receives the
``-debug_access+all`` compile arguments and ``run`` receives ``-gui`` -- yet
neither ``build`` nor ``run`` was edited.

Key points:

* ``feeds`` injects data "from the side" into a task without changing its
  definition.
* The feed target is a fully-qualified task name (``package_name.task_name``).
* It is equivalent to adding the feeding task to the target's ``needs`` list,
  but expressed from the producer's perspective.
* This keeps the base flow clean: the configuration only *adds* tasks that
  connect to existing ones, which is easy to read and maintain.

Use ``feeds`` (inject from the side) when you want to add inputs/options to a
task; use **overrides** or **extensions** when you need to change a task's own
parameters or base.

Modifying Tasks with Extensions
===============================

Where ``feeds`` adds a new upstream input, an **extension** modifies an existing
task in place -- adding parameters, dependencies, or changing its base -- without
replacing the whole task. Extensions are typically defined inside a
configuration and are especially useful for augmenting tasks from imported
packages.

.. code-block:: yaml

    package:
      name: my_project

      imports:
      - hdlsim.vlt

      configs:
      - name: coverage
        extensions:
        - task: hdlsim.vlt.SimImage
          with:
            coverage:
              type: bool
              value: true
          needs:
          - coverage_setup

The extension above adds a ``coverage`` parameter and an extra dependency to the
imported ``hdlsim.vlt.SimImage`` task.

Extensions can:

* **Add parameters** -- introduce new options on the task.
* **Add dependencies** -- include additional ``needs``.
* **Change the base** -- specify a different ``uses`` base task.

Extensions can themselves inherit from other extensions with ``uses``, letting
you build up instrumentation incrementally:

.. code-block:: yaml

    configs:
    - name: base_instrumentation
      extensions:
      - task: my_tool.Compile
        with:
          verbose:
            type: bool
            value: false

    - name: debug_instrumentation
      uses: base_instrumentation
      extensions:
      - task: my_tool.Compile
        uses: base_instrumentation.my_tool.Compile
        with:
          verbose:
            value: true
          trace:
            type: bool
            value: true

Per-Configuration Imports
=========================

An import can itself select a configuration of the imported package via the
``config`` key, so a variant can propagate down the dependency tree:

.. code-block:: yaml

    imports:
    - name: hdlsim.vlt
      config: gui

What Configurations Enable
==========================

* **Build variants** -- debug, release, profiling builds.
* **Tool selection** -- switch between simulator/tool vendors.
* **Target platforms** -- customize for different deployment targets.
* **Test modes** -- normal vs. regression vs. continuous integration.

See Also
========

* :doc:`parameters` -- parameter declarations, overrides, and resolution order.
* :doc:`packages` -- the package namespace that hosts configurations.
* :doc:`running` -- selecting a configuration with ``-c`` at run time.
