#****************************************************************************
#* skills.py
#*
#* Agent-skill discovery entry point.
#*
#* Packaging tools (e.g. ivpm) discover bundled agent skills via the
#* 'agent.skills' entry-point group. Each entry point resolves to a callable
#* that returns one or more skill directories; each directory must contain a
#* 'SKILL.md' file with valid front-matter.
#****************************************************************************
import os


def get_skill_dirs():
    """Return the list of bundled agent-skill directories.

    Auto-discovers every immediate subdirectory of ``share/skills`` that
    contains a ``SKILL.md`` file, so newly bundled skills register without
    editing this function. Referenced by the 'agent.skills' entry point in
    pyproject.toml.
    """
    share = os.path.join(os.path.dirname(__file__), "share", "skills")
    if not os.path.isdir(share):
        return []
    return [
        os.path.join(share, name)
        for name in sorted(os.listdir(share))
        if os.path.isfile(os.path.join(share, name, "SKILL.md"))
    ]
