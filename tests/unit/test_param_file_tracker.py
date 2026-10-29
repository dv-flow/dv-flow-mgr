"""
Tracking of `-P` param-file entries in OverrideBindingTracker: each entry is
registered with its source, and entries that bind nowhere are reported.
"""
from dv_flow.mgr.param_override_tracker import OverrideBindingTracker
from dv_flow.mgr.util import load_param_file


def _tracker(spec, keys=()):
    t = OverrideBindingTracker(keys=list(keys))
    t.add_param_file(spec, load_param_file(spec))
    return t


def test_entries_registered_with_file_source(tmp_path):
    pf = tmp_path / "params.json"
    pf.write_text('{"package": {"seed": 1}, "tasks": {"build": {"top": "t"}}}')
    t = _tracker(str(pf))
    srcs = [(e.kind, e.key, e.source) for e in t.param_file_entries]
    assert srcs == [
        ('package', 'seed', "%s: package.seed" % pf),
        ('task', 'build.top', "%s: tasks.build.top" % pf),
    ]
    e = t.param_file_entries[1]
    assert (e.task, e.param) == ('build', 'top')


def test_inline_json_source():
    t = _tracker('{"tasks": {"build": {"top": "t"}}}')
    assert t.param_file_entries[0].source == "inline JSON: tasks.build.top"


def test_unbound_entries_are_unmatched_in_file_order():
    t = _tracker('{"package": {"seed": 1}, '
                 '"tasks": {"bld": {"top": "t"}, "build": {"top": "t", "x": 1}}}')
    t.note_task_bind("build.top", "pkg.build")
    assert [e.key for e in t.unmatched_param_file()] == [
        'seed', 'bld.top', 'build.x']


def test_all_bound_is_empty():
    t = _tracker('{"package": {"seed": 1}, "tasks": {"pkg.build": {"top": "t"}}}')
    t.note_package_bind("seed", "pkg")
    t.note_task_bind("pkg.build.top", "pkg.build")
    assert t.unmatched_param_file() == []


def test_package_bind_does_not_match_task_entry():
    # A dotted package key and a task entry can share a spelling; a bind in
    # one namespace must not satisfy an entry of the other.
    t = _tracker('{"tasks": {"build": {"top": "t"}}}')
    t.note_package_bind("build.top", "build")
    assert [e.key for e in t.unmatched_param_file()] == ['build.top']


def test_entry_shadowed_by_define_counts_as_matched():
    # -D build.top=... wins over the -P entry; the shared key binds once and
    # both are satisfied.
    t = _tracker('{"tasks": {"build": {"top": "t"}}}', keys=["build.top"])
    t.note_task_bind("build.top", "pkg.build")
    assert t.unmatched_param_file() == []
    assert t.unmatched() == []


def test_param_file_entries_do_not_affect_define_diagnostics():
    t = _tracker('{"tasks": {"build": {"top": "t"}}}')
    assert t.unmatched() == []
    assert t.warnings() == []
