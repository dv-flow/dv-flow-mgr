"""`dfm show` as the contract for documentation metadata.

The point of these tests is that a documentation generator and the CLI answer
the same question the same way. Anything a doc tool has to reconstruct for
itself is a second model of the flow that will drift from this one.
"""
import textwrap

import pytest

from dv_flow.mgr.cmds.show.cmd_show_task import CmdShowTask
from dv_flow.mgr.cmds.show.cmd_show_package import CmdShowPackage
from dv_flow.mgr.util import loadProjPkgDef


FLOW = textwrap.dedent('''\
package:
  name: p
  desc: One line about p
  doc: |
    The longer story about p.
  imports:
  - std
  tasks:
  - name: base
    desc: "Base description"
    doc: "Base documentation"
  - name: derived
    uses: base
    scope: root
    examples:
    - title: Run it
      caption: The usual invocation.
      lang: shell
      code: dfm run derived
  - name: old
    scope: root
    tags:
    - std.Deprecated:
        reason: superseded
        replacement: p.derived
  - name: plain
    scope: root
''')


class TaskArgs:
    def __init__(self, name, root, **kw):
        self.name = name
        self.root = root
        self.param_overrides = []
        self.config = None
        self.needs = None
        self.json = False
        self.verbose = False
        self.usage = False
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def proj(tmp_path, monkeypatch):
    (tmp_path / 'flow.yaml').write_text(FLOW)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _info(proj, name):
    loader, pkg = loadProjPkgDef(str(proj))
    return CmdShowTask()._task_to_info(pkg.task_m[name], 'p')


# ------------------------------------------------------------------ examples

def test_examples_reach_the_cli(proj):
    examples = _info(proj, 'p.derived')['examples']
    assert examples == [{
        'title': 'Run it',
        'code': 'dfm run derived',
        'caption': 'The usual invocation.',
        'lang': 'shell',
    }]


def test_examples_absent_is_empty_list(proj):
    assert _info(proj, 'p.plain')['examples'] == []


# ------------------------------------------------------------- desc inherited

def test_desc_comes_from_the_resolved_task(proj):
    """The view reports what the resolved Task says, not what the YAML said.

    These agree for a directly-declared task, but the Task is the object every
    other consumer reads, and it is the one that exists for tasks with no
    taskdef at all. Reading the authored YAML instead is how those come back
    blank.
    """
    info = _info(proj, 'p.base')
    assert info['desc'] == "Base description"
    assert info['doc'] == "Base documentation"


def test_desc_is_inherited_through_uses(proj):
    """`derived` adds an example and nothing else, so it is still its base.

    Reporting it blank would drop prose that was already written, in the two
    places a reader actually looks: the listing and the generated docs.
    """
    info = _info(proj, 'p.derived')
    assert info['desc'] == "Base description"
    assert info['doc'] == "Base documentation"


# ----------------------------------------------------------------------- tags

def test_tags_are_serializable(proj):
    """A resolved tag is a Type; str() on one is a Python repr.

    Emitting that under a 'tags' key gives a JSON consumer a blob it can only
    regex at -- so the lifecycle tags are unreadable exactly where they matter.
    """
    tags = _info(proj, 'p.old')['tags']
    assert len(tags) == 1
    assert tags[0]['name'] == 'std.Deprecated'
    assert tags[0]['params']['reason'] == 'superseded'
    assert tags[0]['params']['replacement'] == 'p.derived'

    import json
    json.dumps(tags)  # must not raise


def test_no_tags_is_empty_list(proj):
    assert _info(proj, 'p.plain')['tags'] == []


# -------------------------------------------------------------- package prose

def test_package_desc_and_doc_reach_the_cli(proj):
    loader, pkg = loadProjPkgDef(str(proj))
    info = CmdShowPackage()._pkg_to_info(pkg, is_project=True)
    assert info['desc'] == "One line about p"
    assert info['doc'].startswith("The longer story about p.")
