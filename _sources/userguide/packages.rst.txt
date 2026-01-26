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
* **std.Exec** - Execute shell commands
* **std.SetEnv** - Set environment variables
* **std.IncDirs** - Extract include directories from filesets

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

When a directory is specified, DV Flow searches for ``flow.yaml`` or ``flow.yaml`` 
files in the subdirectory tree.

Import with Alias
-----------------

Use the ``as`` keyword to give an imported package an alias:

.. code-block:: yaml

    package:
        name: proj

        imports:
        - name: hdlsim.vlt
          as: sim

        tasks:
        - name: build
          uses: sim.SimImage  # References hdlsim.vlt.SimImage

Import Resolution
-----------------

When resolving imports, DV Flow searches in the following order:

1. **Relative to current file** - Paths relative to the importing package's location
2. **Relative to project root** - Allows sibling packages to find each other
3. **Package registry** - Built-in and installed packages

This allows sub-packages to import sibling packages naturally:

.. code-block:: yaml

    # In packages/ip1/flow.yaml
    package:
        name: ip1
        imports:
        - packages/ip2/flow.yaml  # Finds sibling relative to project root

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
across all fragments - you cannot define ``build`` in multiple fragments of the
same package.

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
