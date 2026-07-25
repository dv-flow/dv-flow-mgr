#****************************************************************************
#* task_elaborator.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""Per-type task elaboration (Feature A).

A `TaskElaborator` owns how a task type's graph node is built -- its *interior*
(leaf/compound/strategy/control node) and its *needs wiring*. The default
elaborators reproduce the builder's standard behavior exactly; a package may
bind a custom elaborator to a task type (resolved along the `uses` chain) to
take over node construction -- e.g. hdlsim's backend selection (Feature C).

Cross-cutting concerns (override substitution, `iff` evaluation, node
memoization) stay in the builder and run *before* an elaborator is invoked; an
elaborator sees an already-substituted, enabled task. See
docs/dfm_task_elaborator_design.md and
docs/proposals/task_elaboration_impl_plan.md §A.
"""


class ElabCtxt:
    """The surface a `TaskElaborator` uses to build nodes. Implemented by the
    builder (BuilderElabCtxt); documented here as the extension-author contract.

    Construction / default interior:
      buildDefault(task, name, **kw)  -- run the standard kind-based interior
                                         (leaf/compound/strategy/control) + wiring
      mkParams(task)                  -- build and return this task's params model
      mkTaskNode(name_or_task, ...)   -- resolve/build another task's node
      resolveNeed(name)               -- memoized lazy need lookup (== _getTaskNode)

    Needs wiring primitives (used by custom compound/leaf elaborators):
      wireNeed(node, need, block=False)
      wireNeeds(node, needs)
      wireBody(node, task)

    Diagnostics:
      error(msg), marker(marker)

    Cross-elaborator communication (A2.3):
      publish(key, value), lookup(key, default=None)
    """
    # Interface only -- see BuilderElabCtxt for the concrete implementation.
    pass


class TaskElaborator:
    """Base class. `elaborate` returns the constructed TaskNode."""

    def elaborate(self, ctxt: 'ElabCtxt', task, name):
        raise NotImplementedError("TaskElaborator.elaborate not implemented")


class DefaultLeafElaborator(TaskElaborator):
    """Reproduces the builder's leaf-node construction + `_gatherNeeds` wiring."""

    def elaborate(self, ctxt, task, name):
        return ctxt.buildDefault(task, name)


class DefaultCompoundElaborator(TaskElaborator):
    """Reproduces the builder's compound-node construction. Subclasses may
    override `selectNeeds` to wire only a subset of the declared needs; the body
    (`wireBody`) is always built in full."""

    def elaborate(self, ctxt, task, name):
        return ctxt.buildDefault(task, name, select_needs=self._select)

    def _select(self, needs):
        return self.selectNeeds(needs)

    def selectNeeds(self, needs):
        """Hook: given the task's declared needs, return the subset to wire.
        Default: all of them.

        `needs` is a list of **Task** objects (see ElabCtxt.declaredNeeds), so a
        filter may match on `.name`, `.tags`, or the `uses` chain.

        Two contract points, both easy to get wrong:

        * **Invoked once per `uses`-chain level.** `_gatherNeeds` recurses into
          `task.uses` *before* filtering, so a task whose base also declares
          needs calls this several times, each with one level's needs. A filter
          must be idempotent and must not assume it sees the full set at once.
        * **A pruned need is never built.** Filtering happens before the need is
          resolved into a node, so everything reachable only through that edge
          drops out of the graph -- unlike `iff:`, which builds a disabled stub.
          That is the point: deselecting a test also skips building whatever
          only it needed.
        """
        return needs


class DefaultStrategyElaborator(TaskElaborator):
    """Reproduces the builder's strategy (generate/matrix) construction."""

    def elaborate(self, ctxt, task, name):
        return ctxt.buildDefault(task, name)


class DefaultControlElaborator(TaskElaborator):
    """Reproduces the builder's control-flow (if/while/match/...) construction."""

    def elaborate(self, ctxt, task, name):
        return ctxt.buildDefault(task, name)
