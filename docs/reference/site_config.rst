###########
Site Config
###########

dfm reads configuration from layered YAML files, and can load a Python
*site-config plugin* for decisions that need code. This page covers the
files, the ``store:`` section that places rundirs (see
:doc:`/guide/rundir_store`), and how to write a plugin. Runner settings in
the same files are described in :doc:`runner_config`.

Config files
============

============ ============================================== ======================
Layer        Path                                           Override
============ ============================================== ======================
install      ``<sys.prefix>/etc/dfm/config.yaml``           ``DFM_INSTALL_CONFIG``
site         ``/etc/dfm/config.yaml``                       ``DFM_SITE_CONFIG``
user         ``$XDG_CONFIG_HOME/dfm/config.yaml``           ``DFM_USER_CONFIG``
             (default ``~/.config/dfm/config.yaml``)
project      ``<package-root>/.dfm/config.yaml``
============ ============================================== ======================

``~/.config/dfm/site.yaml`` -- the name used before the site layer existed --
is still read as user config. Where both exist, ``config.yaml`` wins key by
key. Rename ``site.yaml`` to ``config.yaml``.

``dfm show site-config`` lists the files consulted, whether each exists, the
installed plugins and the resulting store decision.

The ``store:`` section
======================

.. code-block:: yaml

    store:
      root: /scratch/${USER}/dfm    # "" or "local" = no store
      create: true                  # may dfm create the root if missing?
      rules:                        # first match wins; tried before `root`
        - name: acme-farm
          match:
            git-remote: "*github.com[:/]acme/*"
            host: "farm-*"
          root: /proj/acme/scratch/${user}/dfm
        - name: sandboxes
          match:
            path: "/home/*/sandbox/*"
          root: local

``root``
    Absolute path of the store, after expansion; relative paths are ignored
    with a warning. ``local`` or ``""`` means "no store".

``create``
    If true (the default), dfm creates a missing store root when its parent
    directory exists. If false, a missing root is an error.

``rules``
    A list of ``{name, match, root}``. All keys in ``match`` must match
    (``fnmatch`` globs; ``*`` also matches ``/``). The first matching rule's
    ``root`` is used. A rule whose ``root`` cannot be expanded is skipped.

Match keys
----------

=============== ===========================================================
Key             Matched against
=============== ===========================================================
``path``        The project (package) root directory
``link``        The rundir link path, ``<package-root>/rundir``
``user``        The user name
``host``        The short host name
``git-remote``  ``remote.origin.url`` of the project's git repository
``git-branch``  The current branch
``package``     The root package name
``env``         A mapping of environment variable name to glob
=============== ===========================================================

Git is only queried when a rule uses a git key. A project that is not a git
repository, or has no ``origin``, never matches a git key.

Template variables
------------------

``root`` values may use ``${user}``, ``${host}``, ``${package}``,
``${git_org}`` and ``${git_repo}`` (parsed from the remote URL), any
environment variable as ``${NAME}``, and a leading ``~``.

Precedence
==========

The first source with an opinion decides:

1. ``--no-store`` / ``--store DIR`` on the command line
2. ``DFM_STORE`` (``""`` or ``local`` means no store)
3. The project file -- which may only opt out (``store: {root: local}``);
   any other value is ignored with a warning
4. User file (rules, then ``root``)
5. Site file
6. Install file
7. The site-config plugin's ``get_store()``
8. Local ``<package-root>/rundir``

Each decision records where it came from (``env:DFM_STORE``,
``user-config:<path>``, ``site-rule:<name>``, ``site-plugin:<name>``, ...).
``dfm store info`` shows it and it is stored in the entry's metadata.

Note that the project file is consulted differently from runner config, where
a project file overrides user settings: where a rundir lives depends on the
user's machine and site, which a checked-in project cannot know.

Writing a site-config plugin
============================

A plugin is a Python class derived from
``dv_flow.mgr.site_config.SiteConfig``, registered under the
``dv_flow.mgr.site_config`` entry-point group:

.. code-block:: toml

    # pyproject.toml of your site package
    [project.entry-points."dv_flow.mgr.site_config"]
    acme = "acme_dfm.site:AcmeSiteConfig"

.. code-block:: python

    # acme_dfm/site.py
    import grp
    from dv_flow.mgr.site_config import SiteConfig

    class AcmeSiteConfig(SiteConfig):
        def get_store(self, ctx):
            # ctx: link, project_root, package, user, uid, host,
            #      git_remote(), git_branch(), git_org(), git_repo()
            groups = {g.gr_name for g in grp.getgrall() if ctx.user in g.gr_mem}
            if "chip-team" in groups:
                return "/proj/chip/scratch/%s/dfm" % ctx.user
            if (ctx.git_org() or "") == "acme":
                return "/scratch/%s/dfm" % ctx.user
            return None          # no opinion: fall through to local

``get_store`` returns a store root, ``"local"`` (or ``""``) for no store, or
``None`` to defer. Git facts on ``ctx`` are looked up lazily, on first call.
An exception in the hook is logged and treated as ``None``.

The target may also be a zero-argument factory returning a ``SiteConfig``.

One plugin is active at a time, chosen by:

1. ``DFM_SITE_CONFIG_NAME``
2. ``site-config: <name>`` in the user, then site, config file
3. otherwise, the last one registered

The plugin is consulted after the YAML layers, so a user or site file can
always pin a location regardless of the plugin.

Environment variables
=====================

``DFM_STORE``
    Store root, overriding config files. ``""`` or ``local`` disables the
    store.

``DFM_STORE_RECREATE``
    ``1`` makes a dangling rundir link get recreated in the configured store
    instead of stopping with an error (same as ``dfm run --store-recreate``).

``DFM_USER_CONFIG``, ``DFM_SITE_CONFIG``, ``DFM_INSTALL_CONFIG``
    Paths of the user, site and install config files.

``DFM_SITE_CONFIG_NAME``
    Name of the site-config plugin to activate.
