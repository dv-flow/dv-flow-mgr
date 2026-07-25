#****************************************************************************
#* ref_validate.py
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
"""Check a flow description for dangling ``${{ }}`` references.

This is validation as its own pass, separate from evaluation
(run_body_expansion_plan.md §1 and Phase A). It answers "is every name this
task references bound somewhere?" using a *scope signature* -- the set of
names bound in each phase -- rather than a value environment. It reads no
values, mutates nothing, and holds no loader state, so it is callable both
during load and standalone from ``dfm validate``.

Deferred evaluation is what makes it necessary: before, a dangling
reference was caught as a side effect of eagerly substituting values, and a
value that is *not* substituted at load can no longer report its own typos.

**Leniency is deliberate.** A false positive here rejects a working flow at
load time, which is far worse than missing a typo. Where a name's binding
cannot be established statically -- ``$name`` variables, anything under
``this``/``matrix``, a package-qualified path -- the reference is accepted.
"""
import dataclasses as dc
import difflib
from typing import Any, Iterable, List, Optional, Set

from .expr_refs import Ref, refs_of_text
from .task import collect_task_params


# Bound before any task is elaborated: file and environment facts.
LOAD_NAMES = frozenset(("srcdir", "rootdir", "root", "env"))

# Not bound until the task executes. The loader seeds each of these to its
# own literal (``self._eval.set("rundir", "${{ rundir }}")``) precisely so
# the reference survives load intact -- the existing precedent for "this
# name is not bound yet; leave it alone."
RUN_NAMES = frozenset(("rundir", "inputs", "name", "result_file", "memento"))

# Roots whose members cannot be enumerated statically:
#   this    -- parent params and, inside a matrix, that cell's axis values
#   matrix  -- the current cell's axis values
#   input,
#   item    -- bound per-element inside map()/select() (also handled
#              structurally in expr_refs, this is the belt-and-braces case)
OPAQUE_NAMES = frozenset(("this", "matrix", "input", "item"))


@dc.dataclass
class ScopeSignature:
    """The names bound for one task, by origin. Names only -- no values."""
    params: Set[str] = dc.field(default_factory=set)
    package_vars: Set[str] = dc.field(default_factory=set)
    # Package names and aliases reachable from here. A reference rooted at
    # one of these is package-qualified (``hdlsim.sim``) and accepted
    # without checking the member.
    package_names: Set[str] = dc.field(default_factory=set)
    # Names bound by the enclosing construct: a compound body binds the
    # parent task's parameters as bare names.
    enclosing: Set[str] = dc.field(default_factory=set)

    def is_bound(self, root: str) -> bool:
        return (root in self.params
                or root in self.package_vars
                or root in self.package_names
                or root in self.enclosing
                or root in LOAD_NAMES
                or root in RUN_NAMES
                or root in OPAQUE_NAMES)

    def available(self) -> List[str]:
        """Names worth suggesting in a diagnostic -- the task's own scope,
        not the reserved vocabulary the author did not mean to type."""
        return sorted(self.params | self.package_vars | self.enclosing)


@dc.dataclass
class RefFinding:
    """One unresolvable reference."""
    task_name: str
    where: str          # "run", "param 'x'", "rundir", "uptodate"
    ref: Ref
    message: str
    srcinfo: Any = None


def _package_names(pkg) -> Set[str]:
    names = set()
    if pkg is None:
        return names
    if getattr(pkg, "name", None):
        names.add(pkg.name)
        # A dotted package name is referenced by its leading segment too.
        names.add(pkg.name.split('.')[0])
    for attr in ("pkg_m", "pkg_alias_m"):
        m = getattr(pkg, attr, None)
        if m:
            names.update(str(k).split('.')[0] for k in m.keys())
    return names


def _package_vars(pkg) -> Set[str]:
    if pkg is None:
        return set()
    paramT = getattr(pkg, "paramT", None)
    fields = getattr(paramT, "model_fields", None)
    return set(fields.keys()) if fields else set()


def signature_for_task(task, enclosing: Optional[Iterable[str]] = None) -> ScopeSignature:
    """Build the scope signature for ``task``.

    Parameters come from the whole ``uses`` chain (an inherited parameter is
    just as referenceable as a locally declared one); package variables and
    package names come from the task's package.
    """
    definitions, _ = collect_task_params(task)
    return ScopeSignature(
        params=set(definitions.keys()),
        package_vars=_package_vars(getattr(task, "package", None)),
        package_names=_package_names(getattr(task, "package", None)),
        enclosing=set(enclosing) if enclosing else set())


def _iter_strings(value, path=""):
    """Yield every string inside an authored parameter value, with a path
    describing where it sits (``opts[2]``, ``cfg.debug``)."""
    if isinstance(value, str):
        yield value, path
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            yield from _iter_strings(v, "%s[%d]" % (path, i))
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _iter_strings(v, "%s.%s" % (path, k))


def _check(text, where, task_name, sig, srcinfo, findings):
    for ref in refs_of_text(text):
        if ref.has_default or sig.is_bound(ref.root):
            continue
        available = sig.available()
        suggestion = ""
        close = difflib.get_close_matches(ref.root, available, n=1, cutoff=0.6)
        if close:
            suggestion = ". Did you mean '%s'?" % close[0]
        elif available:
            suggestion = ". Available: %s" % ", ".join(available)
        findings.append(RefFinding(
            task_name=task_name,
            where=where,
            ref=ref,
            srcinfo=srcinfo,
            message="task '%s' %s references undefined variable '%s'%s" % (
                task_name, where, ref.path, suggestion)))


def validate_task_refs(task,
                       run_text: Any = None,
                       enclosing: Optional[Iterable[str]] = None,
                       srcinfo: Any = None) -> List[RefFinding]:
    """Return every unresolvable ``${{ }}`` reference in ``task``.

    ``run_text`` overrides the body to check. The load-time call site needs
    this because it validates *before* the body is stored; every other
    caller can leave it None and get ``task.run``.
    """
    sig = signature_for_task(task, enclosing=enclosing)
    task_name = getattr(task, "name", "<unnamed>")
    findings: List[RefFinding] = []

    param_defs = getattr(task, "param_defs", None)
    if param_defs is not None:
        for pname, pdef in param_defs.definitions.items():
            for text, sub in _iter_strings(getattr(pdef, "value", None)):
                where = "parameter '%s%s'" % (pname, sub)
                _check(text, where, task_name, sig, srcinfo, findings)

    body = task.run if run_text is None else run_text
    _check(body, "run", task_name, sig, srcinfo, findings)
    _check(getattr(task, "rundir", None), "rundir", task_name, sig, srcinfo, findings)
    _check(getattr(task, "uptodate", None), "uptodate", task_name, sig, srcinfo, findings)

    return findings
