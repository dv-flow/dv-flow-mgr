import os

# The ONE place dfm's version is written. pyproject.toml reads `_pkg_version`
# (`dynamic = ["version"]`), and the release workflow stamps SUFFIX here --
# `.dev<run>+gh` on a non-release build -- so the wheel's metadata and the
# runtime version cannot disagree. Keep this file free of imports beyond the
# standard library: setuptools loads it on its own, in an isolated build.
BASE = "1.20.0"
SUFFIX = ""

__version__ = (BASE, SUFFIX)

_pkg_version = BASE + SUFFIX


def get_version():
    """Return the full version string.

    In a source tree this is decorated with `git describe`, so a build from
    an untagged commit says which one.
    """
    version = _pkg_version

    src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    if os.path.isdir(os.path.join(src_dir, ".git")):
        try:
            import subprocess
            out = subprocess.check_output(
                ["git", "describe", "--tags", "--dirty", "--always"],
                cwd=src_dir,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            if out.lstrip("v") != BASE:
                return "%s+%s" % (version, out)
        except Exception:
            pass

    return version
