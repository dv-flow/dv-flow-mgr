#****************************************************************************
#* expr_refs.py
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
#****************************************************************************
"""Static reference extraction for ``${{ }}`` expressions.

Answers "what names does this expression depend on?" without any values, so
a flow description can be checked for dangling references separately from
being evaluated. See run_body_expansion_plan.md §1: validation needs name
resolution, evaluation needs values, and entangling them is what makes
eager expansion wrong.
"""
import dataclasses as dc
import re
from typing import Any, List, Optional, Set

from .expr_parser import (
    Expr, ExprBin, ExprBinOp, ExprBool, ExprCall, ExprHId, ExprId, ExprIndex,
    ExprInt, ExprIterator, ExprString, ExprUnary, ExprVar, parse_expr)


# ``${{ ... }}``, non-greedy. Same pattern the runtime expander and
# TaskGraphBuilder._check_runtime_ref use.
EXPR_RE = re.compile(r'\$\{\{\s*(.*?)\s*\}\}')

# Builtins that evaluate their argument once per element, with the element
# bound as `input`/`item`. A reference to either inside such an argument is
# bound, not dangling.
_ITEM_BUILTINS = ("map", "select")
_ITEM_NAMES = ("input", "item")


@dc.dataclass(frozen=True)
class Ref:
    """One name referenced by an expression.

    ``root`` is what must be bound -- the leading identifier of a
    hierarchical reference (``env`` in ``env.CC``), since only the root is
    resolvable without values. ``path`` keeps the whole thing for messages.
    """
    root: str
    path: str
    # ``${{ CC:-gcc }}`` supplies its own fallback, so an unbound root is
    # not an error.
    has_default: bool = False


class _RefCollector(object):
    """Walks an AST collecting variable references.

    Deliberately *not* an ExprVisitor subclass: the base class's generic
    traversal would descend into positions that are not variable references
    at all -- a pipe's right-hand side names a filter, and ExprCall.id names
    a method. Treating those as variables produced false 'undefined
    reference' reports, which is worse than reporting nothing.
    """

    def __init__(self):
        self.refs: List[Ref] = []
        self._bound: List[Set[str]] = []

    def _is_bound(self, name):
        return any(name in s for s in self._bound)

    def _add(self, path: str):
        has_default = False
        if ':-' in path:
            path, has_default = path.split(':-', 1)[0], True
        root = path.split('.')[0]
        if not root or self._is_bound(root):
            return
        self.refs.append(Ref(root=root, path=path, has_default=has_default))

    def visit(self, e: Optional[Expr]):
        if e is None:
            return
        if isinstance(e, ExprId):
            self._add(e.id)
        elif isinstance(e, ExprHId):
            self._add(".".join(e.id))
        elif isinstance(e, ExprVar):
            # `$name` reads the raw variables dict, which carries loader- and
            # builder-injected bindings we cannot enumerate statically. Not
            # reported, rather than reported wrongly.
            pass
        elif isinstance(e, ExprBin):
            self.visit(e.lhs)
            if e.op == ExprBinOp.Pipe:
                self._visit_filter(e.rhs)
            else:
                self.visit(e.rhs)
        elif isinstance(e, ExprUnary):
            self.visit(e.expr)
        elif isinstance(e, ExprCall):
            self._visit_call(e)
        elif isinstance(e, ExprIndex):
            self.visit(e.obj)
            self.visit(e.index)
            self.visit(e.start)
            self.visit(e.end)
        elif isinstance(e, ExprIterator):
            self.visit(e.obj)
        elif isinstance(e, (ExprString, ExprInt, ExprBool)):
            pass

    def _visit_filter(self, e: Expr):
        """Right-hand side of a pipe: a filter or builtin name, whose
        arguments (if any) are ordinary expressions."""
        if isinstance(e, (ExprId, ExprHId)):
            return
        if isinstance(e, ExprCall):
            self._visit_call(e)
            return
        self.visit(e)

    def _visit_call(self, e: ExprCall):
        # e.id is a method/filter name, not a variable -- skip it.
        item_scope = e.id in _ITEM_BUILTINS
        if item_scope:
            self._bound.append(set(_ITEM_NAMES))
        try:
            for arg in e.args:
                self.visit(arg)
        finally:
            if item_scope:
                self._bound.pop()


def refs_of_expr(expr_text: str) -> List[Ref]:
    """References made by the body of a single ``${{ ... }}``."""
    try:
        ast = parse_expr(expr_text)
    except Exception:
        # A malformed expression is a different diagnostic, raised where the
        # expression is actually evaluated. This pass must not convert it
        # into a bogus undefined-reference report.
        return []
    if ast is None:
        return []
    c = _RefCollector()
    c.visit(ast)
    return c.refs


def refs_of_text(text: Any) -> List[Ref]:
    """References made by every ``${{ ... }}`` in a string.

    Non-strings (and strings with no reference) yield an empty list, so
    callers can hand this any authored value without pre-checking.
    """
    if not isinstance(text, str) or "${{" not in text:
        return []
    refs = []
    for m in EXPR_RE.finditer(text):
        refs.extend(refs_of_expr(m.group(1)))
    return refs


def has_refs(text: Any) -> bool:
    return isinstance(text, str) and "${{" in text
