#****************************************************************************
#* checks.py
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
"""Built-in graph-build checks -- the implementations behind `std.check.*`.

A check reports and returns; it never builds. It runs inside graph build, which
is memoized, so it must also be pure and order-independent: a node built once
and needed twice is checked once, and which consumer triggered that is not
something a check may depend on.
"""

import logging

from ..type_match import normalize, pattern_matches

_log = logging.getLogger("std.checks")


#: The `check:` reference identifying the Implemented check. Matching on this
#: rather than on the type name means a project that derives its own check type
#: from `std.check.Implemented` is still recognized.
IMPLEMENTED_CHECK = "dv_flow.mgr.std.checks:implemented"


def _has_implementation(task, needs) -> bool:
    """Whether `task` does anything: a `run:`, a body, a need, or a `select:`
    family. Split out so that the check and the static `unimplemented_slot`
    query below cannot answer the same question differently -- one of them runs
    at graph build and the other in a listing, and a listing that disagreed
    with the run would be worse than no listing."""
    return bool(
        getattr(task, 'run', None)
        or getattr(task, 'subtasks', None)
        or needs
        or getattr(getattr(task, 'strategy', None), 'select', None) is not None)


def implemented(ctxt) -> None:
    """The task must do something.

    A slot a base project declared and a leaf never filled otherwise *runs and
    reports success* -- the worst outcome for a uniform project interface,
    because it makes `dfm run <verb>` mean nothing in some projects while
    meaning something everywhere else.
    """
    if _has_implementation(ctxt.task, ctxt.needs):
        return

    ctxt.error(
        "required project slot is not implemented",
        detail="'%s' has no `run:`, no body, and no `needs:`." % _leaf(ctxt.task))


def unimplemented_slot(task, pkg=None) -> bool:
    """Whether `task`, **as loaded**, is a declared-but-unfilled project slot:
    it is required to be implemented, and nothing implements it.

    This is the same question `implemented` answers, asked early enough to be
    useful in a LISTING. A project interface exists to be filled in, so "which
    of these verbs does this project actually answer to" is what a reader
    arriving at `dfm run` wants to know -- and finding out by running the task
    and reading the failure is a poor way to learn it.

    Necessarily a STATIC approximation: the authoritative check runs at graph
    build, after elaboration, where it sees needs this cannot. So it is
    deliberately conservative -- it answers True only for a task that declares
    the requirement, satisfies none of the ways of being implemented, and is
    not the target of a package `overrides:` substitution (which supplies an
    implementation the loaded task does not show). Anything it is unsure of it
    calls implemented, because a false alarm in a listing is worse than a
    missing one: the run still reports the truth.
    """
    from ..task import collect_task_requires

    reqs = [r for r in collect_task_requires(task)
            if getattr(r, 'check', None) == IMPLEMENTED_CHECK
            and (getattr(getattr(r, 'paramT', None), 'severity', 'error')
                 or 'error') != 'off']
    if not reqs:
        return False

    needs = [n for n in (getattr(task, 'needs', ()) or ()) if n is not None]
    if _has_implementation(task, needs):
        return False

    # A substitution replaces the task wholesale at graph build; the loaded
    # task is not what will run.
    if pkg is not None:
        subs = getattr(pkg, 'substitution_m', None) or {}
        name = getattr(task, 'name', '')
        if name in subs or _leaf(task) in subs:
            return False

    return True


def needs(ctxt) -> None:
    """Constrain what the task depends on.

    `produces:` matches a pattern against what tasks DECLARE, transitively
    through needs. It is a coarse static gate, on purpose: cheap, early, and a
    statement of what kind of input the task expects. Whether the data actually
    carries what the consumer will look for is a runtime question, and belongs
    to the consumer -- see the type's documentation.
    """
    p = ctxt.params
    count = len(ctxt.needs)

    min_n = _int(getattr(p, 'min', 1), 1)
    max_n = _int(getattr(p, 'max', -1), -1)

    if min_n > 0 and count < min_n:
        ctxt.error(
            "not enough inputs" if min_n > 1 else "required input is not provided",
            detail="'%s' needs at least %d input%s; it has %d." % (
                _leaf(ctxt.task), min_n, "" if min_n == 1 else "s", count))
        return
    if max_n >= 0 and count > max_n:
        ctxt.error(
            "too many inputs",
            detail="'%s' accepts at most %d input%s; it has %d." % (
                _leaf(ctxt.task), max_n, "" if max_n == 1 else "s", count))
        return

    named = getattr(p, 'named', None) or []
    if named:
        have = [n.name for n in ctxt.needs]
        missing = [w for w in named
                   if not any(h == w or h.endswith("." + w) for h in have)]
        if missing:
            ctxt.error(
                "required input is not provided",
                detail="'%s' must depend on %s. Present: %s." % (
                    _leaf(ctxt.task),
                    ", ".join("'%s'" % m for m in missing),
                    ", ".join(have) if have else "(nothing)"))
            return

    want = normalize(getattr(p, 'produces', None))
    if want:
        resolve = _type_resolver(ctxt)
        reachable, offered = _reachable_produces(ctxt.needs)
        if not any(pattern_matches(want, have, resolve) for have in reachable):
            ctxt.error(
                "required input is not provided",
                detail="'%s' requires an input producing %s.\n"
                       "   provided   %s" % (
                           _leaf(ctxt.task), _fmt(want),
                           _describe(ctxt.needs, offered)))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _leaf(task):
    name = getattr(task, 'name', '') or ''
    return name.rsplit('.', 1)[-1] if '.' in name else name


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _type_resolver(ctxt):
    """The loader's type lookup, for is-a matching on `type`. None when it is
    not reachable -- matching then degrades to string equality rather than
    guessing."""
    builder = getattr(ctxt, 'builder', None)
    loader = getattr(builder, 'loader', None) if builder is not None else None
    return getattr(loader, 'findType', None) if loader is not None else None


def _node_produces(node):
    """The produce patterns a single node declares, as maps."""
    out = []
    produces = getattr(node, 'produces', None)
    if not produces:
        return out
    for entry in produces:
        if isinstance(entry, dict):
            out.append(dict(entry))
        elif isinstance(entry, str):
            out.append({"type": entry})
    return out


def _passes_through(node):
    """Whether items reaching `node` continue on to its consumers.

    Forwarding is a function of BOTH `passthrough` and `consumes` -- mirroring
    what the engine actually does (`task_node_leaf.py`). In particular the
    default combination (`passthrough: unused` with an undeclared `consumes`,
    which defaults to *all*) forwards **nothing**: an undeclared task is a
    sink, not a window. Reading `passthrough` alone made the walk transparent
    through sinks, so a requirement could be satisfied by an item its consumer
    never receives.
    """
    # A COMPOUND is not governed by the leaf passthrough rules: its output is
    # assembled from its needs -- which, for a compound, are its terminal
    # interior tasks (`task_node_compound.py`). So it always forwards, and the
    # thing a consumer actually receives from `sim-img.tlm.opt` is what the
    # SimImage inside it produced.
    from ..task_node_compound import TaskNodeCompound
    if isinstance(node, TaskNodeCompound):
        return True

    pt = getattr(node, 'passthrough', None)
    pt_v = str(getattr(pt, 'value', pt)).lower() if pt is not None else "unused"
    if pt_v in ("none", "false"):
        return False
    if pt_v == "all":
        return True

    # `unused`: forwards what it does not consume.
    consumes = getattr(node, 'consumes', None)
    if isinstance(consumes, list):
        # Reads matching items, forwards the rest.
        return True
    c_v = str(getattr(consumes, 'value', consumes)).lower()
    if c_v in ("none", "false"):
        return True
    # `consumes: all` -- reads everything, so nothing is left to forward.
    return False


def _reachable_produces(nodes):
    """(produce patterns reachable from `nodes`, {node name: [patterns]}).

    A node's effective outputs are what it DECLARES plus what it PASSES
    THROUGH. Declaring only what a task adds is what keeps the declarations
    maintainable (a passthrough task would otherwise have to restate the union
    of everything upstream, and be wrong the moment upstream changed), and
    walking passthrough here is what makes those partial declarations add up to
    the truth at the consumer.

    It also means the walk stops at a task that consumes its inputs rather than
    forwarding them -- which is correct, and stricter than following every edge.
    """
    reachable = []
    direct = {}
    seen = set()

    def walk(node):
        if id(node) in seen:
            return
        seen.add(id(node))
        # What the node itself declares is always visible to its consumer.
        for t in _node_produces(node):
            reachable.append(t)
        # What its UPSTREAM declared is visible only if this node forwards it.
        # The passthrough test belongs to the node being walked, including a
        # direct need -- that node is exactly the one deciding whether its
        # inputs continue on.
        if not _passes_through(node):
            return
        for entry in getattr(node, 'needs', ()) or ():
            nxt = entry[0] if isinstance(entry, tuple) else entry
            if nxt is not None:
                walk(nxt)
        # A compound's `input` is internal plumbing, not a passthrough
        # decision, so it is always followed.
        inp = getattr(node, 'input', None)
        if inp is not None and inp is not node:
            walk(inp)

    for node in nodes:
        direct[node.name] = _node_produces(node)
        walk(node)
    return reachable, direct


def _fmt(pattern):
    """'{type: hdlsim.SimImg, profile: true}' -- readable in a diagnostic."""
    return "{%s}" % ", ".join(
        "%s: %s" % (k, _fmt_value(v)) for k, v in pattern.items())


def _fmt_value(v):
    return "true" if v is True else ("false" if v is False else str(v))


def _describe(nodes, offered):
    """What each input actually offers, so the reader can see the mismatch
    rather than be told there is one."""
    if not nodes:
        return "(no inputs)"
    parts = []
    for node in nodes:
        pats = offered.get(node.name) or []
        parts.append("%s%s" % (
            node.name,
            (" -> " + ", ".join(_fmt(p) for p in pats)) if pats else ""))
    return "\n              ".join(parts)
