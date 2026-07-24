Task Elaboration
================

Normally the builder decides how a task's graph node is constructed: it looks at
the task (leaf, compound, strategy, control), builds the interior, and wires up
its ``needs``. **Task elaboration** lets a task *type* take over that step with a
bound ``TaskElaborator``. The default elaborators reproduce the standard
behavior exactly, so this is an opt-in extension point — existing flows are
unaffected.

The motivating example is simulator backend selection: an author writes the
generic ``uses: hdlsim.SimImage`` and selects the simulator once (``-D
hdlsim.sim=vlt``); an elaborator bound to ``hdlsim.SimImage`` reads the resolved
``sim`` and dispatches to the concrete ``hdlsim.vlt.SimImage`` backend.

For users: backend-selecting tasks
----------------------------------

You rarely interact with elaboration directly. When a package ships a
backend-selecting task (like ``hdlsim``), you:

1. write the generic ``uses:`` (e.g. ``uses: hdlsim.SimImage``), and
2. select the backend once, via any of the :doc:`scoped-variable <scoped_variables>`
   mechanisms — ``-D hdlsim.sim=vlt`` globally, a ``sim`` variable in your
   package, or a ``let: { sim: … }`` scope over a subtree.

Dispatch to the concrete backend is automatic. The explicit form
(``uses: hdlsim.vlt.SimImage``) still works and always takes precedence — if you
name a concrete backend, no selection happens.

For extension authors: the API
-------------------------------

An elaborator is a small Python class bound to a task **type**. Binding resolves
along the ``uses`` chain, so binding an abstract type covers every task that
``uses:`` it (nearest binding wins). ``needs`` never participate in resolution.

.. code-block:: python

    from dv_flow.mgr.task_elaborator import TaskElaborator

    class BackendSelect(TaskElaborator):
        def elaborate(self, ctxt, task, name):
            sim = ctxt.resolveParam(task, "sim", "unset")
            if sim == "unset":
                ctxt.error("No simulator selected for '%s'" % name)
                raise Exception("no simulator selected")
            # rebind `uses` to the concrete backend and build normally
            import dataclasses as dc
            concrete = ctxt.getTask("hdlsim.%s.SimImage" % sim)
            return ctxt.buildDefault(dc.replace(task, uses=concrete, paramT=None), name)

The ``ctxt`` (an ``ElabCtxt``) is how an elaborator builds nodes:

``buildDefault(task, name, select_needs=None)``
    Run the standard kind-based interior (leaf/compound/strategy/control) and
    needs wiring. Delegating to this is how you reuse normal behavior.
``mkParams(task)`` / ``resolveParam(task, name, default)``
    Build the task's params (evaluating ``resolve()``) and read one.
``mkTaskNode(name, …)`` / ``resolveNeed(name)`` / ``getTask(name)``
    Build another task's node, resolve a need (memoized), or look up a task type
    without building it.
``wireNeed`` / ``wireNeeds``
    Wire ``needs`` onto a node you built yourself.
``error(msg)`` / ``marker(marker)``
    Emit diagnostics through the builder.
``publish(key, value)`` / ``lookup(key, default)``
    Pass values from an enclosing elaborator down to nested ones. Because the
    build is lazy and top-down, a publisher always elaborates before the
    descendants that ``lookup`` it.
``args``
    Build-global arguments (root package params). **Root-only**: only the
    outermost elaborator may read ``args``; a nested elaborator that does is a
    build error. This keeps elaboration output a function of the task name so
    name-keyed memoization stays sound — pass context down with ``publish`` /
    ``lookup`` instead.

The ``selectNeeds`` hook
------------------------

A compound elaborator can subclass ``DefaultCompoundElaborator`` and override
``selectNeeds`` to wire only a subset of the declared needs (the body is always
built in full):

.. code-block:: python

    from dv_flow.mgr.task_elaborator import DefaultCompoundElaborator

    class RunSelected(DefaultCompoundElaborator):
        def selectNeeds(self, needs):
            return [n for n in needs if n.name in self._chosen]

Registering an elaborator
-------------------------

Elaborators are Python, registered by the owning package's extension module via
a ``dvfm_elaborators()`` hook that returns ``{type_name: factory}`` (each factory
is a zero-arg callable returning a fresh elaborator instance):

.. code-block:: python

    # in your package's __ext__.py
    def dvfm_elaborators():
        from .backend_select import BackendSelect
        return {"mypkg.MyAbstractTask": lambda: BackendSelect()}

There is no YAML ``elaborate:`` field; elaborators are code shipped with the
package.

See also the design note ``docs/dfm_task_elaborator_design.md`` for the
rationale and the invariants (behavior-preserving default, ``uses``-chain
binding, root-only parameterization).
