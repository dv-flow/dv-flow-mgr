###############
Lifecycle Tags
###############

Every task makes an implicit promise about how stable its name, parameters and
outputs are. Lifecycle tags make that promise explicit, so it can be read by a
person browsing ``dfm show task`` and by tools that generate documentation --
rather than living in a comment that nothing can check.

These tags change nothing at runtime. A ``std.Deprecated`` task still runs;
deprecation is a message to whoever reads or maintains the flow file.

Type Definitions
================

All three extend ``std.Tag``.

``std.Stable``
--------------

The task's interface is settled: a project may depend on it and expect a
deprecation cycle before it changes.

``since`` (str, default ``""``)
    Version at which the task became stable. Free-form (e.g. ``"1.4"``).

This is the assumed state of an untagged task, so tag with it only where
saying so out loud earns its keep -- typically alongside ``std.Experimental``
siblings, to mark which of a set is the safe one.

``std.Experimental``
--------------------

The task may change or disappear without a deprecation cycle. It is a promise
about churn, not a claim that the task is broken: the point of the tag is to
let you ship something useful before its interface has settled.

``reason`` (str, default ``""``)
    What is still unsettled, so a reader can judge the risk of depending on
    it.

``std.Deprecated``
------------------

The task should no longer be used.

``reason`` (str, default ``""``)
    Why, in the author's words.

``replacement`` (str, default ``""``)
    The task to use instead. Leave it empty when there is no replacement --
    that is itself worth saying, and is different from having forgotten to
    name one.

``since`` (str, default ``""``)
    Version at which the task was deprecated.

Usage Examples
==============

Retiring a task in favor of another:

.. code-block:: yaml

    tasks:
      - name: build-legacy
        uses: hdl.Compile
        tags:
          - std.Deprecated:
              reason: superseded by the incremental compile flow
              replacement: proj.build
              since: "1.4"

      - name: build
        uses: hdl.CompileIncremental

Shipping a new backend before its parameters have settled:

.. code-block:: yaml

    tasks:
      - name: sim-vlt
        tags:
          - std.Experimental:
              reason: parameter names likely to change

      - name: sim-vcs
        tags:
          - std.Stable:
              since: "1.0"

Reading Them Back
=================

``dfm show task <name>`` prints the tag with whichever parameters were set:

.. code-block:: text

    Tags:
      - std.Deprecated (reason=superseded by the incremental compile flow,
        replacement=proj.build, since=1.4)

``dfm show task <name> --json`` emits the same thing structurally, as
``{"name": ..., "params": {...}}``, which is the form a documentation
generator consumes.
