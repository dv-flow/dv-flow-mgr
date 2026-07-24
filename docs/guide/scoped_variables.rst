Scoped Variables and Overrides
==============================

An enclosing task can shape the tasks in its subtree with a ``set:`` block. It
fills the gap between the two other ways of passing values:

* **global** package parameters, visible everywhere, and
* **explicit** ``with:`` parameters, passed to one task at a time.

``set:`` does two related things over a subtree:

* **rebind a package variable** — change what an ordinary ``${{ pkg.var }}``
  reference resolves to, for the whole subtree (or a matched part of it), and
* **force a parameter** — set a parameter on the descendant instances selected
  by a matcher, overriding their ``with:``.

This is useful when a value (a simulator selection, an optimization level, a
target) should flow down to whatever tasks in a subtree care about it, without
threading it through every intervening ``with:``.

.. note::

   ``set:`` supersedes the older ``let:`` block and the :ref:`resolve()
   <scoped-resolution>` function. ``let:``/``resolve()`` still work but are
   deprecated; see :ref:`migration <set-migration>` below. The chief difference:
   a value provided by ``set:`` is read by an **ordinary** ``${{ pkg.var }}``
   reference (not a special function), and ``set:`` overrides ``with:``.

``with:`` versus ``set:``
-------------------------

The two blocks look similar but do opposite things:

============  ======================================  ===============================
Block         Configures                              Read by
============  ======================================  ===============================
``with:``     *this* task's own parameters            the task implementation
``set:``      *this task's subtree*                   ordinary ``${{ pkg.var }}`` reads / matched instances
============  ======================================  ===============================

``with:`` answers "configure me." ``set:`` answers "shape my subtree." A ``set:``
never sets the providing task's own parameters.

The model: declare, read, rebind
---------------------------------

**1. Declare an axis** once, as a package variable:

.. code-block:: yaml

    package:
      name: hdlsim
      with:
        sim: {type: str, value: "unset"}     # the axis + its default

**2. Read it** by an ordinary reference, in a parameter default and/or in a
``uses:`` for variant selection:

.. code-block:: yaml

    - name: SimRun
      with:
        sim:
          type: str
          value: "${{ hdlsim.sim }}"          # ordinary read of the package var

**3. Rebind it** for a subtree with ``set:``:

.. code-block:: yaml

    - name: regression
      set:
      - hdlsim.sim: mti          # every ${{ hdlsim.sim }} in this subtree now reads 'mti'
      body:
      - name: smoke
        uses: SimRun
      - name: full
        uses: SimRun

The value under a **package-qualified** name (``hdlsim.sim``) is a *rebind*: any
ordinary ``${{ hdlsim.sim }}`` reference in the subtree resolves to it.

The ``set:`` grammar
--------------------

``set:`` is a **list**. Each item is either:

* an **assignment** — a map ``{<name>: <value>}``; or
* a **scope item** — ``{uses?: <glob>, path?: <glob>, set: [ ... ]}`` (identified
  by having a nested ``set:``), which narrows the assignments inside it to the
  descendants its matchers select.

.. code-block:: yaml

    set:
    - hdlsim.sim: mti                    # (a) global rebind for the subtree
    - uses: "hdlsim.*"                    # (b) scope item: match by uses-chain
      path: "regress/**"                 #     AND by instance path
      set:
      - hdlsim.sim: xcm                  #     narrowed rebind (only matched readers)
      - opt: "-O3"                        #     forced param on matched instances

Qualified vs. bare names
~~~~~~~~~~~~~~~~~~~~~~~~~~

* A **package-qualified** name (contains a dot, e.g. ``hdlsim.sim``) is a
  **variable rebind** — it changes what ``${{ hdlsim.sim }}`` reads. Under a
  scope item it is *narrowed* to the matched readers.
* A **bare** name (e.g. ``opt``) under a scope item **forces that parameter** on
  the matched instances, overriding their ``with:``. (A bare name at the top
  level, with no matcher, has no target and is reported as an info message.)

Matchers
~~~~~~~~

* ``uses:`` is an *is-a* glob over the node's ``uses`` chain of task type-names,
  so ``uses: "hdlsim.*"`` matches any task derived (directly or indirectly) from
  an ``hdlsim`` task.
* ``path:`` is a glob over the instance's hierarchical path, where ``*`` matches
  one path segment and ``**`` matches any depth.
* Both on one scope item are **AND**-combined; nesting scope items narrows
  further.

Recipe: sweep across simulators
-------------------------------

Combine a ``matrix`` strategy with ``set:`` to run a subtree once per simulator.
The ``set:`` binding is evaluated **per matrix cell**:

.. code-block:: yaml

    - name: run-all-sims
      strategy:
        matrix:
          sim: ['vlt', 'mti']
      set:
      - hdlsim.sim: "${{ matrix.sim }}"
      body:
      - name: body
        uses: RunSims       # RunSims (and its subtree) read ${{ hdlsim.sim }}

Recipe: pick a simulator per leg
--------------------------------

Set a subtree default and override one leg with a narrowed rebind:

.. code-block:: yaml

    - name: regression
      set:
      - hdlsim.sim: vlt                    # subtree default
      - path: "**/smoke*"                  # the smoke leg only ...
        set:
        - hdlsim.sim: mti                  # ... runs on mti
      body:
      - name: build
        uses: hdlsim.SimImage
      - name: smoke
        uses: hdlsim.SimImage

Precedence
----------

Values follow **outer overrides inner**, with the CLI as the ceiling. Highest to
lowest:

1. **CLI / ``-D``** — ``-D <pkg>.<name>=<value>`` always wins; the operator is
   final.
2. **package level** — reserved for a future tier.
3. **task ``set:``** — overrides any ``with:`` in its compound tree; an
   outer/container ``set:`` overrides an inner/nested one for the same name.
   Within one ``set:`` block, a matcher-narrowed rebind beats a global one.
4. **instance ``with:``**.
5. the **declared default**.

Consequences:

* ``set:`` is forceful **downward** — only a package-level (future) or CLI
  override can beat an ancestor's ``set:``. To let a leg choose, put the choice
  *at that leg*, not at an ancestor and then "override" it (the ancestor wins).
* Select a simulator globally from the command line, and a subtree can still
  narrow it:

  .. code-block:: bash

      dfm run build -D hdlsim.sim=vlt        # global default for the whole build

.. _set-migration:

Migrating from ``let:`` / ``resolve()``
---------------------------------------

``let:``/``resolve()`` still work but are deprecated. To migrate:

============================================  ==============================================
Old                                           New
============================================  ==============================================
``resolve('sim', 'vlt')`` in a value          declare ``pkg.sim`` (default ``vlt``); read ``${{ pkg.sim }}``
``let: { sim: mti }``                          ``set: [ { pkg.sim: mti } ]``  (qualified name)
per-instance selection                         ``set: [ { uses: "pkg.*", set: [ { param: v } ] } ]``
============================================  ==============================================

Note two intentional differences: a ``set:`` value is read by an ordinary
``${{ pkg.var }}`` reference (``let:`` required ``resolve()``), and ``set:``
**overrides** ``with:`` (``let:`` lost to ``with:``).

Gotchas
-------

* **A ``set:`` on a leaf task affects nothing** — a leaf has no subtree.
* **A scope item must have a ``set:``** key; ``uses:``/``path:`` are its
  matchers. A parameter may not be named ``set``.
* **A matcher that selects nothing** in the whole subtree emits an info message —
  useful for catching a typo'd ``uses:``/``path:`` glob.
* **``set:`` is evaluated per matrix cell**, so
  ``set: [ { hdlsim.sim: "${{ matrix.sim }}" } ]`` yields a distinct value per
  expansion.
