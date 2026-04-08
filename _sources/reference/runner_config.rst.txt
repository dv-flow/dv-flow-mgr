################
Runner Config
################

Reference for all runner configuration fields. Configuration is loaded
from YAML files and merged across layers (install, site, project, CLI).

Top-Level Structure
===================

.. code-block:: yaml

    runner:
      default: local          # or "type: lsf"
      pool:
        min_workers: 0
        max_workers: 16
        idle_timeout: 300
        launch_batch_size: 4
      lsf:
        bsub_cmd: bsub
        queue: ""
        project: ""
        resource_select: []
        bsub_extra: []
        worker_dfm_path: dfm
      defaults:
        memory: "1G"
        cores: 1
        walltime: "1:00"
      resource_classes:
        small:  { cores: 1,  memory: "2G" }
        medium: { cores: 4,  memory: "8G" }
        large:  { cores: 8,  memory: "32G" }

Runner Type
===========

``default`` / ``type``
    Runner backend name. ``default`` and ``type`` are synonyms; both
    set the active runner. Default: ``local``.

Pool Config
===========

Controls worker pool scaling (used by remote runners).

``min_workers`` (int, default 0)
    Minimum warm workers per resource class.

``max_workers`` (int, default 16)
    Maximum concurrent workers per resource class.

``idle_timeout`` (int, default 300)
    Seconds before an idle worker is terminated.

``launch_batch_size`` (int, default 4)
    Workers to launch per scale-up event.

LSF Config
==========

LSF-specific settings. Ignored when using the ``local`` runner.

``bsub_cmd`` (str, default ``"bsub"``)
    Command to submit jobs. Sites with wrapper scripts (e.g.
    ``lsf_bsub``) set this in the install config. *Last-writer-wins.*

``queue`` (str, default ``""``)
    Default LSF queue (``-q``). Empty means LSF picks the default.
    *Last-writer-wins.*

``project`` (str, default ``""``)
    Accounting project string (``-P``). *Last-writer-wins.*

``resource_select`` (list of str, default ``[]``)
    Host selection predicates for ``-R select[...]``. *Accumulated*
    across layers; predicates from all layers are combined with ``&&``.

``bsub_extra`` (list of str, default ``[]``)
    Arbitrary extra ``bsub`` flags (e.g. ``["-G", "dv_users"]``).
    *Accumulated* across layers.

``worker_dfm_path`` (str, default ``"dfm"``)
    Path to the ``dfm`` binary on compute nodes. *Last-writer-wins.*

Resource Defaults
=================

Default resource requirements for tasks without explicit resource tags.

``memory`` (str, default ``"1G"``)
    Memory with unit suffix (e.g. ``"512M"``, ``"2G"``).

``cores`` (int, default 1)
    Number of CPU cores.

``walltime`` (str, default ``"1:00"``)
    Maximum walltime in ``HH:MM`` format.

Resource Classes
================

Named bundles of resource requirements. Tasks can reference a class
by name via ``std.ResourceTag: { resource_class: large }``.

.. code-block:: yaml

    resource_classes:
      small:   { cores: 1,  memory: "2G" }
      medium:  { cores: 4,  memory: "8G" }
      large:   { cores: 8,  memory: "32G" }
      gpu:
        cores: 4
        memory: "16G"
        queue: gpu_queue
        resource_select: ["ngpus>0"]

Each class may include its own ``queue`` and ``resource_select``
overrides that are merged with the config-level values at submission
time.

Merge Rules
===========

+-----------------------+-------------------+
| Field                 | Merge Strategy    |
+=======================+===================+
| ``default`` / ``type``| Last-writer-wins  |
+-----------------------+-------------------+
| ``bsub_cmd``          | Last-writer-wins  |
+-----------------------+-------------------+
| ``queue``             | Last-writer-wins  |
+-----------------------+-------------------+
| ``project``           | Last-writer-wins  |
+-----------------------+-------------------+
| ``worker_dfm_path``   | Last-writer-wins  |
+-----------------------+-------------------+
| ``resource_select``   | Accumulated       |
+-----------------------+-------------------+
| ``bsub_extra``        | Accumulated       |
+-----------------------+-------------------+
| Pool scalars          | Last-writer-wins  |
+-----------------------+-------------------+

Environment Variables
=====================

``DFM_RUNNER``
    Override the runner type (equivalent to ``--runner``).

``DFM_INSTALL_CONFIG``
    Path to the installation config file (overrides the default
    ``<sys.prefix>/etc/dfm/config.yaml``).
