##############################
Conditional & Iterative Tasks
##############################

Most flows are static dependency graphs. Sometimes, though, you need a step
that branches on a value or repeats until a condition is met -- "run this body
only if the input matches," "retry until it succeeds," "refine for up to N
rounds." A task expresses this with a ``control:`` block.

``control:`` turns a compound task into one of five constructs selected by
``type:``:

* ``if`` -- run one branch or another based on a condition.
* ``match`` -- pick the first matching case (a multi-way branch).
* ``while`` -- repeat *while* a pre-condition holds (0 or more times).
* ``do-while`` -- repeat *until* a post-condition holds (1 or more times).
* ``repeat`` -- repeat a fixed number of times, with optional early exit.

``control:`` is mutually exclusive with ``strategy:`` (a task uses one or the
other). It is independent of ``iff:`` -- ``iff:`` gates whether the task runs at
all, while ``control:`` shapes how its body runs once it does.

Conditions are ``${{ }}`` expressions and may reference the task's input
(``${{ in.<field> }}``), loop state (``${{ state.<field> }}``), and the
auto-injected iteration counters ``${{ _iter }}`` / ``${{ _max_iter }}``.

if
==

``if`` evaluates ``cond`` once. If it is true, the task's ``body:`` runs; if it
is false, the ``else:`` branch (declared *inside* ``control:``) runs, or the
task passes its input through if there is no ``else:``.

.. code-block:: yaml

    tasks:
    - name: check_value
      run: echo '{"value":5}'

    - root: conditional_task
      needs: [check_value]
      control:
        type: if
        cond: '${{ in.value == 5 }}'
        else:
          - name: when_not_five
            run: echo "Value is not 5"
      body:
        - name: when_five
          run: echo "Value is 5"

The "then" branch is the task-level ``body:``; the "else" branch is
``control.else:``.

match
=====

``match`` evaluates each entry in ``cases`` in order and runs the ``body:`` of
the **first** case whose ``when:`` condition is true. A case marked
``default: true`` runs when no earlier case matches. If nothing matches and
there is no default, the task passes through.

.. code-block:: yaml

    - root: route_task
      control:
        type: match
        cases:
          - when: '${{ in.category == "bug" }}'
            body:
              - name: fix_bug
                run: echo "Fixing bug"
          - when: '${{ in.category == "feature" }}'
            body:
              - name: add_feature
                run: echo "Adding feature"
          - default: true
            body:
              - name: log_unknown
                run: echo "Unknown category"

Each case carries its own ``body:`` (inside the case); only one case runs.

while
=====

``while`` is a **pre-condition** loop: it checks ``cond`` *before* each
iteration, so the body may run zero times. ``max_iter`` is required and bounds
the loop. ``state:`` seeds values that the condition and body can read.

.. code-block:: yaml

    - root: wait_loop
      control:
        type: while
        cond: '${{ state.status != "ready" }}'
        max_iter: 10
        state:
          init:
            status: pending
            attempt: 0
      body:
        - name: check_status
          run: echo "checking..."

The loop runs at most ``max_iter`` times and stops as soon as ``cond`` becomes
false.

do-while
========

``do-while`` is a **post-condition** loop: the body always runs at least once,
then ``until`` is checked *after* each iteration. ``max_iter`` is required. This
fits "attempt, then decide whether to retry" patterns.

.. code-block:: yaml

    - root: retry_loop
      control:
        type: do-while
        until: '${{ state.success == true }}'
        max_iter: 3
        state:
          init:
            success: false
            attempt: 0
      body:
        - name: attempt_task
          run: echo "attempting..."

The loop repeats until ``until`` is true or ``max_iter`` is reached.

repeat
======

``repeat`` runs the body a fixed ``count`` times. An optional ``until:``
condition lets it exit early once satisfied.

.. code-block:: yaml

    - root: refine_loop
      control:
        type: repeat
        count: 5
        until: '${{ state.quality >= 0.9 }}'
        state:
          init:
            quality: 0.5
      body:
        - name: improve
          run: echo "refining..."

The body runs up to ``count`` times, stopping early if ``until`` becomes true.

Carrying state across iterations
================================

Loops (``while``, ``do-while``, ``repeat``) maintain a ``state`` dictionary:

* ``state.init`` provides the values for the first iteration. They are readable
  in conditions and bodies as ``${{ state.<field> }}``.
* A loop body reports updated values by **producing output items** whose data
  fields are merged into ``state`` for the next iteration. This is how a loop
  makes progress -- e.g. a body that emits ``success: true`` lets a
  ``do-while`` ``until: '${{ state.success == true }}'`` terminate.
* The counters ``${{ _iter }}`` (0-based) and ``${{ _max_iter }}`` are available
  inside the loop.
* A body that emits ``_break: true`` causes the loop to exit immediately.

.. note::

   ``control:`` constructs are compound tasks: every ``body:`` (and each
   ``match`` case body, and the ``else:`` branch) is a list of ordinary tasks
   that may have their own ``needs``, parameters, and implementations. Bounded
   loops (``max_iter`` / ``count``) are required so a flow always terminates.

See Also
========

* :doc:`expressions` -- the expression syntax used in ``cond`` / ``until`` /
  ``when``.
* :doc:`tasks` -- compound tasks and task bodies.
* :doc:`error_handling` -- handling failures within a task body.
