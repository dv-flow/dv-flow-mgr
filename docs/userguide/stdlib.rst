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


Running Shell Commands
======================

Shell commands are executed by specifying ``shell: bash`` (or another shell)
and providing the command with ``run:``. This is useful for running external
tools, scripts, or commands that don't have dedicated task implementations.

Example
-------

.. code-block:: yaml

    package:
        name: exec.example
    
        tasks:
        - name: run_script
          shell: bash
          run: ./scripts/process_data.sh
        
        - name: inline_commands
          shell: bash
          run: |
            echo "Processing data..."
            ./scripts/process.sh
            echo "Done"

Shell Tasks
-----------

Shell tasks support all standard shells. Common options:

* ``bash`` - Bourne Again Shell (most common)
* ``sh`` - POSIX shell
* ``python`` - Python interpreter
* ``pytask`` - Python task with context (for custom tasks)

The ``run:`` field specifies the command or script to execute. For inline
scripts, use YAML's multi-line syntax (``|`` or ``>``).


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


std.Prompt
==========

Executes an AI assistant with a specified prompt and collects structured 
results. The AI assistant must create a valid JSON result file or the task 
will fail with an error.

This task enables AI-assisted workflows for code generation, documentation, 
test creation, and other automated tasks that benefit from large language 
model capabilities.

Example
-------

Basic usage:

.. code-block:: yaml

    package:
        name: prompt.example
    
        tasks:
        - name: generate_code
          uses: std.Prompt
          with:
            user_prompt: "Generate a Python function to parse CSV files"
            assistant: copilot

Custom system prompt:

.. code-block:: yaml

    package:
        name: prompt.custom
    
        tasks:
        - name: generate_test
          uses: std.Prompt
          with:
            system_prompt: |
              You are a test generation assistant.
              Input data: ${{ inputs }}
              
              Generate unit tests for the code and write results to ${{ result_file }}
              in JSON format with the following structure:
              {
                "status": 0,
                "changed": true,
                "output": [],
                "markers": []
              }
            user_prompt: "Create comprehensive unit tests"
            result_file: "tests.result.json"

Consumes
--------
All inputs by default (``consumes: all``). Input data is available in the 
prompt via the ``${{ inputs }}`` variable.

Produces
--------
Outputs are determined by the AI assistant's result JSON file. Typically 
produces ``std.FileSet`` items for generated files, but can produce any 
data type specified in the result.

Parameters
----------

* **system_prompt** - [Optional] System prompt template. Can include variable references:

  * ``${{ inputs }}`` - JSON of input data from upstream tasks
  * ``${{ name }}`` - Current task name
  * ``${{ result_file }}`` - Expected result filename
  
  If empty, uses a default template that describes the expected JSON result format.

* **user_prompt** - [Optional] User's prompt content. This is appended to the 
  system prompt with a "User Request:" header.

* **result_file** - [Optional] Name of the JSON result file the AI must create 
  (default: ``{name}.result.json``). The task fails if this file is missing or 
  contains invalid JSON.

* **assistant** - [Optional] AI assistant to use. Options:

  * ``copilot`` - GitHub Copilot CLI (default)
  * ``openai`` - OpenAI API (not yet implemented)
  * ``claude`` - Claude API (not yet implemented)

* **assistant_config** - [Optional] Map of assistant-specific configuration 
  (e.g., API keys, model settings)

Required Result Format
----------------------

The AI assistant must create a JSON file with the following structure:

.. code-block:: json

    {
      "status": 0,
      "changed": true,
      "output": [
        {
          "type": "std.FileSet",
          "filetype": "pythonSource",
          "basedir": ".",
          "files": ["generated.py"]
        }
      ],
      "markers": [
        {
          "msg": "Generated 1 file",
          "severity": "info"
        }
      ]
    }

Fields:

* **status** - Exit code (0 = success, non-zero = failure)
* **changed** - Whether the task produced new/modified outputs
* **output** - Array of output data items (e.g., FileSets)
* **markers** - Array of diagnostic messages with severity levels

Error Handling
--------------

The Prompt task uses strict validation:

* **Missing result file** → Task fails with status=1
* **Invalid JSON syntax** → Task fails with status=1
* **Result is not a JSON object** → Task fails with status=1
* **Assistant not available** → Task fails with status=1
* **Assistant execution fails** → Task fails with assistant's exit code

Debugging
---------

When the Prompt task runs, it creates several files in the task's run directory:

* ``{name}.prompt.txt`` - The complete prompt sent to the AI assistant
* ``{name}.result.json`` - The structured result from the AI (if created)
* ``assistant.stdout.log`` - Standard output from the AI assistant
* ``assistant.stderr.log`` - Standard error from the AI assistant

These files are invaluable for debugging when the AI assistant doesn't produce 
the expected result or when result parsing fails.

Setup Requirements
------------------

**GitHub Copilot CLI**

To use the default ``copilot`` assistant:

1. Install GitHub CLI: https://cli.github.com/
2. Install Copilot extension:

   .. code-block:: bash

       gh extension install github/gh-copilot

3. Authenticate:

   .. code-block:: bash

       gh auth login

**Other Assistants**

OpenAI and Claude assistants are placeholders for future implementation. 
Contributions are welcome!


