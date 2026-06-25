############################
Script ↔ Dataflow I/O
############################

Shell tasks (``shell: bash`` and friends) exchange data with the dataflow
graph through a GitHub-Actions-style contract: **environment variables carry
inputs into the script**, and **append-only files carry outputs back to the
graph**. The files are located by ``DFM_*`` environment variables that the
runner sets, so a script just appends to ``$DFM_OUTPUT`` (etc.) and the runner
parses the file after the process exits.

This is fully backward compatible: ``${{ }}`` parameter substitution still
works, and a script that ignores all of the channels below behaves exactly as
before.

Inputs the runner provides
==========================

.. list-table::
   :header-rows: 1
   :widths: 22 12 66

   * - Env var
     - Kind
     - Contents
   * - ``DFM_RUNDIR``
     - path
     - Task run directory (alias: ``TASK_RUNDIR``)
   * - ``DFM_SRCDIR``
     - path
     - Task source directory (alias: ``TASK_SRCDIR``)
   * - ``DFM_TASK_NAME``
     - string
     - Fully-qualified task name
   * - ``DFM_PARAM_<NAME>``
     - string
     - Each declared param. Scalars verbatim; ``list``/``map`` as compact JSON;
       booleans as ``true``/``false``.
   * - ``DFM_PARAMS``
     - path
     - JSON file: ``{ "<name>": <value>, ... }`` — full structured params
   * - ``DFM_INPUTS``
     - path
     - JSON file: ``[ <data item>, ... ]`` — every consumed input item
   * - ``DFM_MEMENTO``
     - path
     - JSON file of the prior memento (absent on the first run)

``DFM_INPUTS`` is a *path to a file* rather than inline JSON so that large
filesets cannot blow the environment-size limit. Scalar params are *also*
inlined as ``DFM_PARAM_*`` for the common, ergonomic case.

Outputs the script provides
===========================

All output files are pre-created empty, so a script can blindly ``>>`` to them.

.. list-table::
   :header-rows: 1
   :widths: 24 30 46

   * - Env var
     - Format
     - Becomes
   * - ``DFM_OUTPUT``
     - JSONL — one data-item object per line
     - ``output`` items (filesets, etc.)
   * - ``DFM_ENV``
     - ``KEY=VALUE`` lines (+ heredoc form)
     - a ``std.Env`` item (``vals``) → downstream env
   * - ``DFM_PATH``
     - one directory per line
     - a ``std.Env`` item (``prepend_path``) → downstream PATH
   * - ``DFM_MARKERS``
     - JSONL of ``{severity, msg, loc?}``
     - ``markers``
   * - ``DFM_MEMENTO_OUT``
     - JSON object (write)
     - ``memento`` for the next run's up-to-date check
   * - *exit code*
     - integer
     - ``status`` (authoritative — markers never flip it)

File formats
============

``DFM_OUTPUT`` — typed data items (JSONL). Each line is one item; ``type`` is
required. A ``std.FileSet`` with ``basedir: "."`` is rewritten to the rundir:

.. code-block:: bash

   echo '{"type":"std.FileSet","filetype":"verilogSource","basedir":".","files":["gen.sv"]}' >> "$DFM_OUTPUT"

``DFM_ENV`` — GHA-compatible key/value, including the multiline heredoc form:

.. code-block:: bash

   echo "SIM_SEED=42" >> "$DFM_ENV"
   { echo "BANNER<<EOF"; cat banner.txt; echo "EOF"; } >> "$DFM_ENV"

The runner folds the accumulated keys (and ``DFM_PATH`` directories) into a
single ``std.Env`` item, so they flow downstream through the *same*
env-merging path that ``std.Env`` inputs already use.

The ``dfm-out`` helper
======================

Hand-writing JSON in bash is the rough edge of this design. The bundled
``dfm-out`` console script writes the files for you (it reads the ``DFM_*``
paths from its own environment, and is placed on ``PATH`` for shell tasks):

.. code-block:: bash

   dfm-out fileset --filetype verilogSource gen.sv pkg.sv   # → $DFM_OUTPUT
   dfm-out env  SIM_SEED=42                                  # → $DFM_ENV
   dfm-out path /opt/tools/bin                               # → $DFM_PATH
   dfm-out error "synthesis failed" --file top.sv --line 10  # → $DFM_MARKERS
   dfm-out item --type my_pkg.Report key=val n:=3           # n:= ⇒ JSON-typed value

``python -m dv_flow.mgr.out`` is an equivalent fallback. Scripts may always
fall back to raw ``echo >> "$DFM_OUTPUT"``.

Worked example
==============

.. code-block:: yaml

   - name: GenRtl
     shell: bash
     consumes: [{type: std.FileSet}]
     produces: [{type: std.FileSet}]
     with:
       top:   {type: str, value: "soc_top"}
       seeds: {type: list, value: [1, 2, 3]}
     run: |
       echo "Generating for $DFM_PARAM_TOP"          # scalar param, inline
       echo "seeds JSON: $DFM_PARAM_SEEDS"           # list param as JSON

       # Read upstream filesets structurally
       jq -r '.[] | select(.type=="std.FileSet") | .files[]' "$DFM_INPUTS" > srclist.txt

       python gen.py --top "$DFM_PARAM_TOP" --srcs srclist.txt --out gen.sv

       # Hand results back to the graph
       dfm-out fileset --filetype verilogSource gen.sv
       dfm-out env GEN_OK=1
       [ -s gen.sv ] || dfm-out error "generator produced empty output"

Downstream tasks that ``consumes: std.FileSet`` automatically see ``gen.sv``;
downstream shell tasks see ``GEN_OK`` in their environment.

Coming from GitHub Actions
==========================

.. list-table::
   :header-rows: 1
   :widths: 50 50

   * - GitHub Actions
     - DV Flow
   * - ``$GITHUB_OUTPUT``
     - ``$DFM_OUTPUT`` (typed JSONL, not ``key=value``)
   * - ``$GITHUB_ENV``
     - ``$DFM_ENV``
   * - ``$GITHUB_PATH``
     - ``$DFM_PATH``
   * - ``INPUT_<NAME>``
     - ``DFM_PARAM_<NAME>``
   * - ``$GITHUB_STEP_SUMMARY``
     - ``$DFM_MARKERS`` (structured markers)

.. note::

   ``TASK_SRCDIR`` / ``TASK_RUNDIR`` remain as aliases for one release and are
   then removed in favor of ``DFM_SRCDIR`` / ``DFM_RUNDIR``.
