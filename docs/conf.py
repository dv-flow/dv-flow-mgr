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
# (docs/reference/stdlib.rst). It is a documentation dependency, declared in the
# `docs` extra -- but in the development checkout it lives beside this package
# rather than being installed, so fall back to the sibling source tree.
_DEV_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
if os.path.isdir(os.path.join(_DEV_SRC, "sphinx_dv_flow")):
    sys.path.insert(0, _DEV_SRC)

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
