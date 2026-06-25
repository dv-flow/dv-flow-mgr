#######
Caching
#######

Caching lets a task reuse a result that was produced by an *equivalent* run --
possibly in a different workspace, on a different machine, or by a different
user. Where :doc:`incremental` execution skips work that is up to date *within a
rundir*, and ``--base-rundir`` reuses artifacts from *one specific* prior build,
the cache is a **shared, content-addressed store**: a task computes a key from
its inputs and looks that key up across every configured cache.

This is what makes a shared CI cache useful -- the first job to build a given
fileset populates the cache, and every later job (any workspace) gets a cache
hit instead of recompiling.

Caching is **opt-in** at two levels: you enable a cache for the run (an
environment variable) and you mark individual tasks as cacheable.

Creating a cache
================

``dfm cache init`` initializes a cache directory:

.. code-block:: bash

    dfm cache init /path/to/cache

    # A cache shared by a group of users (group-writable, setgid):
    dfm cache init /shared/build/cache --shared

This creates the directory and a ``.cache_config.yaml`` marker. ``--shared``
sets group-writable permissions so multiple users in the same group can share
it.

Enabling caching for a run
==========================

Point ``DV_FLOW_CACHE`` at a cache directory (or a cache config file). When it
is set, ``dfm run`` consults the cache for every cacheable task:

.. code-block:: bash

    export DV_FLOW_CACHE=/path/to/cache
    dfm run build

If ``DV_FLOW_CACHE`` is unset, caching is disabled regardless of any task
``cache:`` settings.

To layer multiple caches -- for example a writable local cache in front of a
read-only shared one -- point ``DV_FLOW_CACHE`` at a config file:

.. code-block:: yaml

    caches:
      - type: directory
        path: /home/me/.dfm/cache       # writable local cache
        writable: true
      - type: directory
        path: /shared/build/cache       # read-only shared cache
        writable: false

Marking a task cacheable
========================

A task opts in with its ``cache:`` field. The simplest form is a boolean:

.. code-block:: yaml

    - name: build
      run: |
        gcc -O2 -o program main.c
      cache: true        # enable caching with defaults

``cache: false`` (or omitting the field) leaves the task uncached. For more
control, supply a ``CacheDef``:

.. code-block:: yaml

    - name: build
      run: |
        gcc -O2 -o program main.c
      cache:
        enabled: true
        compression: gzip
        hash:
          - 'shell("gcc --version")'

The ``CacheDef`` fields are:

.. list-table::
   :header-rows: 1
   :widths: 18 18 64

   * - Field
     - Default
     - Meaning
   * - ``enabled``
     - ``true``
     - Whether this task participates in caching.
   * - ``compression``
     - ``no``
     - Artifact compression: ``no`` (store a directory), ``gzip``, ``bzip2``,
       or ``yes`` (the default compression).
   * - ``hash``
     - ``[]``
     - Extra expressions folded into the cache key (see below).

What the cache key is built from
================================

A task's cache key is derived from everything that should make its output
*different*:

* the task name,
* the content of its input filesets (hashed by a filetype-aware hash provider --
  e.g. a SystemVerilog-aware provider for HDL sources, otherwise a default
  content hash),
* the task's parameter values, and
* any extra ``hash`` expressions you declare.

If a task's inputs cannot be hashed (or a ``hash`` expression cannot be
evaluated), the task is simply treated as not cacheable for that run rather than
producing a wrong hit.

The ``hash`` expressions exist to capture *implicit* inputs that DFM cannot see
in the dataflow -- most commonly the tool version or an environment setting that
affects the output:

.. code-block:: yaml

    cache:
      hash:
        - 'shell("gcc --version")'   # invalidate when the compiler changes
        - 'env.CFLAGS'               # ...or when build flags change

On a cache hit, the task's recorded output is restored and its artifacts are
unpacked into the task's run directory (output paths are rewritten to the
current rundir), so downstream tasks consume them exactly as if the task had
run. The run report marks whether each task was a cache hit or was stored.

Caching vs. incremental vs. base-rundir
=======================================

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Mechanism
     - Scope
   * - :doc:`Incremental <incremental>` (up-to-date)
     - Skips re-running a task whose inputs are unchanged **within the same
       rundir** (mementos).
   * - ``--base-rundir``
     - Reuses successful results from **one specific** prior rundir.
   * - **Cache** (this page)
     - Reuses results across **any** workspace/machine/user via a shared,
       input-addressed store keyed on task inputs + parameters.

See Also
========

* :doc:`incremental` -- up-to-date checking and ``--base-rundir`` reuse.
* :doc:`/reference/cli` -- the ``dfm cache`` command and ``--report``.
