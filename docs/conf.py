# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'DV Flow Manager'
copyright = '2023-2025, Matthew Ballance'
author = 'Matthew Ballance'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

import os
import sys

# sphinx-dv-flow generates the standard-library reference from `std/flow.yaml`
# (docs/reference/stdlib.rst). ivpm brings it in as a `dep-set: use` import,
# which CHECKS IT OUT but does not install it into packages/python -- so
# `import sphinx_dv_flow` fails in the ivpm venv and the extension has to be put
# on the path from here. Candidates, in order: the ivpm checkout, then a sibling
# development checkout.
#
# The previous form of this fallback resolved to <projects>/dv-flow/src, which
# has never existed; the build worked only when PYTHONPATH was set by hand. A
# path that points at nothing fails silently -- os.path.isdir() is simply False
# and Sphinx reports a missing extension one step later -- so keep these
# relative to conf.py and keep them pointing at real directories.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _cand in (
        os.path.join(_HERE, "..", "packages", "sphinx-dv-flow", "src"),
        os.path.join(_HERE, "..", "..", "sphinx-dv-flow", "src")):
    _cand = os.path.abspath(_cand)
    if os.path.isdir(os.path.join(_cand, "sphinx_dv_flow")):
        sys.path.insert(0, _cand)
        break

extensions = [
    'sphinxarg.ext',
    'sphinx-jsonschema',
    'sphinxcontrib.mermaid',
    'sphinx_dv_flow',
]

# The standard library is the package this project documents with its own
# extension. Pointing at the source tree rather than the installed copy keeps
# the documentation describing the code in this checkout.
dvflow_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src", "dv_flow", "mgr", "std"))

# Structural keys on a generated page link into the schema reference on this
# same site, which is the seam readers otherwise fall through.
dvflow_schema_url = "reference/flow_spec.html#{key}"

# `doc:` prose in std/flow.yaml is Markdown -- fenced code blocks and
# single-backtick code spans. That is what gets written when the same string is
# also read by `dfm show` and `dfm llms`, neither of which renders rST.
dvflow_doc_format = "markdown"

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'furo'
html_static_path = ['_static']
