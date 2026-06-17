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

    Each returned directory contains a 'SKILL.md' describing the skill.
    Referenced by the 'agent.skills' entry point in pyproject.toml.
    """
    share = os.path.join(os.path.dirname(__file__), "share", "skills")
    return [os.path.join(share, "dv-flow-manager")]
