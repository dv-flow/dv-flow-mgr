"""
Tests for run command task listing with visibility filtering.
"""
import os
import textwrap
from dv_flow.mgr.cmds.cmd_run import CmdRun


class Args:
    """Minimal args holder for CmdRun"""
    def __init__(self, root):
        self.tasks = []
        self.ui = 'log'
        self.clean = False
        self.j = -1
        self.param_overrides = []
        self.config = None
        self.root = root


def test_run_list_shows_only_root_tasks(tmp_path, capsys):
    """Test that dfm run with no task shows only root-scoped tasks"""
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: my_pkg
      tasks:
      - name: entry
        scope: root
        desc: "Entry point task"
        run: echo "entry"
      - name: helper
        desc: "Helper task (not root)"
        run: echo "helper"
      - name: build
        scope: [root, export]
        desc: "Build task"
        run: echo "build"
    '''))
    
    args = Args(root=str(tmp_path))
    CmdRun()(args)
    out = capsys.readouterr().out
    
    # Should show only root tasks
    assert 'my_pkg.entry' in out
    assert 'my_pkg.build' in out
    assert 'my_pkg.helper' not in out
    assert 'Available Tasks:' in out


def test_run_list_warns_when_no_root_tasks(tmp_path, capsys):
    """Test that dfm run warns and shows all tasks when no root tasks exist"""
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: my_pkg
      tasks:
      - name: task1
        desc: "Task 1"
        run: echo "task1"
      - name: task2
        desc: "Task 2"
        run: echo "task2"
    '''))
    
    args = Args(root=str(tmp_path))
    CmdRun()(args)
    out = capsys.readouterr().out
    
    # Should show warning
    assert "Warning: No 'root' tasks found in the current package" in out
    assert "Runnable tasks must be marked 'scope: root'" in out
    
    # Should still show all tasks
    assert 'my_pkg.task1' in out
    assert 'my_pkg.task2' in out
    assert 'Available Tasks:' in out


def test_run_list_shows_only_root_with_mixed_scopes(tmp_path, capsys):
    """Test filtering with various scope combinations"""
    (tmp_path / 'flow.yaml').write_text(textwrap.dedent('''\
    package:
      name: my_pkg
      tasks:
      - name: main
        scope: root
        desc: "Main entry"
        run: echo "main"
      - name: internal
        desc: "Internal task"
        run: echo "internal"
      - name: shared
        scope: export
        desc: "Shared task"
        run: echo "shared"
      - name: utility
        scope: local
        desc: "Local utility"
        run: echo "utility"
    '''))
    
    args = Args(root=str(tmp_path))
    CmdRun()(args)
    out = capsys.readouterr().out
    
    # Should show only root task
    assert 'my_pkg.main' in out
    assert 'my_pkg.internal' not in out
    assert 'my_pkg.shared' not in out
    assert 'my_pkg.utility' not in out
