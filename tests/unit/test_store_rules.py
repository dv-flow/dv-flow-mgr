"""Store selection rules, lazy git context, and the SiteConfig plugin
registry (entry-point group dv_flow.mgr.site_config)."""
import json
import os
import subprocess
import sys

import pytest
import yaml

from dv_flow.mgr import site_config
from dv_flow.mgr.site_config import (SiteConfig, SiteConfigRgy, StoreContext,
                                     parse_git_org_repo)
from dv_flow.mgr.store_config import resolve_store, rule_matches


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    user = tmp_path / "user.yaml"
    site = tmp_path / "site.yaml"
    monkeypatch.setenv("DFM_USER_CONFIG", str(user))
    monkeypatch.setenv("DFM_SITE_CONFIG", str(site))
    monkeypatch.setenv("DFM_INSTALL_CONFIG", str(tmp_path / "install.yaml"))
    proj = tmp_path / "proj"
    proj.mkdir()

    class W:
        root = proj

        def user(self, data):
            user.write_text(yaml.safe_dump(data))

        def site(self, data):
            site.write_text(yaml.safe_dump(data))

        def ctx(self, **kw):
            kw.setdefault("user", "alice")
            kw.setdefault("host", "farm-01")
            return StoreContext(link=str(proj / "rundir"), project_root=str(proj),
                                package=kw.pop("package", "demo"), uid=1000, **kw)

        def resolve(self, ctx=None, **kw):
            return resolve_store(ctx or self.ctx(), str(proj), **kw)
    return W()


def _git_repo(path, remote="git@github.com:acme/widget.git", branch="main"):
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", remote],
                   check=True)


# ---------------------------------------------------------------- git facts

@pytest.mark.parametrize("url,org,repo", [
    ("git@github.com:acme/widget.git", "acme", "widget"),
    ("https://github.com/acme/widget.git", "acme", "widget"),
    ("https://github.com/acme/widget", "acme", "widget"),
    ("ssh://git@host:2222/acme/widget.git", "acme", "widget"),
    (None, None, None),
])
def test_parse_git_org_repo(url, org, repo):
    assert parse_git_org_repo(url) == (org, repo)


def test_context_git_lazy(cfg):
    _git_repo(cfg.root)
    ctx = cfg.ctx()
    assert not ctx.git_queried()
    assert ctx.git_remote() == "git@github.com:acme/widget.git"
    assert ctx.git_branch() == "main"
    assert ctx.git_org() == "acme" and ctx.git_repo() == "widget"


def test_context_non_git(cfg):
    ctx = cfg.ctx()
    assert ctx.git_remote() is None and ctx.git_branch() is None


# ---------------------------------------------------------------- matching

@pytest.mark.parametrize("match,expect", [
    ({"user": "alice"}, True),
    ({"user": "bob"}, False),
    ({"host": "farm-*"}, True),
    ({"host": "laptop"}, False),
    ({"package": "de*"}, True),
    ({"path": "*/proj"}, True),
    ({"path": "/nowhere/*"}, False),
    ({"link": "*/proj/rundir"}, True),
    ({"user": "alice", "host": "laptop"}, False),       # AND
    ({"bogus": "x"}, False),                            # unknown key
])
def test_rule_keys(cfg, match, expect):
    assert rule_matches({"name": "r", "match": match}, cfg.ctx(), "t") == expect


def test_rule_env_key(cfg, monkeypatch):
    monkeypatch.setenv("SITE", "acme-east")
    assert rule_matches({"match": {"env": {"SITE": "acme-*"}}}, cfg.ctx(), "t")
    assert not rule_matches({"match": {"env": {"SITE": "other"}}}, cfg.ctx(), "t")
    assert not rule_matches({"match": {"env": {"UNSET_VAR_X": "*"}}}, cfg.ctx(), "t")


def test_rule_git_keys(cfg):
    _git_repo(cfg.root, branch="dev")
    ctx = cfg.ctx()
    assert rule_matches({"match": {"git-remote": "*github.com[:/]acme/*"}}, ctx, "t")
    assert rule_matches({"match": {"git-branch": "dev"}}, ctx, "t")
    assert not rule_matches({"match": {"git-remote": "*gitlab*"}}, ctx, "t")


def test_git_rule_on_non_git_project_does_not_match(cfg):
    assert not rule_matches({"match": {"git-remote": "*"}}, cfg.ctx(), "t")


def test_git_not_queried_without_git_rules(cfg, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(site_config, "_git", lambda *a: calls.append(a))
    cfg.user({"store": {"rules": [{"name": "u", "match": {"user": "alice"},
                                   "root": str(tmp_path / "s")}]}})
    assert cfg.resolve().root == str(tmp_path / "s")
    assert calls == []


# ---------------------------------------------------------------- rule evaluation

def test_first_match_wins_and_provenance(cfg, tmp_path):
    cfg.site({"store": {"rules": [
        {"name": "nomatch", "match": {"user": "bob"}, "root": str(tmp_path / "a")},
        {"name": "farm", "match": {"host": "farm-*"}, "root": str(tmp_path / "b")},
        {"name": "also", "match": {"host": "*"}, "root": str(tmp_path / "c")},
    ]}})
    d = cfg.resolve()
    assert d.root == str(tmp_path / "b") and d.provenance == "site-rule:farm"


def test_rules_before_root_in_same_file(cfg, tmp_path):
    cfg.site({"store": {"root": str(tmp_path / "plain"), "rules": [
        {"name": "r", "match": {"user": "alice"}, "root": str(tmp_path / "rule")}]}})
    assert cfg.resolve().root == str(tmp_path / "rule")
    assert cfg.resolve(cfg.ctx(user="bob")).root == str(tmp_path / "plain")


def test_user_root_beats_site_rule(cfg, tmp_path):
    cfg.user({"store": {"root": str(tmp_path / "u")}})
    cfg.site({"store": {"rules": [{"name": "r", "match": {}, "root": str(tmp_path / "s")}]}})
    assert cfg.resolve().root == str(tmp_path / "u")


def test_rule_local(cfg, tmp_path):
    cfg.site({"store": {"root": str(tmp_path / "s"), "rules": [
        {"name": "sandbox", "match": {"path": "*/proj"}, "root": "local"}]}})
    d = cfg.resolve()
    assert d.root is None and d.provenance == "site-rule:sandbox"


def test_rule_templates(cfg, tmp_path):
    _git_repo(cfg.root)
    cfg.site({"store": {"rules": [{"name": "t", "match": {},
        "root": str(tmp_path) + "/${git_org}/${git_repo}/${user}/${host}/${package}"}]}})
    assert cfg.resolve().root == str(tmp_path / "acme/widget/alice/farm-01/demo")


def test_rule_unresolved_template_skips(cfg, tmp_path):
    cfg.site({"store": {"rules": [
        {"name": "git", "match": {}, "root": "/x/${git_org}"},
        {"name": "fallback", "match": {}, "root": str(tmp_path / "f")}]}})
    d = cfg.resolve()
    assert d.provenance == "site-rule:fallback"


# ---------------------------------------------------------------- plugin

class _EP:
    def __init__(self, name, target):
        self.name = name
        self._t = target

    def load(self):
        if isinstance(self._t, Exception):
            raise self._t
        return self._t


def _plugin(root):
    class P(SiteConfig):
        def get_store(self, ctx):
            return root
    return P


@pytest.fixture
def eps(monkeypatch):
    lst = []
    monkeypatch.setattr(site_config, "_load_entry_points", lambda: list(lst))
    SiteConfigRgy.reset()
    yield lst
    SiteConfigRgy.reset()


def test_plugin_last_registered(cfg, eps, tmp_path):
    eps += [_EP("a", _plugin(str(tmp_path / "a"))), _EP("b", _plugin(str(tmp_path / "b")))]
    d = cfg.resolve()
    assert d.root == str(tmp_path / "b") and d.provenance == "site-plugin:b"


def test_plugin_env_selection(cfg, eps, tmp_path, monkeypatch):
    eps += [_EP("a", _plugin(str(tmp_path / "a"))), _EP("b", _plugin(str(tmp_path / "b")))]
    monkeypatch.setenv("DFM_SITE_CONFIG_NAME", "a")
    assert cfg.resolve().root == str(tmp_path / "a")
    assert SiteConfigRgy.inst().active_reason == "env:DFM_SITE_CONFIG_NAME"


def test_plugin_yaml_selection(cfg, eps, tmp_path):
    eps += [_EP("a", _plugin(str(tmp_path / "a"))), _EP("b", _plugin(str(tmp_path / "b")))]
    cfg.site({"site-config": "a"})
    assert cfg.resolve().root == str(tmp_path / "a")


def test_plugin_unknown_selection(cfg, eps, tmp_path, monkeypatch):
    eps += [_EP("a", _plugin(str(tmp_path / "a")))]
    monkeypatch.setenv("DFM_SITE_CONFIG_NAME", "nope")
    assert cfg.resolve().root is None


def test_plugin_after_yaml(cfg, eps, tmp_path):
    eps.append(_EP("p", _plugin(str(tmp_path / "plug"))))
    cfg.site({"store": {"root": str(tmp_path / "site")}})
    assert cfg.resolve().root == str(tmp_path / "site")


@pytest.mark.parametrize("ret,root", [(None, None), ("local", None), ("", None)])
def test_plugin_defer_or_local(cfg, eps, ret, root):
    eps.append(_EP("p", _plugin(ret)))
    d = cfg.resolve()
    assert d.root == root
    assert d.provenance == ("default:local" if ret is None else "site-plugin:p")


def test_plugin_factory_and_failures(cfg, eps, tmp_path, caplog):
    eps.append(_EP("broken", ImportError("no module")))
    eps.append(_EP("factory", lambda: _plugin(str(tmp_path / "f"))()))
    assert cfg.resolve().root == str(tmp_path / "f")
    assert SiteConfigRgy.inst().errors()[0][0] == "broken"


def test_plugin_get_store_raises(cfg, eps):
    class Bad(SiteConfig):
        def get_store(self, ctx):
            raise RuntimeError("x")
    eps.append(_EP("bad", Bad))
    assert cfg.resolve().root is None


def test_plugin_sees_context(cfg, eps, tmp_path):
    seen = {}

    class P(SiteConfig):
        def get_store(self, ctx):
            seen.update(user=ctx.user, package=ctx.package, link=ctx.link)
            return str(tmp_path / ctx.user)
    eps.append(_EP("p", P))
    assert cfg.resolve().root == str(tmp_path / "alice")
    assert seen["package"] == "demo" and seen["link"].endswith("/proj/rundir")


# ---------------------------------------------------------------- show site-config

def test_show_site_config_json(cfg, tmp_path):
    (cfg.root / "flow.yaml").write_text("package:\n  name: demo\n")
    cfg.user({"store": {"root": str(tmp_path / "u")}})
    r = subprocess.run([sys.executable, "-m", "dv_flow.mgr", "show", "site-config",
                        "--json"], cwd=str(cfg.root), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["store"]["root"] == str(tmp_path / "u")
    assert d["store"]["provenance"].startswith("user-config:")
    layers = [f["layer"] for f in d["files"]]
    assert layers[:2] == ["install", "site"] and "project" in layers
