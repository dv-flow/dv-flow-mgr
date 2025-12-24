################
Standard Library
################

std.CreateFile
==============
Example 
-------
.. code-block::

    package:
        name: create
    
        tasks:
        - name: TemplateFile
            uses: std.CreateFile
            with:
              type: text
              filename: template.txt
              content: |
                This is a template file
                with multiple lines
                of text.

Consumes 
--------

Produces 
--------
Produces a `std.FileSet` parameter set containing a single file


Parameters
----------

* **type** - [Required] Specifies the `filetype` of the produced fileset
* **filename** - [Required] Name of the file to produce
* **incdir** - [Optional] If 'true', adds the output directory as an include directory


std.FileSet
===========
Creates a 'FileSet' parameter set from a specification. This task is
primarily used to build up list of files for processing by HDL compilation
tools.

Example 
-------
.. code-block::

    package:
        name: fileset.example
    
        tasks:
        - name: rtlsrc
            uses: std.FileSet
            with:
              include: '*.v'
              base: 'src/rtl'
              type: 'verilogSource'

The example above finds all files with a `.v` extension in the `src/rtl` 
subdirectory of the task's source directory. The task emits a FileSet
parameter set having the filetype of `verilogSource`.

Consumes 
--------
None by default (``consumes: none``)

Produces 
--------
Produces a `std.FileSet` parameter set containing files matched by the parameter specification.


Parameters
----------

* **type** - [Required] Specifies the `filetype` of the produced fileset
* **base** - [Optional] Base directory for the fileset. Defaults to the task's source directory
* **include** - [Required] Set of file patterns to include in the fileset. Glob patterns may be used
* **exclude** - [Optional] Set of file patterns to exclude from the fileset. Glob patterns may be used
* **incdirs** - [Optional] Set of include directories that consumers of the fileset must use
* **defines** - [Optional] Set of pre-processor defines that consumers of the fileset must use
* **attributes** - [Optional] Set of attributes to tag the fileset with (e.g., ['uvm', 'testbench'])


std.Exec
========

Executes a shell command as part of the task flow. This is useful for
running external tools, scripts, or commands that don't have dedicated
task implementations.

Example
-------

.. code-block:: yaml

    package:
        name: exec.example
    
        tasks:
        - name: run_script
          uses: std.Exec
          with:
            command: "./scripts/process_data.sh"
            shell: bash
            when: changed

Consumes
--------
All inputs by default (``consumes: all``)

Produces
--------
Passes through all inputs to output. Does not produce additional data items.

Parameters
----------

* **command** - [Required] The shell command to execute
* **shell** - [Optional] Shell to use for execution (default: "bash")
* **when** - [Optional] Controls when the command runs:

  * ``"always"`` - Always run the command (default)
  * ``"changed"`` - Only run if upstream tasks changed

* **timestamp** - [Optional] Path to a timestamp file to check for changes

The ``timestamp`` parameter allows incremental execution based on file
timestamps. If specified, the task compares the timestamp of the file
against the previous execution to determine if output changed.


std.SetEnv
==========

Sets environment variables for use by downstream tasks. Supports glob
pattern expansion for paths, making it easy to configure tool paths
and directories.

Example
-------

.. code-block:: yaml

    package:
        name: setenv.example
    
        tasks:
        - name: tool_env
          uses: std.SetEnv
          with:
            setenv:
              TOOL_HOME: /opt/tools/my_tool
              PYTHONPATH: "lib/python/site-packages"
            append_path:
              PATH: /opt/tools/my_tool/bin
            prepend_path:
              LD_LIBRARY_PATH: /opt/tools/my_tool/lib

Glob Expansion
--------------

Values containing glob patterns (``*``, ``?``, ``[...]``) are expanded
relative to the task's source directory:

.. code-block:: yaml

    tasks:
    - name: lib_paths
      uses: std.SetEnv
      with:
        setenv:
          MY_LIBS: "libs/*/lib"  # Expands to all lib dirs

If multiple paths match, they are joined with the platform path separator
(`:` on Unix, `;` on Windows).

Consumes
--------
All inputs by default (``consumes: all``)

Produces
--------
Produces a ``std.Env`` data item containing the environment variable mappings.

Parameters
----------

* **setenv** - [Optional] Map of environment variable names to values
* **append_path** - [Optional] Map of environment variables to values that should be appended
* **prepend_path** - [Optional] Map of environment variables to values that should be prepended

The ``append_path`` and ``prepend_path`` parameters automatically handle
path separator logic for PATH-like environment variables.


std.SetFileType
===============

Modifies the file type of input filesets. This is useful when you need
to reinterpret files with a different type for different tools.

Example
-------

.. code-block:: yaml

    package:
        name: setfiletype.example
    
        tasks:
        - name: verilog_files
          uses: std.FileSet
          with:
            include: "*.v"
            type: verilogSource
        
        - name: reinterpret
          uses: std.SetFileType
          needs: [verilog_files]
          with:
            filetype: systemVerilogSource

Consumes
--------
Only ``std.FileSet`` data items (``consumes: [{type: std.FileSet}]``)

Produces
--------
Produces new ``std.FileSet`` data items with the updated file type.

Parameters
----------

* **filetype** - [Required] The new file type to assign to all consumed filesets


std.IncDirs
===========

Extracts include directories from input filesets and produces them as
a structured list. This is useful for passing include paths to compilation
tools.

Example
-------

.. code-block:: yaml

    package:
        name: incdirs.example
    
        tasks:
        - name: rtl_files
          uses: std.FileSet
          with:
            include: "*.sv"
            incdirs:
              - include
              - rtl/include
        
        - name: extract_dirs
          uses: std.IncDirs
          needs: [rtl_files]

Consumes
--------
``std.FileSet`` data items

Produces
--------
Produces a data item containing the collected include directories.

Parameters
----------

None. The task operates entirely on input filesets.


std.Message
===========

Displays a message during task execution. Useful for logging, debugging,
and providing user feedback during flow execution.

Example
-------

.. code-block:: yaml

    package:
        name: message.example
    
        tasks:
        - name: hello
          uses: std.Message
          with:
            msg: "Hello, World!"
        
        - name: status
          uses: std.Message
          with:
            msg: "Build completed successfully"
          needs: [build]

Consumes
--------
All inputs by default (``consumes: all``)

Produces
--------
Passes through all inputs. Does not produce additional data items.

Parameters
----------

* **msg** - [Optional] The message to display (default: empty string)

Messages support expression syntax for dynamic content:

.. code-block:: yaml

    package:
      name: example
      with:
        version:
          type: str
          value: "1.0"
      
      tasks:
      - name: version_msg
        uses: std.Message
        with:
          msg: "Building version ${{ version }}"

