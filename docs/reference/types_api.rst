==============
Type System API
==============

DV Flow Manager provides a type system for defining structured data that
flows between tasks. Types can be defined in packages, inherit from other
types, and be used as the basis for tasks and parameters.

Overview
========

The type system enables:

* **Structured Data**: Define complex data structures with typed fields
* **Inheritance**: Build on existing types to create specialized variants
* **Type Safety**: Ensure data consistency across task boundaries
* **Documentation**: Self-documenting data contracts between tasks

Type Definition
===============

Types are defined in packages using the ``types`` section:

.. code-block:: yaml

    package:
      name: my_types
      
      types:
      - name: BaseOptions
        doc: Common compiler options
        with:
          optimization:
            type: str
            value: "-O2"
            doc: Optimization level
          warnings:
            type: list
            value: []
            doc: Warning flags to enable

Type Inheritance
================

Types can inherit from other types using the ``uses`` field:

.. code-block:: yaml

    types:
    - name: BaseOptions
      with:
        optimization:
          type: str
          value: "-O2"
    
    - name: DebugOptions
      uses: BaseOptions
      with:
        debug_symbols:
          type: bool
          value: true
        optimization:
          value: "-O0"  # Override parent value

The ``DebugOptions`` type inherits all parameters from ``BaseOptions`` and:

* Adds a new ``debug_symbols`` parameter
* Overrides the ``optimization`` parameter's default value

Using Types as Task Bases
==========================

Types can be used as the base for tasks, creating "DataItem" tasks that
produce data without executing code:

.. code-block:: yaml

    package:
      name: my_pkg
      
      types:
      - name: SimOptions
        with:
          trace:
            type: bool
            value: false
          seed:
            type: int
            value: 0
      
      tasks:
      - name: default_sim_opts
        uses: SimOptions
        with:
          trace: true
          seed: 42

This task produces a ``SimOptions`` data item with the specified values.
Tasks depending on ``default_sim_opts`` receive this structured data.

Type Schema
===========

TypeDef Structure
-----------------

The ``TypeDef`` class defines the YAML schema for types:

.. code-block:: python

    class TypeDef(BaseModel):
        name: str              # Type name
        uses: str = None       # Base type to inherit from
        doc: str = None        # Documentation
        params: Dict           # Field definitions (alias: "with")
        srcinfo: SrcInfo       # Source location

Field Definition
----------------

Each field in a type's ``with`` section can be:

**Simple value**:

.. code-block:: yaml

    types:
    - name: Simple
      with:
        field1: "value"
        field2: 42

**ParamDef with metadata**:

.. code-block:: yaml

    types:
    - name: Documented
      with:
        field1:
          type: str
          value: "default"
          doc: "Field documentation"

Field Types
-----------

Supported field types:

* **str**: String values
* **int**: Integer values
* **bool**: Boolean values (true/false)
* **list**: List of values
* **map**: Dictionary of key-value pairs

Complex types can nest:

.. code-block:: yaml

    types:
    - name: Complex
      with:
        settings:
          type: map
          value:
            key1: "value1"
            key2: "value2"
        files:
          type:
            list:
              item: str

Runtime Type System
===================

Type Class
----------

At runtime, types are represented by the ``Type`` class:

.. code-block:: python

    @dataclass
    class Type:
        name: str                           # Qualified type name
        doc: str                            # Documentation
        params: Dict[str, TypeField]        # Field definitions
        paramT: Any                         # Parameter class
        uses: Type                          # Base type
        srcinfo: SrcInfo                    # Source location
        typedef: TypeDef                    # Original definition

TypeField Class
---------------

Individual fields are represented by ``TypeField``:

.. code-block:: python

    @dataclass
    class TypeField:
        name: str           # Field name
        type: Any           # Field type
        doc: str            # Documentation
        value: str          # Default value
        append: List[Any]   # Values to append (for list types)
        srcinfo: SrcInfo    # Source location

Creating Type Instances
=======================

Types are instantiated when creating data items:

.. code-block:: python

    # In a task implementation
    async def MyTask(ctxt, input):
        # Create a data item of a custom type
        item = ctxt.mkDataItem("my_pkg.SimOptions")
        item.trace = True
        item.seed = 42
        
        return TaskDataResult(
            output=[item]
        )

The runtime ensures that the data item conforms to the type definition.

Standard Library Types
======================

std.DataItem
------------

The base type for all data items:

.. code-block:: yaml

    types:
    - name: DataItem
      with:
        type:
          type: str

All custom types should ultimately derive from ``std.DataItem`` (directly
or indirectly).

std.FileSet
-----------

Structured file collection with metadata:

.. code-block:: yaml

    types:
    - name: FileSet
      uses: std.DataItem
      with:
        filetype: str         # File type (e.g., "verilogSource")
        basedir: str          # Base directory
        files: list           # List of file paths
        incdirs: list         # Include directories
        defines: list         # Preprocessor defines
        attributes: list      # Tags/attributes

std.Env
-------

Environment variable mappings:

.. code-block:: yaml

    types:
    - name: Env
      with:
        vals: map             # Environment variable values
        append_path: map      # Paths to append
        prepend_path: map     # Paths to prepend

Best Practices
==============

Type Naming
-----------

* Use PascalCase for type names (``SimOptions``, ``CompilerFlags``)
* Choose descriptive names that indicate the data's purpose
* Prefix with package name for clarity in large projects

Type Organization
-----------------

* Define common types in a dedicated types package
* Import type packages where needed
* Use inheritance to avoid duplication

Type Documentation
------------------

* Document each type's purpose in the ``doc`` field
* Document each field's meaning and valid values
* Include examples in the documentation

Example: Complete Type Definition
==================================

.. code-block:: yaml

    package:
      name: hdl_types
      
      types:
      - name: CompilerOptions
        doc: |
          Common options for HDL compilation tools.
          Used to configure simulators, synthesizers, and linters.
        with:
          optimization:
            type: str
            value: "-O2"
            doc: Optimization level (-O0, -O1, -O2, -O3)
          warnings:
            type: list
            value: []
            doc: List of warning flags to enable
          defines:
            type: map
            value: {}
            doc: Preprocessor defines as key-value pairs
      
      - name: SimulatorOptions
        uses: CompilerOptions
        doc: Simulator-specific options extending compiler options
        with:
          trace:
            type: bool
            value: false
            doc: Enable waveform tracing
          coverage:
            type: bool
            value: false
            doc: Enable coverage collection
          seed:
            type: int
            value: 0
            doc: Random seed (0 = random)

This defines a type hierarchy for tool configuration that can be extended
and customized throughout a project.
