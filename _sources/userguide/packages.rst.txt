########
Packages
########

Packages are the fundamental organizational unit in DV Flow. A package is a
**parameterized namespace** that defines tasks, types, and configuration. Packages
serve two key purposes:

* **Organization** - Group related tasks and provide a namespace to avoid name conflicts
* **Reusability** - Enable sharing and reuse of task definitions across projects

Package Structure
=================

Each package has a unique name and contains zero or more tasks. The minimal
package definition looks like this:

.. code-block:: yaml

    package:
        name: my_project

        tasks:
        - name: task1
          uses: std.Message
          with:
            msg: "Hello from my_project!"

Built-in Packages
=================

DV Flow Manager includes the **std** package as part of its core installation.
The std package provides fundamental tasks that are commonly used across all flows:

* **std.FileSet** - Collect files matching patterns
* **std.Message** - Display messages during execution
* **std.CreateFile** - Create files from literal content
* **std.SetEnv** - Set environment variables
* **std.IncDirs** - Extract include directories from filesets

Shell commands are executed by specifying ``shell: bash`` with ``run:``.

The std package is always available and does not require an explicit import.

Plugin Packages
---------------

Additional packages are installed as **Python plugins** using Python's entry point
mechanism. When DV Flow Manager starts, it automatically discovers and loads all
packages registered under the ``dv_flow.mgr`` entry point group.

Common plugin packages include:

* **hdlsim** packages - HDL simulation support (Verilator, Xcelium, VCS, etc.)
* **pss** packages - Portable Stimulus Specification (PSS) support
* **ide** packages - IDE integration (file lists, etc.)

Installing Plugin Packages
---------------------------

Plugin packages are typically installed via ``pip`` alongside dv-flow-mgr:

.. code-block:: bash

    pip install dv-flow-libhdlsim  # HDL simulator support
    pip install dv-flow-libpss     # PSS support

Once installed, plugin packages are automatically discovered and their tasks
become available without explicit imports.

Creating Plugin Packages
-------------------------

To create your own plugin package, add an entry point in your ``pyproject.toml``:

.. code-block:: toml

    [project.entry-points."dv_flow.mgr"]
    my_plugin = "my_package.plugin"

Your plugin module should provide a ``dfm_packages()`` function that returns
a dictionary mapping package names to their flow.yaml file paths:

.. code-block:: python

    # my_package/plugin.py
    import os

    def dfm_packages():
        pkg_dir = os.path.dirname(__file__)
        return {
            "my_tool": os.path.join(pkg_dir, "flow.yaml")
        }

See the developer documentation for complete details on creating plugin packages.

Using Built-in and Plugin Packages
-----------------------------------

All packages are referenced using dot notation, independent of their source:

.. code-block:: yaml

    tasks:
    - name: files
      uses: std.FileSet
      with:
        include: "*.sv"
    
    - name: sim
      uses: hdlsim.vlt.SimImage
      needs: [files]

Importing Packages
==================

Packages can import other packages to use their tasks and extend their functionality.
There are several ways to import packages:

Import by Path
--------------

Import a package from a file or directory path:

.. code-block:: yaml

    package:
        name: top

        imports:
        - subdir/flow.yaml
        - packages/my_lib

        tasks:
        - name: use_imported
          uses: my_lib.some_task

When a directory is specified, DV Flow searches for ``flow.dv`` or ``flow.yaml`` 
files in the subdirectory tree.

Import with Explicit Location
-----------------------------

Combine ``name`` with ``from`` to import a package by name while pinning the exact
file that defines it (no package map required):

.. code-block:: yaml

    package:
        name: top

        imports:
        - name: hdlsim.vlt
          from: ../vendor/vlt/flow.dv

        tasks:
        - name: build
          uses: hdlsim.vlt.SimImage

The pinned name/location takes precedence over any map or registry entry for the
same name. The file's declared ``package.name`` must match the ``name`` given.

Import with Alias
-----------------

Use the ``as`` keyword to give an imported package an alias. The alias can then be
used to qualify the package's tasks, types, and parameters:

.. code-block:: yaml

    package:
        name: proj

        imports:
        - name: hdlsim.vlt
          as: sim

        tasks:
        - name: build
          uses: sim.SimImage  # References hdlsim.vlt.SimImage

Aliases are local to the importing package. Two imports cannot share the same
alias, and an alias cannot collide with an existing package name.

Import by Name
--------------

A package can be imported by **name** alone, leaving its location to be resolved
through a package map (see below), the package registry, or ``DV_FLOW_PATH``:

.. code-block:: yaml

    package:
        name: top

        imports:
        - name: my_lib

        tasks:
        - name: build
          uses: my_lib.some_task

Importing by name decouples the importing project from where the dependency lives
on disk — useful when dependencies are fetched into a workspace by a package
manager rather than checked in at a fixed path.

Import Resolution
-----------------

When resolving imports, DV Flow searches in the following order:

1. **Relative to current file** - Paths relative to the importing package's location
2. **Relative to project root** - Allows sibling packages to find each other
3. **Package maps** - ``name -> flow file`` entries from declared package maps
4. **Package registry** - Built-in and installed packages, and ``DV_FLOW_PATH``

This allows sub-packages to import sibling packages naturally:

.. code-block:: yaml

    # In packages/ip1/flow.yaml
    package:
        name: ip1
        imports:
        - packages/ip2/flow.yaml  # Finds sibling relative to project root

Package Maps
============

A **package map** is a generated file that lists the packages contributed by a
dependency tree, keyed by name. It lets a project import dependencies by name
without hard-coding their paths. A map is a pure ``name -> flow file`` directory:

.. code-block:: yaml

    # deps/flow-packages.yaml  (generated)
    package-map:
      version: 1
      packages:
        - name: hdl.sim.vcs
          path: hdl_sim_vcs/flow.dv
        - name: uvm.util
          path: uvm_util/flow.yaml

Each ``path`` is resolved relative to the directory containing the map file.

A project references one or more maps via the ``package-map`` key, which accepts a
single path or a list (earlier entries take precedence on name collisions):

.. code-block:: yaml

    package:
        name: my_project
        package-map: deps/flow-packages.yaml
        # — or — multiple maps:
        # package-map:
        # - deps/flow-packages.yaml
        # - ../shared/flow-packages.yaml
        imports:
        - name: hdl.sim.vcs
        - name: uvm.util

Maps can also be supplied without editing the flow file:

* command line: ``dfm --package-map deps/flow-packages.yaml run ...`` (repeatable)
* environment: ``DV_FLOW_PACKAGE_MAP`` (a ``:``-separated list of map files)

**Precedence** (highest first): maps declared in the flow file, then ``--package-map``
maps, then ``DV_FLOW_PACKAGE_MAP`` maps, then the package registry / ``DV_FLOW_PATH``.

**Lazy loading.** A map registers package *names* without parsing any dependency, so
listing many available packages in a map is cheap. More generally, any import by
**name** is deferred: the dependency's ``flow`` file is parsed only when one of its
tasks, types, or parameters is first touched. (Unresolvable names are still reported at
load time, so a typo'd or missing dependency is not silently ignored.)

Two things still force a dependency to be parsed eagerly, by design:

* Building a task graph flattens *all* imported packages to resolve names, so
  ``dfm run``/``dfm graph`` parse every reachable import.
* Resolving an unqualified task/type name scans imported packages.

So lazy loading mainly benefits load-only operations (introspection, partial
validation) where an import is never referenced. Imports by **path** are always
parsed eagerly.

.. note::

    Package-map files are typically produced by a dependency manager (e.g. ivpm)
    when it syncs a project's dependencies. dv-flow consumes the map; generating it
    is the dependency manager's responsibility.

Package Parameters
==================

Packages can define parameters that control their behavior. Parameters can be
overridden when the package is imported or instantiated:

.. code-block:: yaml

    package:
        name: configurable_ip
        
        with:
          debug:
            type: int
            value: 0
          width:
            type: int
            value: 32

        tasks:
        - name: build
          uses: std.Message
          with:
            msg: "Building with width=${{ width }}, debug=${{ debug }}"

Package Fragments
=================

Large packages can be split into multiple files using **fragments**. Fragments
allow you to organize tasks across multiple files while maintaining a single
package namespace:

.. code-block:: yaml

    # Main package file
    package:
        name: big_project

        fragments:
        - src/rtl/flow.yaml
        - src/tb/flow.yaml
        - tests/

        tasks:
        - name: top_task
          needs: [rtl.build, tb.build]

Fragment files use the ``fragment`` keyword instead of ``package``:

.. code-block:: yaml

    # src/rtl/flow.yaml
    fragment:
        tasks:
        - name: build
          uses: std.FileSet
          with:
            include: "*.sv"

All fragments contribute to the same package namespace. Task names must be unique
across all fragments -- you cannot define ``build`` in multiple fragments of the
same package.

Fragment Fields
---------------

Fragments support most package-level constructs but not all.  The schema
uses ``extra = "forbid"``, so any unlisted field produces an error.

.. list-table:: Allowed Fragment Fields
   :header-rows: 1
   :widths: 20 10 70

   * - Field
     - Allowed?
     - Notes
   * - ``tasks``
     - Yes
     - Task definitions, same syntax as in a package
   * - ``types``
     - Yes
     - Data type definitions
   * - ``configs``
     - Yes
     - Configuration definitions
   * - ``imports``
     - Yes
     - Package imports
   * - ``filters``
     - Yes
     - Filter definitions
   * - ``fragments``
     - Yes
     - Nested fragment paths (hierarchical)
   * - ``name``
     - Yes
     - Optional; prefixes all task names with ``<package>.<name>.<task>``
   * - ``with``
     - **No**
     - Package-level parameters can only be declared in the root package
   * - ``desc``
     - **No**
     - Package description is set in the root package only

Nested Fragments
----------------

Fragments can reference other fragments, enabling a hierarchical directory
structure:

.. code-block:: yaml

    # Top-level flow.dv
    package:
      name: my_project
      fragments:
        - src/flow.dv
        - tb/flow.dv

    # src/flow.dv -- intermediate fragment
    fragment:
      fragments:
        - rtl/flow.dv
        - lib/flow.dv

    # src/rtl/flow.dv -- leaf fragment
    fragment:
      tasks:
        - name: rtl_sources
          uses: std.FileSet
          with:
            type: systemVerilogSource
            include: "*.sv"

Fragment paths are always relative to the file that contains the
``fragments:`` list.

Task Namespacing
================

Tasks within a package are referenced using dot notation: ``package_name.task_name``.

Local vs. Qualified References
-------------------------------

Within a package, you can reference tasks by their short name:

.. code-block:: yaml

    package:
        name: my_pkg

        tasks:
        - name: task1
          uses: std.Message
        
        - name: task2
          needs: [task1]  # Short name - refers to my_pkg.task1

From outside the package, use the fully-qualified name:

.. code-block:: yaml

    package:
        name: top
        
        imports:
        - packages/my_pkg

        tasks:
        - name: runner
          needs: [my_pkg.task1]  # Fully-qualified reference

Best Practices
==============

**Package Organization**

* Use packages to group related tasks by function (e.g., RTL compilation, verification, synthesis)
* Keep package names short but descriptive
* Use fragments for large packages to improve maintainability

**Reusability**

* Make packages parameterizable when they need to work in different contexts
* Document package parameters and their effects
* Avoid hard-coded paths - use parameters or dataflow

**Dependencies**

* Import only the packages you need
* Use aliases to simplify long package names
* Keep import chains shallow when possible

**Naming**

* Use descriptive task names that indicate their purpose
* Avoid generic names like ``task1``, ``task2``
* Use consistent naming conventions across related packages


Package Configurations
======================

Packages can define multiple configurations that customize behavior for
different scenarios (debug builds, different tools, deployment targets, etc.).
Configurations provide a way to organize variations without duplicating
the core package definition.

Defining Configurations
-----------------------

Configurations are defined in the package using the ``configs`` field:

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

* **with**: Parameter values for this configuration
* **uses**: Base configuration to inherit from
* **overrides**: Package/parameter overrides
* **extensions**: Task extensions (see below)
* **tasks**: Additional or overriding tasks
* **types**: Additional or overriding types
* **imports**: Additional imports for this configuration
* **fragments**: Additional fragments for this configuration

Selecting a Configuration
--------------------------

Configurations are selected via the command line:

.. code-block:: bash

    dfm run build -c debug

When a configuration is selected:

1. Base package is loaded
2. Configuration parameters override package parameters
3. Configuration overrides are applied
4. Configuration tasks/types/imports/fragments are merged
5. Task graph is built using the merged definition

Configurations enable:

* **Build variants**: debug, release, profiling builds
* **Tool selection**: Switch between different tool vendors
* **Target platforms**: Customize for different deployment targets
* **Test modes**: Normal vs. regression vs. continuous integration


Package Extensions
==================

Extensions allow you to modify existing tasks by adding parameters, dependencies,
or other attributes without replacing the entire task. This is useful for
augmenting tasks from imported packages.

Defining Extensions
-------------------

Extensions are typically defined in configurations:

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

The extension above adds a ``coverage`` parameter and an additional dependency
to the ``hdlsim.vlt.SimImage`` task.

Extension Capabilities
----------------------

Extensions can modify tasks by:

* **Adding parameters**: Introduce new configuration options
* **Adding dependencies**: Include additional ``needs``
* **Changing base**: Specify a different ``uses`` base task

Extensions are particularly useful when:

* Working with third-party packages that need customization
* Adding instrumentation or monitoring to existing tasks
* Implementing cross-cutting concerns (logging, metrics, etc.)

Extension Inheritance
---------------------

Extensions can inherit from other extensions using ``uses``:

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

This allows building up complex configurations incrementally.
