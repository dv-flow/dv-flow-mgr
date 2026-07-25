#****************************************************************************
#* summary_ctxt.py
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
"""Resolution and invocation of a task's `summary:` declaration.

A summary is a *post-run* renderer, not a listener: listeners observe the stream
of events during the run, while this runs once over the completed subgraph. That
separation is what lets it behave identically under every UI.
"""

import dataclasses as dc
import logging
from typing import Any, Callable, List, Optional, Tuple

from .task import iter_uses_chain
from . import summary_builtin

_log = logging.getLogger("summary")

BUILTIN_TASK_SUMMARY = "task-summary"

_BUILTINS = (BUILTIN_TASK_SUMMARY,)


def resolve_task_summary(task) -> Optional[Any]:
    """The `summary:` declaration in effect for `task`.

    Walks the `uses:` chain, nearest declaration winning, with **whole-value
    replacement** -- a derived task that wants a different summary restates it.
    Same rule as `elaborate:`, and deliberately not a merge: merging would
    immediately raise "how do I remove an inherited summary?", a question
    `elaborate:` never has to answer.
    """
    if task is None:
        return None
    for current in iter_uses_chain(task):
        decl = getattr(current, 'summary', None)
        if decl:
            return decl
    return None


@dc.dataclass
class SummaryCtxt(object):
    """What a summary callable receives.

    Two data channels, deliberately. `tasks` is the *generic* one -- per-node
    status, markers and timing, enough for a roll-up with zero authoring in the
    subtasks. `output` is the *domain* one -- structured items that subtasks
    emitted and that propagated up through ordinary dataflow, which is what
    makes a "48/50 passed" summary possible at all.
    """

    root : Any
    status : int
    roots : List[Any] = dc.field(default_factory=list)
    verbose : bool = False
    cache_enabled : bool = False

    @property
    def tasks(self) -> List[Tuple[Any, Any]]:
        """[(TaskNode, TaskDataResult)] over the subgraph, in dependency order."""
        return [(n, getattr(n, 'result', None))
                for n in summary_builtin.ordered_nodes(self.roots)]

    @property
    def output(self):
        """The root task's aggregated output items -- the domain channel."""
        out = getattr(self.root, 'output', None)
        if out is None:
            return []
        return getattr(out, 'output', out)

    def markers(self) -> List[Any]:
        """Every marker across the subgraph, flattened, in the same order."""
        ret = []
        for _, result in self.tasks:
            if result is not None and result.markers:
                ret.extend(result.markers)
        return ret

    def task_summary(self):
        """The built-in renderable, so a custom summary can compose with the
        generic roll-up instead of reimplementing it."""
        return summary_builtin.build_task_summary(
            self.roots, verbose=self.verbose, cache_enabled=self.cache_enabled)


def load_summary_fn(ref : str) -> Callable:
    """Import the ``module:function`` (or ``module.function``) named by a
    `summary:` clause. Same accepted spellings as `elaborate:`."""
    import importlib
    sep = ':' if ':' in ref else '.'
    module_name, func_name = ref.rsplit(sep, 1)
    mod = importlib.import_module(module_name)
    return getattr(mod, func_name)


def invoke_summary(decl, ctxt : SummaryCtxt):
    """Produce the summary value for `decl`: a rich renderable, a str, or None.

    A broken user summary must not change the run's verdict, so any exception is
    logged and reported as a note, and the caller carries on with `runner.status`
    untouched.
    """
    if decl is None or decl is False:
        return None

    builtin_name = None
    if isinstance(decl, str):
        if decl in _BUILTINS:
            builtin_name = decl
    else:
        builtin_name = getattr(decl, 'builtin', None)
        if builtin_name is None and isinstance(decl, dict):
            builtin_name = decl.get('builtin')

    if builtin_name is not None:
        if builtin_name != BUILTIN_TASK_SUMMARY:
            _log.error("Unknown builtin summary '%s'; expected one of %s",
                       builtin_name, ", ".join(_BUILTINS))
            return None
        return ctxt.task_summary()

    try:
        fn = load_summary_fn(decl)
    except Exception as e:
        _log.error("Failed to load summary '%s': %s", decl, e)
        return None

    try:
        return fn(ctxt)
    except Exception as e:
        _log.error("Summary '%s' raised: %s", decl, e)
        return None


def is_builtin_summary(decl) -> bool:
    if isinstance(decl, str):
        return decl in _BUILTINS
    name = getattr(decl, 'builtin', None)
    if name is None and isinstance(decl, dict):
        name = decl.get('builtin')
    return name in _BUILTINS


def render_renderable_to_text(value, width : int = 100) -> str:
    """Render a rich renderable to plain text.

    Fixed width and no color, never the terminal's: otherwise the same run
    produces different bytes locally and in CI, which breaks diffs and any
    golden-file test.
    """
    import io
    from rich.console import Console

    buf = io.StringIO()
    Console(file=buf, force_terminal=False, no_color=True, width=width,
            highlight=False).print(value)
    return buf.getvalue()


def summary_file_text(decl, ctxt : SummaryCtxt, value,
                      markdown : bool = False) -> Optional[str]:
    """The text to write to `--summary-file` (or into the report bundle).

    Returns None when nothing should be written -- a `None`-returning summary
    produces no file rather than an empty one.
    """
    if is_builtin_summary(decl):
        # The builtin has native renderers, so a `.md` target gets real
        # markdown -- headings and a table -- not a fenced block of
        # box-drawing characters.
        render = (summary_builtin.render_task_summary_markdown if markdown
                  else summary_builtin.render_task_summary_text)
        return render(ctxt.roots, verbose=ctxt.verbose,
                      cache_enabled=ctxt.cache_enabled)

    if value is None:
        return None

    if isinstance(value, str):
        # The author owns their own markdown; pass it through untouched.
        return value if value.endswith("\n") else value + "\n"

    text = render_renderable_to_text(value)
    if markdown:
        # A rich renderable flattened to text is box drawing, which markdown
        # would mangle. Fence it.
        if not text.endswith("\n"):
            text += "\n"
        text = "```\n%s```\n" % text
    return text
