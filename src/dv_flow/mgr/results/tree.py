#****************************************************************************
#* tree.py -- the out/<run-id>/results/ link tree
#*
#* Copyright 2023-2026 Matthew Ballance and Contributors
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
"""``out/<run-id>/results/``: the run record as a directory tree, for ``ls``,
``less`` and any editor.

* One directory per node, named by the node's ``name`` (``/`` becomes ``_``,
  no leading ``.``; a repeated sibling name gets ``~2``, ``~3`` ...).
* ``STATUS`` in each: ``<status>: <msg>``, then the failing checks.
* Each entry of the node's run directory is linked under its own name, so
  ``two-ch/`` holds ``sim.log``, ``waves.fst`` ... and a suite's directory
  its ``<task>.exec_data.json`` directly. A child's directory takes
  precedence over a run-directory entry of the same name (a compound's
  subtask directory is that child's own run directory). A node whose run
  directory does not exist when the tree is built links ``rundir`` to it
  instead.
* Links to the node's artifacts, by role: ``log`` (more logs are
  ``log-<file>``), the waveform under its own name (``waves.fst``),
  ``cov/<file>``, ``report-<label>``, ``<role>-<file>`` otherwise. An
  artifact that is already linked under its own name from the run
  directory gets no second link, except ``log``, which every case has.
* ``FAILED/`` links to every failure the summary lists; a run with none
  has no ``FAILED/``.

Links into task rundirs are absolute; links inside the tree are relative,
so a copied ``out/<run-id>`` keeps its structure. Where symlinks are not
supported, each directory gets a ``LINKS.txt`` listing the paths instead.
"""
import logging
import os
import re
import shutil
from typing import Dict, List, Optional

from .model import ResultNode, ResultsFile

_log = logging.getLogger("results.tree")

TREE_DIR = "results"
FAILED_DIR = "FAILED"
_UNSAFE = re.compile(r"[\x00-\x1f/\\]")


def safe_name(name: str) -> str:
    n = _UNSAFE.sub("_", name or "") or "_"
    n = n.lstrip(".") or "_"
    if n in (FAILED_DIR, "STATUS", "LINKS.txt", "rundir", "log"):
        n = "_" + n
    return n


class _Unique(object):
    def __init__(self):
        self.seen = {}

    def __call__(self, name):
        if name not in self.seen:
            self.seen[name] = 1
            return name
        self.seen[name] += 1
        return "%s~%d" % (name, self.seen[name])


def status_text(node: ResultNode) -> str:
    from .render_text import fmt_check
    own = getattr(node, "own_status", None) or node.status
    lines = ["%s: %s" % (own, node.msg) if node.msg else own]
    for c in node.checks:
        if c.status in ("fail", "error"):
            lines.append(fmt_check(c))
    return "\n".join(lines) + "\n"


_RESERVED = ("STATUS", "LINKS.txt")


def _rundir_entries(node: ResultNode, taken) -> Optional[List[str]]:
    """The run-directory entries a node links under their own names, or
    None when the node gets a ``rundir`` link instead."""
    rd = node.rundir
    if not rd or not os.path.isdir(rd):
        return None
    try:
        names = sorted(os.listdir(rd))
    except OSError:
        return None
    return [n for n in names
            if not n.startswith(".") and n not in _RESERVED and n not in taken]


def _artifact_links(node: ResultNode, log_copies: Dict[str, str],
                    names=None, covered=()):
    """[(link name, absolute target)] for a node's artifacts. ``covered``
    holds targets already linked under their own name; only ``log`` links
    one of those again."""
    out = []
    names = names or _Unique()
    nlog = 0
    for a in node.artifacts:
        for f in a.files:
            path = f if os.path.isabs(f) else os.path.join(a.basedir, f)
            base = os.path.basename(path.rstrip(os.sep)) or "file"
            role = a.role or "other"
            if role == "log":
                path = log_copies.get(path, path)
                name = "log" if nlog == 0 else "log-%s" % base
                nlog += 1
            elif role == "waves":
                name = base
            elif role == "cov":
                name = os.path.join("cov", base)
            elif role == "report":
                name = "report-%s" % safe_name((a.label or base).replace(" ", "_"))
            else:
                name = "%s-%s" % (role, base)
            if role != "log" and os.path.normpath(path) in covered:
                continue
            out.append((names(name), path))
    return out


class TreeBuilder(object):

    def __init__(self, out_dir: str, log_copies: Optional[Dict[str, str]] = None):
        self.out_dir = out_dir
        self.root = os.path.join(out_dir, TREE_DIR)
        self.log_copies = log_copies or {}
        self.symlinks = True
        self.warned = False
        self.paths = {}            # result path (by name) -> tree dir

    def _link(self, target: str, link: str, listing: List[str]):
        if self.symlinks:
            try:
                os.makedirs(os.path.dirname(link), exist_ok=True)
                os.symlink(target, link)
                return
            except (OSError, NotImplementedError) as e:
                self.symlinks = False
                if not self.warned:
                    _log.warning("symlinks are not supported here (%s); writing LINKS.txt "
                                 "files in %s instead" % (e, self.root))
                    self.warned = True
        listing.append("%s -> %s" % (os.path.relpath(link, self._cur), target))

    def _node(self, node: ResultNode, d: str, rpath: str):
        os.makedirs(d, exist_ok=True)
        self._cur = d
        self.paths[rpath] = (d, node.name)
        with open(os.path.join(d, "STATUS"), "w") as fp:
            fp.write(status_text(node))
        listing = []
        uniq = _Unique()
        kids = [(uniq(safe_name(c.name)), c) for c in node.children]
        names = _Unique()
        for n in _RESERVED:
            names(n)
        for cn, _c in kids:
            names(cn)
        # Without symlinks, one `rundir` line beats a LINKS.txt line per file.
        entries = _rundir_entries(node, set(names.seen)) if self.symlinks else None
        covered = set()
        for e in entries or []:
            target = os.path.join(node.rundir, e)
            self._link(target, os.path.join(d, names(e)), listing)
            covered.add(os.path.normpath(target))
        for name, target in _artifact_links(node, self.log_copies, names, covered):
            self._link(target, os.path.join(d, name), listing)
        if node.rundir and entries is None:
            self._link(node.rundir, os.path.join(d, names("rundir")), listing)
        if listing:
            with open(os.path.join(d, "LINKS.txt"), "w") as fp:
                fp.write("\n".join(listing) + "\n")
            listing = []
        for cn, c in kids:
            self._node(c, os.path.join(d, cn), rpath + "/" + (c.name or "?"))

    def build(self, rf: ResultsFile) -> str:
        # Rebuilt from scratch (a reused --run-id records again)
        if os.path.isdir(self.root) and not os.path.islink(self.root):
            shutil.rmtree(self.root)
        elif os.path.lexists(self.root):
            os.remove(self.root)
        os.makedirs(self.root)
        root = rf.result
        self._node(root, os.path.join(self.root, safe_name(root.name or "run")),
                   root.name or "<root>")

        # No failures, no FAILED/: its absence is the "all passed" signal.
        hits = [self.paths[f.path] for f in rf.summary.failures if f.path in self.paths]
        if not hits:
            return self.root
        failed = os.path.join(self.root, FAILED_DIR)
        os.makedirs(failed, exist_ok=True)
        self._cur = failed
        uniq = _Unique()
        listing = []
        for d, nname in hits:
            name = uniq(safe_name(nname))
            self._link(os.path.relpath(d, failed), os.path.join(failed, name), listing)
        if listing:
            with open(os.path.join(failed, "LINKS.txt"), "w") as fp:
                fp.write("\n".join(listing) + "\n")
        return self.root


def build_tree(rf: ResultsFile, out_dir: str, log_copies: Optional[Dict[str, str]] = None) -> str:
    """Build ``<out_dir>/results/``; returns its path."""
    return TreeBuilder(out_dir, log_copies).build(rf)
