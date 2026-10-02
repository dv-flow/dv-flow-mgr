#****************************************************************************
#* test_select.py
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
"""Graph-build test selection: the engine behind `std.TestRunner` and
`std.TestInfo`.

A test-running root receives the available tests and suites as `needs:`. This
module reads that need-set as a **suite tree**, resolves a command-line
selection against it, and prunes the graph **at graph build**, so a deselected
test is *never built* -- not built-and-skipped. Everything reachable only
through a pruned edge drops out too, which is why deselecting a DUT view also
skips compiling that view's simulation image.

That is the point of doing it here rather than with `iff:`, which was the
earlier design: `iff: false` still constructs a stub node, and its upstream
image still gets built.

The tree
--------
* **a test** -- a task carrying a `std.Test` tag, kept or dropped whole;
* **a matrix suite** -- a matrix task whose cells are tests. It is rebuilt as a
  locally-derived variant whose axes hold only the selected cells, so
  unselected cells are never generated;
* **a collector suite** -- a task that `uses: std.TestSuite` (or carries a
  `std.TestSuite` tag); its members are its own `needs:`, which may be tests or
  further suites. That is how super-suites nest.

A test's **path** is its position in that tree relative to the runner
(`sanity.reset`). Membership is by reference, so a test reachable through two
suites has two paths but is one test.

Needs that are none of these -- an image, a flags item, a helper -- are
**always kept** at the runner level. Selection must never break the build.

Both `std.TestRunner` and `std.TestInfo` go through `build_tree` + `resolve`,
so what the inventory reports and what a run selects cannot disagree.
"""

import dataclasses as dc
import fnmatch
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ..task import Strategy, iter_uses_chain

_log = logging.getLogger("test_select")

TEST_TAG = "std.Test"
SUITE_TAG = "std.TestSuite"
SUITE_TASK = "std.TestSuite"


class SelectionError(Exception):
    """A selection that cannot be honored. Raised rather than reported-and-
    continued: every failure mode here ends in a run that tests less than the
    user asked for, and the worst of them is a green run that tested nothing."""


# ---------------------------------------------------------------------------
# Selection spec
# ---------------------------------------------------------------------------

@dc.dataclass
class Selection(object):
    """What the user asked to run. An empty dimension means "all of it"."""

    tests : List[str] = dc.field(default_factory=list)
    views : List[str] = dc.field(default_factory=list)
    exclude : List[str] = dc.field(default_factory=list)
    test_key : str = "name"
    view_axis : str = "view"

    @classmethod
    def from_params(cls, params) -> 'Selection':
        return cls(
            tests=_as_list(getattr(params, "tests", None)),
            views=_as_list(getattr(params, "views", None)),
            exclude=_as_list(getattr(params, "exclude", None)),
            test_key=getattr(params, "test_key", None) or "name",
            view_axis=getattr(params, "view_axis", None) or "view")

    @property
    def active(self) -> bool:
        return bool(self.tests or self.views or self.exclude)

    def wants_view(self, view) -> bool:
        return not self.views or view in self.views


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Defensive: the ladder coerces a `-D a,b` into a list before we see it.
        return [v for v in (s.strip() for s in value.split(",")) if v]
    return [str(v) for v in value]


# ---------------------------------------------------------------------------
# Path patterns
# ---------------------------------------------------------------------------
#
# A pattern is matched against test paths, segment by segment:
#
#   reset            any test or suite whose trailing segment is `reset`
#   sanity.reset     that trailing sequence, anywhere in the tree
#   sanity.          everything under a suite named `sanity` (suites only)
#   .sanity.reset    anchored at the runner
#   uart.fifo_*      `*`/`?`/`[...]` glob within one segment
#   regress.**.x     `**` spans any number of segments
#
# Left-unanchored by default so a bare name (`--tests arb`) keeps working, and
# because short names are what people type. Globs, not substrings: `arb` does
# not match `arb_eq`.

@dc.dataclass
class Pattern(object):
    text : str
    segs : List[str]
    anchored : bool = False
    suites_only : bool = False

    @classmethod
    def parse(cls, text : str) -> 'Pattern':
        raw = text.strip()
        if "@" in raw or re.search(r"\[[^\]]*=", raw):
            # `@seed` and `[view=...]` are reserved for instance selection,
            # which is not implemented yet. Refuse rather than glob-match the
            # characters literally and select nothing.
            raise SelectionError(
                "'%s': selecting a specific seed (@) or variant ([k=v]) is not "
                "supported yet. Use --views to select a view." % text)
        anchored = raw.startswith(".")
        suites_only = raw.endswith(".") and len(raw) > 1
        body = raw.strip(".")
        segs = body.split(".") if body else []
        if not segs or any(s == "" for s in segs):
            raise SelectionError(
                "'%s' is not a valid test pattern: expected dot-separated "
                "names, e.g. 'sanity.reset' or 'sanity.'" % text)
        return cls(text=text, segs=segs, anchored=anchored,
                   suites_only=suites_only)

    def _match(self, path : Tuple[str, ...]) -> bool:
        segs = self.segs if self.anchored else ["**"] + self.segs
        return _match_segs(segs, list(path))

    def selects(self, path : Tuple[str, ...]) -> bool:
        """Whether this pattern selects the test at `path`: it matches the
        test's own path, or the path of a suite enclosing it."""
        last = len(path) if not self.suites_only else len(path) - 1
        for k in range(1, last + 1):
            if self._match(path[:k]):
                return True
        return False


def _match_segs(pat : List[str], path : List[str]) -> bool:
    if not pat:
        return not path
    head = pat[0]
    if head == "**":
        return any(_match_segs(pat[1:], path[i:]) for i in range(len(path) + 1))
    if not path:
        return False
    return (fnmatch.fnmatchcase(path[0], head)
            and _match_segs(pat[1:], path[1:]))


def format_path(path : Tuple[str, ...]) -> str:
    return ".".join(path)


# ---------------------------------------------------------------------------
# Reading tags off a task
# ---------------------------------------------------------------------------

def test_tag(task) -> Optional[Any]:
    """The `std.Test` tag's resolved values for `task`, or None.

    A tag instance materializes its values into `paramT`, so the fields are read
    as ordinary attributes. Note the instance does *not* keep a `uses` link back
    to its declared type (`_instantiateTag` builds a fresh `Type`), so an is-a
    test is impossible -- hence the structural fallback: any tag exposing a
    `case` field is treated as a test tag, which lets a project derive its own
    tag type from `std.Test`.
    """
    for tag in getattr(task, "tags", None) or []:
        values = getattr(tag, "paramT", None)
        if values is None:
            continue
        if getattr(tag, "name", None) == TEST_TAG or hasattr(values, "case"):
            return values
    return None


def suite_tag(task) -> Optional[Any]:
    """The `std.TestSuite` tag's resolved values for `task`, or None."""
    for tag in getattr(task, "tags", None) or []:
        values = getattr(tag, "paramT", None)
        if values is not None and getattr(tag, "name", None) == SUITE_TAG:
            return values
    return None


def _uses_suite_task(task) -> bool:
    return any(getattr(t, "name", None) == SUITE_TASK
               for t in iter_uses_chain(task))


def _short_name(task) -> str:
    name = getattr(task, "name", "") or ""
    return name.rpartition(".")[2] or name


def _matrix_of(task):
    """The task's matrix axes if it is a matrix strategy task, else None."""
    strategy = getattr(task, "strategy", None)
    if strategy is None:
        return None
    matrix = getattr(strategy, "matrix", None)
    return matrix if matrix else None


def _case_axis(matrix, test_key):
    """The axis whose cells are maps carrying `test_key` -- the case axis."""
    for axis, values in matrix.items():
        if isinstance(values, list) and any(
                isinstance(v, dict) and test_key in v for v in values):
            return axis
    return None


def _check_segment(name, what, task):
    if "." in name:
        raise SelectionError(
            "%s name '%s' (task %s) contains '.', which separates the segments "
            "of a test path. Rename it, or set `name:` on its tag."
            % (what, name, getattr(task, "name", "?")))
    return name


# ---------------------------------------------------------------------------
# The suite tree
# ---------------------------------------------------------------------------

@dc.dataclass
class TestEntry(object):
    """One test. `key` identifies it independently of how it was reached."""
    key : Tuple[str, Optional[str]]     # (task name, cell name or None)
    name : str                           # its own path segment
    task : Any
    paths : List[Tuple[str, ...]] = dc.field(default_factory=list)
    views : List[str] = dc.field(default_factory=list)
    views_open : bool = False
    # A tagged test's single view ("" when it declares none). None for a test
    # whose views are a matrix axis.
    view : Optional[str] = None

    @property
    def path(self) -> Tuple[str, ...]:
        """The canonical path: the first one, in declaration order."""
        return self.paths[0]


@dc.dataclass
class SuiteEntry(object):
    task : Any
    name : str
    kind : str                           # 'collector' | 'matrix'
    paths : List[Tuple[str, ...]] = dc.field(default_factory=list)
    members : List[Any] = dc.field(default_factory=list)   # collector: Tasks
    tests : List[Tuple] = dc.field(default_factory=list)   # matrix: test keys
    # Matrix suites only.
    case_axis : Optional[str] = None
    view_axis : Optional[str] = None
    views : Optional[List[str]] = None   # None = unknowable expression axis

    @property
    def path(self) -> Tuple[str, ...]:
        return self.paths[0]


@dc.dataclass
class Tree(object):
    """The runner's suite tree. Dicts preserve declaration order."""
    root : Any
    tests : Dict[Tuple, TestEntry] = dc.field(default_factory=dict)
    suites : Dict[str, SuiteEntry] = dc.field(default_factory=dict)
    # Task-level classification, keyed by task name: 'test', 'matrix',
    # 'collector', 'other'.
    kinds : Dict[str, str] = dc.field(default_factory=dict)
    # Runner-level needs that are not tests (reported; always kept).
    other : List[str] = dc.field(default_factory=list)
    # Matrix-axis tests (view-only matrices): task name -> (axis, views).
    matrix_tests : Dict[str, Tuple[str, Optional[List[str]]]] = dc.field(
        default_factory=dict)


def _resolve_views(matrix, view_axis, expand):
    """(axis name or None, list of views or None when unknowable)."""
    if view_axis not in matrix:
        return None, None
    values = matrix[view_axis]
    if not isinstance(values, list) and expand is not None:
        # The axis is an expression (`image: "${{ images }}"`). Resolve it so
        # its members are validatable; without this a mistyped view is bound
        # literally and fails much later, deep in the flow, with an error that
        # names neither the view nor the flag that set it.
        resolved = expand(values)
        if isinstance(resolved, list):
            values = resolved
    if isinstance(values, list):
        return view_axis, [str(v) for v in values]
    return view_axis, None


def build_tree(root_task, needs_of, test_key="name", view_axis="view",
               expand=None) -> Tree:
    """Read `root_task`'s declared needs as a suite tree.

    `needs_of(task)` returns a task's declared needs (the elaboration
    context's `declaredNeeds`); `expand` evaluates a `${{ }}` expression.
    """
    tree = Tree(root=root_task)

    def add_test(key, name, task, path, views=None, views_open=False,
                 view=None):
        entry = tree.tests.get(key)
        if entry is None:
            entry = TestEntry(key=key, name=name, task=task,
                              views=list(views or []), views_open=views_open,
                              view=view)
            tree.tests[key] = entry
        entry.paths.append(path)

    def walk(task, prefix, stack, top):
        for need in needs_of(task):
            name = getattr(need, "name", "") or ""
            matrix = _matrix_of(need)
            ttag = test_tag(need)
            stag = suite_tag(need)

            if matrix is not None:
                case_axis = _case_axis(matrix, test_key)
                vaxis, views = _resolve_views(matrix, view_axis, expand)
                if case_axis is not None:
                    seg = _check_segment(
                        str(getattr(stag, "name", "") or "") or _short_name(need),
                        "Suite", need)
                    path = prefix + (seg,)
                    suite = tree.suites.get(name)
                    if suite is None:
                        suite = SuiteEntry(task=need, name=seg, kind="matrix",
                                           case_axis=case_axis,
                                           view_axis=vaxis, views=views)
                        tree.suites[name] = suite
                        tree.kinds[name] = "matrix"
                    suite.paths.append(path)
                    for cell in matrix[case_axis]:
                        if not (isinstance(cell, dict) and test_key in cell):
                            continue
                        cname = _check_segment(str(cell[test_key]), "Test", need)
                        key = (name, cname)
                        if key not in suite.tests:
                            suite.tests.append(key)
                        add_test(key, cname, need, path + (cname,),
                                 views=views or [],
                                 views_open=(vaxis is not None and views is None))
                    continue
                if vaxis is not None:
                    # A matrix over views only: the task itself is the test,
                    # run once per view.
                    seg = _check_segment(
                        str(getattr(ttag, "name", "") or getattr(ttag, "case", "")
                            or "") or _short_name(need), "Test", need)
                    tree.kinds[name] = "test"
                    tree.matrix_tests[name] = (vaxis, views)
                    add_test((name, None), seg, need, prefix + (seg,),
                             views=views or [], views_open=views is None)
                    continue
                # A matrix that is neither: infrastructure.

            elif ttag is not None:
                seg = _check_segment(
                    str(getattr(ttag, "name", "") or getattr(ttag, "case", "")
                        or "") or _short_name(need), "Test", need)
                view = str(getattr(ttag, "view", "") or "")
                tree.kinds[name] = "test"
                add_test((name, None), seg, need, prefix + (seg,),
                         views=[view] if view else [], view=view)
                continue

            elif stag is not None or _uses_suite_task(need):
                if name in stack:
                    raise SelectionError(
                        "test suites form a cycle: %s"
                        % " -> ".join(stack[stack.index(name):] + [name]))
                seg = _check_segment(
                    str(getattr(stag, "name", "") or "") or _short_name(need),
                    "Suite", need)
                path = prefix + (seg,)
                suite = tree.suites.get(name)
                if suite is None:
                    suite = SuiteEntry(task=need, name=seg, kind="collector",
                                       members=list(needs_of(need)))
                    tree.suites[name] = suite
                    tree.kinds[name] = "collector"
                suite.paths.append(path)
                walk(need, path, stack + [name], False)
                continue

            tree.kinds.setdefault(name, "other")
            if top and name not in tree.other:
                tree.other.append(name)

    walk(root_task, (), [getattr(root_task, "name", "")], True)
    return tree


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

@dc.dataclass
class Resolution(object):
    """The outcome of resolving a Selection against a Tree."""
    selection : Selection
    kept : Dict[Tuple, bool] = dc.field(default_factory=dict)
    # Matrix task name -> its narrowed axes, when narrowing changed anything.
    narrowed : Dict[str, Dict[str, Any]] = dc.field(default_factory=dict)
    # Task names withheld entirely: dropped tests and empty suites.
    dropped : set = dc.field(default_factory=set)
    # Views each kept matrix will actually run on (matrix task name -> views).
    run_views : Dict[str, Optional[List[str]]] = dc.field(default_factory=dict)
    warnings : List[str] = dc.field(default_factory=list)

    def kept_tests(self, tree : Tree) -> List[TestEntry]:
        return [t for k, t in tree.tests.items() if self.kept.get(k)]


def resolve(tree : Tree, sel : Selection) -> Resolution:
    """Apply `sel` to `tree`, in a fixed order:

    1. selectors -- `--tests` patterns, unioned (none: every test);
    2. filters   -- `--views`;
    3. excludes  -- `--exclude` patterns, which win last.

    Raises SelectionError for any selection that would silently under-run.
    """
    res = Resolution(selection=sel)
    patterns = [Pattern.parse(p) for p in sel.tests]
    excludes = [Pattern.parse(p) for p in sel.exclude]

    if sel.active and not tree.tests:
        raise SelectionError(
            "a test selection was given, but none of this task's needs are "
            "recognizable as tests. Tag a case with `tags: [{std.Test: "
            "{name: <name>}}]`, or give a suite a matrix axis whose cells "
            "carry a '%s' field." % sel.test_key)

    hits = [0] * len(patterns)
    ex_hits = [0] * len(excludes)
    for key, t in tree.tests.items():
        selected = not patterns
        for i, p in enumerate(patterns):
            if any(p.selects(path) for path in t.paths):
                hits[i] += 1
                selected = True
        excluded = False
        for i, p in enumerate(excludes):
            if any(p.selects(path) for path in t.paths):
                ex_hits[i] += 1
                excluded = True
        view_ok = True
        if t.view is not None:
            # A tagged test: its one view (or none) against --views.
            view_ok = sel.wants_view(t.view) if t.view else not sel.views
        res.kept[key] = selected and not excluded and view_ok

    unmatched = [p.text for p, n in zip(patterns, hits) if n == 0]
    if unmatched:
        available = sorted(format_path(t.path) for t in tree.tests.values())
        raise SelectionError(
            "no test matches %s. Available: %s" % (
                ", ".join("'%s'" % u for u in unmatched),
                ", ".join(available) if available else "(none)"))
    for p, n in zip(excludes, ex_hits):
        if n == 0:
            res.warnings.append("--exclude '%s' matches no test" % p.text)

    # Views. Only validate when EVERY view axis was knowable: a suite whose axis
    # is an expression contributes no names, so an incomplete offered-set would
    # reject a perfectly good view -- the false positive that matters most.
    offered_views = []
    views_open = False
    for t in tree.tests.values():
        views_open = views_open or t.views_open
        for v in t.views:
            if v not in offered_views:
                offered_views.append(v)
    if sel.views and offered_views and not views_open:
        unmatched_v = [v for v in sel.views if v not in offered_views]
        if unmatched_v:
            raise SelectionError(
                "no view matches %s. Available: %s" % (
                    ", ".join("'%s'" % u for u in unmatched_v),
                    ", ".join(sorted(offered_views))))

    # Matrix narrowing: the case axis to the kept cells, the view axis to the
    # selected views. A matrix that filters down to nothing is dropped -- an
    # empty matrix would otherwise build a suite that runs nothing.
    def narrow_views(name, matrix, vaxis, views):
        if vaxis is None:
            return None, False
        if views is None:
            if sel.views:
                # Unknowable axis: bind the named views literally; there is
                # nothing to validate them against.
                res.run_views[name] = list(sel.views)
                return list(sel.views), True
            res.run_views[name] = None
            return None, False
        kept_v = [v for v in matrix[vaxis] if sel.wants_view(str(v))] \
            if isinstance(matrix[vaxis], list) else \
            [v for v in views if sel.wants_view(v)]
        res.run_views[name] = [str(v) for v in kept_v]
        changed = (not isinstance(matrix[vaxis], list)
                   or len(kept_v) != len(matrix[vaxis]))
        return kept_v, changed

    for name, suite in tree.suites.items():
        if suite.kind != "matrix":
            continue
        matrix = _matrix_of(suite.task)
        narrowed = dict(matrix)
        changed = False
        cells = matrix[suite.case_axis]
        kept_cells = [c for c in cells
                      if not (isinstance(c, dict) and sel.test_key in c)
                      or res.kept.get((name, str(c[sel.test_key])))]
        if len(kept_cells) != len(cells):
            narrowed[suite.case_axis] = kept_cells
            changed = True
        kept_v, vchanged = narrow_views(name, matrix, suite.view_axis,
                                        suite.views)
        if vchanged:
            narrowed[suite.view_axis] = kept_v
            changed = True
        if not any(isinstance(c, dict) and sel.test_key in c
                   for c in kept_cells) or kept_v == []:
            res.dropped.add(name)
            for key in suite.tests:
                res.kept[key] = False
        elif changed:
            res.narrowed[name] = narrowed

    for name, (vaxis, views) in tree.matrix_tests.items():
        key = (name, None)
        if not res.kept.get(key):
            res.dropped.add(name)
            continue
        matrix = _matrix_of(tree.tests[key].task)
        kept_v, vchanged = narrow_views(name, matrix, vaxis, views)
        if kept_v == []:
            res.dropped.add(name)
            res.kept[key] = False
        elif vchanged:
            narrowed = dict(matrix)
            narrowed[vaxis] = kept_v
            res.narrowed[name] = narrowed

    for key, t in tree.tests.items():
        if t.view is not None and not res.kept[key]:
            res.dropped.add(key[0])

    # A collector suite with no kept test anywhere beneath it is dropped.
    memo : Dict[str, bool] = {}

    def has_kept(task_name) -> bool:
        if task_name in memo:
            return memo[task_name]
        memo[task_name] = False      # cycle guard; cycles were rejected earlier
        kind = tree.kinds.get(task_name)
        if kind == "collector":
            val = any(has_kept(m.name) for m in tree.suites[task_name].members)
        elif kind == "matrix":
            val = task_name not in res.dropped
        elif kind == "test":
            val = any(res.kept.get(k) for k in tree.tests
                      if k[0] == task_name)
        else:
            val = False
        memo[task_name] = val
        return val

    for name, suite in tree.suites.items():
        if suite.kind == "collector" and not has_kept(name):
            res.dropped.add(name)

    if sel.active and not any(res.kept.values()):
        raise SelectionError(
            "the selection matched no tests, so the run would report success "
            "without testing anything")

    return res


# ---------------------------------------------------------------------------
# Runs in the built graph
# ---------------------------------------------------------------------------

RunKey = Tuple[Tuple[str, Optional[str]], Optional[str]]   # (test key, view)


def run_nodes(tree : Tree, res : Resolution, root_node,
              test_key : str = "name") -> Dict[RunKey, List[Any]]:
    """The built node(s) of each selected run -- a test on one view.

    A matrix cell is found by its axis values (`node.matrix_bindings`), not by
    parsing the name the naming scheme gave it, so this survives a change of
    naming scheme. A run that is not in the graph has no entry.
    """
    by_name : Dict[str, Any] = {}
    cells_of : Dict[str, List[Any]] = {}
    seen = set()
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        by_name.setdefault(node.name, node)
        for sub in getattr(node, "tasks", None) or []:
            if getattr(sub, "matrix_bindings", None) is not None:
                cells_of.setdefault(node.name, []).append(sub)
            stack.append(sub)
        for entry in getattr(node, "needs", ()) or ():
            stack.append(entry[0] if isinstance(entry, tuple) else entry)

    def view_of(bindings, axis):
        if axis is None or axis not in bindings:
            return None
        return str(bindings[axis])

    out : Dict[RunKey, List[Any]] = {}
    for key, t in tree.tests.items():
        if not res.kept.get(key):
            continue
        name = key[0]
        if name in tree.matrix_tests:
            vaxis = tree.matrix_tests[name][0]
            for cell in cells_of.get(name, []):
                out.setdefault(
                    (key, view_of(cell.matrix_bindings, vaxis)), []).append(cell)
        elif key[1] is not None:
            suite = tree.suites[name]
            for cell in cells_of.get(name, []):
                case = cell.matrix_bindings.get(suite.case_axis)
                if isinstance(case, dict) and str(case.get(test_key)) == key[1]:
                    out.setdefault(
                        (key, view_of(cell.matrix_bindings, suite.view_axis)),
                        []).append(cell)
        elif name in by_name:
            out[(key, t.view or None)] = [by_name[name]]
    return out


def run_requires(tree : Tree, res : Resolution, root_node, want,
                 test_key : str = "name",
                 resolve_type=None) -> Dict[RunKey, List[Any]]:
    """The producers of `want` each selected run depends on -- the build
    fan-in of the selection. See `checks.producers` for the walk."""
    from .checks import producers
    out : Dict[RunKey, List[Any]] = {}
    for run, nodes in run_nodes(tree, res, root_node, test_key).items():
        found = []
        for hits in producers(nodes, want, resolve_type).values():
            for p in hits:
                if p not in found:
                    found.append(p)
        out[run] = found
    return out


# ---------------------------------------------------------------------------
# The elaborator
# ---------------------------------------------------------------------------

def tree_for(ctxt, task, params) -> Tree:
    """The suite tree under `task`, read through the elaboration context."""
    return build_tree(
        task, ctxt.declaredNeeds,
        test_key=getattr(params, "test_key", None) or "name",
        view_axis=getattr(params, "view_axis", None) or "view",
        expand=getattr(ctxt, "expand", None))


def TestSelect(ctxt, task, name):
    """`elaborate:` entry point for `std.TestRunner`.

    Builds the standard interior with the deselected needs withheld, then wires
    back the selected ones -- rebuilding a suite as a narrowed variant wherever
    the selection reaches inside it.

    Nested collector suites are pruned here too, bottom-up, rather than by an
    elaborator of their own: the builder does not re-enter an elaborator bound
    to a type already being elaborated, so a `std.TestSuite` nested in another
    would be built unpruned. A collector variant is registered in the node memo
    under its original name, so its parent's ordinary needs-gathering picks it
    up. Matrix variants are wired explicitly, because a strategy node is not
    registered in the memo and substituting one "by name" would silently
    rebuild the original.
    """
    params = ctxt.mkParams(task)
    sel = Selection.from_params(params)
    tree = tree_for(ctxt, task, params)
    res = resolve(tree, sel)
    for w in res.warnings:
        _log.warning(w)

    matrix_nodes : Dict[str, Any] = {}

    def matrix_node(need):
        if need.name not in matrix_nodes:
            variant = dc.replace(
                need, strategy=Strategy(matrix=res.narrowed[need.name]),
                paramT=None)
            matrix_nodes[need.name] = ctxt.mkTaskNode(variant, name=need.name)
        return matrix_nodes[need.name]

    def withheld_of(needs):
        return {n.name for n in needs
                if n.name in res.dropped or n.name in res.narrowed}

    def needs_rebuild(suite) -> bool:
        return bool(withheld_of(suite.members))

    built = set()

    def build_collector(sname):
        """Post-order: a suite's changed members are built before it is."""
        if sname in built or sname in res.dropped:
            return
        built.add(sname)
        suite = tree.suites[sname]
        for m in suite.members:
            if tree.kinds.get(m.name) == "collector":
                build_collector(m.name)
        if not needs_rebuild(suite):
            return
        withheld = withheld_of(suite.members)
        variant = dc.replace(
            suite.task, needs=[m for m in suite.members if m.name not in withheld])
        node = ctxt.mkTaskNode(variant, name=suite.task.name)
        for m in suite.members:
            if m.name in res.narrowed and m.name not in res.dropped:
                ctxt.wireNeed(node, matrix_node(m))

    for sname, suite in tree.suites.items():
        if suite.kind == "collector":
            build_collector(sname)

    declared = ctxt.declaredNeeds(task)
    withheld = withheld_of(declared)

    build_only = str(getattr(params, "build_only", "") or "").strip()
    if build_only:
        kept = [matrix_node(n) if n.name in res.narrowed else ctxt.resolveNeed(n.name)
                for n in declared if n.name not in withheld
                or (n.name in res.narrowed and n.name not in res.dropped)]
        return build_only_node(ctxt, task, name, tree, res, sel, kept,
                               build_only)

    node = ctxt.buildDefault(
        task, name,
        select_needs=lambda needs: [n for n in needs if n.name not in withheld])

    for need in declared:
        if need.name in res.narrowed and need.name not in res.dropped:
            ctxt.wireNeed(node, matrix_node(need))

    if sel.active:
        _log.debug("test selection: tests=%s views=%s exclude=%s dropped=%s",
                   sel.tests, sel.views, sel.exclude, sorted(res.dropped))

    return node


def parse_requires(text : str):
    """A `--requires`/`--build-only` pattern, or SelectionError."""
    from ..type_match import parse_pattern
    try:
        want = parse_pattern(text)
    except ValueError as e:
        raise SelectionError(str(e))
    if not want:
        raise SelectionError("an empty produce pattern matches every producer")
    return want


def warn_unproduced(run_ids : List[str], total : int, text : str) -> None:
    """Warn about runs with no producer of `text`. When none of them has
    one, the pattern is the likelier mistake, so say that once."""
    if not run_ids:
        return
    if len(run_ids) == total:
        _log.warning("no selected test depends on a producer of %s. Check the "
                     "pattern, and that the producer declares it in "
                     "`produces:`", text)
        return
    for rid in run_ids:
        _log.warning("%s depends on no producer of %s -- if it should, its "
                     "producer does not declare it in `produces:`", rid, text)


def build_only_node(ctxt, task, name, tree, res, sel, kept, text):
    """`--build-only <pattern>`: build what the selected runs need, run none
    of them.

    The runs are built exactly as a normal run builds them -- same selection,
    same nodes, same rundirs -- and then left unwired: the node returned in the
    runner's place is a no-op collector over their producers. That is what
    makes this the first half of a split regression: the per-run commands that
    follow, given `--base-rundir` pointing here, find each producer where they
    would have built it themselves.
    """
    import types
    from .checks import _type_resolver
    want = parse_requires(text)
    holder = types.SimpleNamespace(
        name=name, needs=[(n, False) for n in kept], tasks=[])
    required = run_requires(tree, res, holder, want, sel.test_key,
                            _type_resolver(ctxt))
    producers = []
    warn_unproduced(
        [format_path(tree.tests[run[0]].path)
         + ("[view=%s]" % run[1] if run[1] else "")
         for run, nodes in required.items() if not nodes],
        len(required), text)
    for run, nodes in required.items():
        for p in nodes:
            if p not in producers:
                producers.append(p)
    node = ctxt.mkTaskNode(dc.replace(ctxt.getTask("std.Null"), needs=[]),
                           name=name)
    for p in producers:
        ctxt.wireNeed(node, p)
    _log.debug("build-only %s: %s", text, [p.name for p in producers])
    return node
