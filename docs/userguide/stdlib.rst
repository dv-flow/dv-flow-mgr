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
              includes: '*.v'
              base: 'src/rtl'
              type: 'verilogSource'

The example above finds all files with a `.v` extension in the `src/rtl` 
subdirectory of the task's source directory. The task emits a FileSet
parameter set having the filetype of `verilogSource`.

Consumes 
--------

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

