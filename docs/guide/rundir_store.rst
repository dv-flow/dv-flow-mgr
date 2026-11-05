############
Rundir Store
############

Every project has a rundir at ``<package-root>/rundir``. The package root is
the directory of the root ``flow.yaml`` (or ``flow.dv``), found by walking up
from the current directory, so ``dfm run`` uses the same rundir wherever in
the project you start it.

By default the rundir is a plain directory. A **rundir store** keeps rundir
contents somewhere else -- typically a large scratch filesystem -- and makes
``rundir`` a symlink into it::

    /home/me/projects/myproj/rundir -> /scratch/me/dfm/_home_me_projects_myproj_rundir

Sources stay in your (small, backed-up) home directory, while build and
simulation results land on scratch. The store is shared by all your projects,
and ``dfm store`` can list it and clean up after projects that have been
deleted.

Enabling a store
================

Set ``DFM_STORE`` to the store directory:

.. code-block:: bash

    export DFM_STORE=/scratch/$USER/dfm

or make it permanent in ``~/.config/dfm/config.yaml``:

.. code-block:: yaml

    store:
      root: /scratch/${USER}/dfm

The next ``dfm run`` in a project with no rundir creates a store entry and
the ``rundir`` symlink. dfm creates the store directory itself if its parent
exists (a guard against an unmounted filesystem); set ``create: false`` to
require it to exist already. To create a store explicitly, or one shared by
several users:

.. code-block:: bash

    dfm store init /scratch/team/dfm --shared   # mode 1777, like /tmp
    dfm store init /proj/acme/dfm --group       # mode 2775

``dfm store info`` shows which store is in effect, where that setting came
from, and the state of the current project's rundir:

.. code-block:: text

    $ dfm store info
    Store:     /scratch/me/dfm
      from:    user-config:/home/me/.config/dfm/config.yaml
      exists:  yes
    Layers consulted:
      * user-config:/home/me/.config/dfm/config.yaml   /scratch/me/dfm
    Project:   /home/me/projects/myproj
    Rundir:    /home/me/projects/myproj/rundir
      state:   ok (linked to a store entry)

Choosing per run or per project
-------------------------------

* ``dfm run --store DIR`` uses ``DIR`` for this run; ``--no-store`` uses a
  local rundir. ``DFM_STORE=local`` (or empty) also disables the store.
* A project that must keep a local rundir (for example because a tool needs
  it on the same filesystem as the sources) can opt out in its checked-in
  ``.dfm/config.yaml``:

  .. code-block:: yaml

      store:
        root: local

  A project file cannot *choose* a store location -- that is a user and site
  decision -- and any other value there is ignored with a warning. The CLI
  and ``DFM_STORE`` still override the opt-out.

The full precedence order is CLI, ``DFM_STORE``, project opt-out, user
config, site config, install config, site plugin, then local. Sites can pick
a store per project with rules; see :doc:`/reference/site_config`.

An existing rundir stays where it is
------------------------------------

Turning on a store does not move existing rundirs. A project with a local
``rundir`` directory keeps using it, and dfm prints a one-time hint to run
``dfm store migrate``. Likewise, a rundir already linked into one store keeps
using it if you configure a different store; ``dfm store info`` reports the
mismatch and ``dfm store relink`` moves it.

Version control
---------------

Ignore the rundir with ``rundir`` in ``.gitignore``, **without** a trailing
slash: ``rundir/`` matches only a directory, not a symlink. dfm warns when it
creates a link that git does not ignore.

How entries work
================

Each project gets one entry, named after the link path with ``/`` replaced by
``_``. If two projects mangle to the same name (``/a_b/rundir`` and
``/a/b/rundir``), or the name is very long, a short hash is appended. The
name is cosmetic: every entry carries metadata in ``.dfm-rundir.json`` --
the link path, project root, package, user, host, git remote and branch,
which config chose the store, and when it was created and last used. That is
what lets ``dfm store`` tell live projects from dead ones.

While ``dfm run`` (or ``dfm agent``) runs, it holds a shared lock on the
entry's ``.dfm-rundir.lock``, so ``dfm store gc`` never deletes an entry in
use.

dfm uses the link path, never the resolved path, in everything it records,
so moving an entry between stores does not invalidate up-to-date checks.

Copied and moved projects
-------------------------

* **Copied** (``cp -a proj proj2``): both copies' links point at the same
  entry, which would make them overwrite each other's results. On its next
  run the copy gets a fresh, empty entry, with a warning.
* **Moved** (``mv proj newname``): the entry is adopted -- its metadata is
  updated and it is renamed to match the new location. Results are kept.

``--clean``
-----------

``dfm run --clean`` empties the entry but keeps the link and the entry's
metadata.

Analysing and cleaning the store
================================

Four commands answer "where did the space go, and what can I delete?":

=========================== ==================================================
``dfm store stats``         Dashboard: filesystem usage, totals, breakdowns by
                            status, last use, project, user and host, the
                            largest entries, and how much is reclaimable.
``dfm store list``          Every entry with status, size, last use, age,
                            sessions, host and project; sortable and
                            filterable. ``--long`` shows everything about each.
``dfm store candidates``    The cleanup list: what is worth deleting, biggest
                            first, with the reason.
``dfm store gc``            Deletes entries -- by policy, by size target, or
                            from a reviewed list.
=========================== ==================================================

All four default to your own entries in the configured store; ``--user U``,
``--all-users`` and ``--store DIR`` change that. ``dfm store info --size``
breaks down the current project's rundir by top-level directory (i.e. by
task).

Where the space goes
--------------------

.. code-block:: text

    $ dfm store stats
    ╭─ Filesystem ──────────────────────────────────────────────╮
    │ /scratch/me/dfm                                           │
    │ ███████████████████████████████████████████████████████   │
    │ █ store 3.8G (2%)   █ other 180.2G   █ free 38.6G of 222G │
    ╰───────────────────────────────────────────────────────────╯
    7 entries  ·  3.8G  ·  1 user
    By status                                  By last use
     STATUS      ENTRIES   SIZE                 LAST USED  ENTRIES   SIZE
     ok                4   2.6G  ██████████▉ 69%  <1d            1 340.0M  █▍     9%
     orphan            1 900.0M  ███▊        23%  1-7d           1   1.8G  ███████▍ 46%
     ...
    Largest 7 entries
     STATUS    SIZE  SHARE      LAST USED  CREATED  RUNS  HOST   PACKAGE  PROJECT
     ok        1.8G  █████▌        2d ago 200d ago   540  a9550  soc      ~/projects/soc-top
     orphan  900.0M  ██▊          75d ago  80d ago     4  a9550  exp      ~/projects/old-exp
     ...
    By project ...
    Reclaimable: 960.0M safe (2 orphaned/retargeted)  ·  790.1M to review (3 ...)
    ╭─ Suggested actions ──────────────────────────╮
    │ # delete entries whose project is gone        │
    │ dfm store gc -y                               │
    │ # see the entries to review, biggest first    │
    │ dfm store candidates --tier review            │
    ╰───────────────────────────────────────────────╯

On a terminal the output is coloured: green for live entries, red for dead
ones, yellow for those to review.

What each entry reports:

* **last used** -- when a dfm session last started in the project, and
  **runs**, the number of sessions;
* **created** -- when the entry was made, so its age;
* **size** -- space on disk (what deleting it frees), plus apparent size, file
  count, the newest modification time, and the largest top-level directories;
* **status**, owner, host, package, git remote and branch, and paths.

Sizes come from walking each entry, which is slow on network filesystems,
so they are cached in the entry (``.dfm-rundir-stats.json``). ``stats``,
``candidates`` and ``gc`` measure entries that have no cached size or have
been used since it was measured; ``--no-measure`` uses the cache only, and
``--refresh`` re-measures everything. ``list`` shows cached sizes unless
``--size`` is given; a ``~`` after a size means the entry has been used since
it was measured.

Useful listings:

.. code-block:: bash

    dfm store list --sort size --limit 10          # ten biggest
    dfm store list --sort last-used                # longest unused first
    dfm store list --older-than 60d --larger-than 1G
    dfm store list --package 'soc*' --long         # all details

What to clean up
----------------

``dfm store candidates`` ranks entries worth deleting, biggest first, in two
tiers:

* **safe** -- the project is gone (``orphan``) or no longer links to the
  entry (``retargeted``). Nobody will miss it.
* **review** -- the project could not be checked from this host
  (``unknown``), or it exists but has not used its rundir for ``--stale``
  days (default 30). Deleting a stale entry discards that project's results;
  its next run starts clean.

Entries in use, entries without metadata, and entries used in the last hour
are never listed.

.. code-block:: text

    $ dfm store candidates
     TIER     SIZE  SHARE    LAST USED  PACKAGE  WHY                                     PROJECT
     safe   900.0M  ██████▏    75d ago  exp      project deleted                         ~/projects/old-exp
     review 420.0M  ██▉        45d ago  dma      project exists; unused 45d (results...) ~/projects/dma-v1
     review 250.0M  █▊         20d ago  soc      not visible from this host; last used   /hostlocal/farm-run
                                                 on farm-07
     safe    60.0M  ▍          12d ago  scratch  project no longer links here            ~/projects/tmp-try
    2 safe (960.0M)  ·  2 to review (670.0M)

Cleaning up
-----------

``dfm store gc`` deletes entries. It prints its plan -- what, how big, why,
and how much free space the filesystem will have afterwards -- and asks for
confirmation unless ``-y``.

.. code-block:: bash

    dfm store gc --dry-run                     # the plan, nothing deleted
    dfm store gc -y                            # entries whose project is gone
    dfm store gc -y --older-than 30d           # everything unused for 30 days
    dfm store gc -y --orphans --older-than 7d  # dead *and* unused for a week
    dfm store gc --reclaim 50G                 # free 50G: dead entries first,
                                               # then least recently used
    dfm store gc --target-free 200G            # free enough to leave 200G free

Selection:

* With no criteria, ``gc`` selects orphaned and retargeted entries.
* ``--older-than AGE`` (``30d``, ``12h``, ``2w``) on its own selects every
  entry unused for that long, including linked ones. Deleting a linked entry
  leaves a dangling link, which the project's next run recreates (empty).
  Combined with ``--orphans``, both conditions must hold.
* ``--larger-than SIZE`` (``500M``, ``10G``), ``--package`` and ``--host``
  narrow any selection.
* ``--reclaim SIZE`` and ``--target-free SIZE`` keep only as much of the
  selection as needed -- dead entries first, then the least recently used.
  Alone, they choose from all entries.

**Review, then delete a list.** ``candidates --format names`` prints one
entry per line; ``--annotate`` adds a ``# tier size reason`` comment. Edit
the file, then hand it to ``gc --from`` (``-`` reads stdin). Entries can
also be named on the command line, by entry name or project link path:

.. code-block:: bash

    dfm store candidates --tier review --format names --annotate > cleanup.txt
    $EDITOR cleanup.txt
    dfm store gc --from cleanup.txt -y
    dfm store gc ~/projects/old-thing/rundir -y

Explicitly named entries skip the status checks, but never entries in use,
entries used within the last hour (unless ``--force``), or other users'
entries (unless ``--all-users``).

Safety:

* By default ``gc`` only considers your own entries; deletion is also subject
  to filesystem permissions.
* Entries used in the last hour are skipped unless ``--force``, as a backstop
  for filesystems where file locks are unreliable (some NFS setups).
* ``gc`` refuses to run on a directory without a ``.dfm-store.yaml`` marker,
  so a mistyped ``--store`` cannot delete your home directory.

``dfm store gc -y --orphans`` is safe to run from cron.

For scripts and agents
----------------------

Every report has ``--json``: a document with ``"schema": 1`` and a ``kind``
(``store.stats``, ``store.list``, ``store.candidates``, ``store.gc``,
``store.info``). Sizes are in bytes, times are ISO-8601 UTC, and ages are in
seconds (``last_used_age_s``, ``created_age_s``). Each entry carries its
status, link, project root, package, user, host, git remote and branch,
session count, sizes, the largest top-level directories, and -- in
``candidates`` -- ``tier``, ``kind`` and ``reason``. ``list`` and
``candidates`` also print plain lines with ``--format names|links|paths``.

A typical agent loop:

.. code-block:: bash

    dfm store stats --json                     # how full, how much reclaimable
    dfm store candidates --json                # decide what to remove
    dfm store gc --from - -y --json <<'EOF'    # remove the chosen entries
    _home_me_projects_old-exp_rundir
    EOF

Run ``gc --dry-run --json`` first to see exactly what a command would do.

Across hosts
------------

``gc`` decides whether a project still exists by looking for its link. That
works when project directories are visible from the host running ``gc``
(e.g. home directories on NFS). If projects live on host-local disks, an
entry from another host whose path is not visible here is ``unknown``: run
``gc`` on each host, or use ``--include-unknown`` when you know those
projects are gone.

Moving rundirs in and out of the store
======================================

``dfm store migrate``
    Moves the current project's local ``rundir`` into the configured store
    and replaces it with a link. Up-to-date state is preserved, so the next
    run does no unnecessary work.

``dfm store unlink [--local] [--keep]``
    Removes the link. With ``--local`` the contents move back into a local
    ``rundir`` directory. The store entry is deleted unless ``--keep``.

``dfm store relink [--store DIR]``
    Moves the entry to the configured store (or ``DIR``), or recreates a
    dangling link there.

These commands refuse to touch an entry that a running dfm session is using.

Troubleshooting
===============

**"rundir -> ..., but ... does not exist"**
    The rundir link points into a directory that is missing, typically
    because the store filesystem is not mounted. dfm will not silently fall
    back to a local rundir (that would hide results and fill your home
    directory). Mount the store, or:

    * ``dfm store relink`` -- recreate the entry in the configured store
      (``dfm run --store-recreate`` or ``DFM_STORE_RECREATE=1`` does the same
      without stopping, for CI);
    * ``dfm store unlink --local`` -- go back to a local rundir.

    If the link's directory exists but the entry itself is gone (for example
    after ``gc``), dfm recreates it automatically and notes that previous
    results are gone.

**"... is no longer used; the rundir is now ..."**
    Older versions put the rundir in the directory dfm was started from.
    A ``rundir`` left in a subdirectory of the project is now unused and can
    be deleted.

**Locks on NFS**
    Session locks use ``flock``. Where that is unreliable, ``gc`` still skips
    entries used within the last hour.
