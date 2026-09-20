#****************************************************************************
#* tui_theme.py
#*
#* Copyright 2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may
#* not use this file except in compliance with the License.
#* You may obtain a copy of the License at:
#*
#*   http://www.apache.org/licenses/LICENSE-2.0
#*
#* Unless required by applicable law or agreed to in writing, software
#* distributed under the License is distributed on an "AS IS" BASIS,
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#* See the License for the specific language governing permissions and
#* limitations under the License.
#*
#****************************************************************************
"""Shared Rich styles for dfm's console output.

Rich's ``dim`` emits SGR 2, which terminals render by blending the foreground
toward the background.  On a dark theme that yields readable grey-on-black; on
a light theme it yields pale-grey-on-white, which is effectively invisible.
The blend is a property of the attribute, not of a colour choice, so no amount
of light/dark detection fixes it -- the answer is to stop using ``dim`` for
anything the user has to read.

The rule this module encodes:

  * ``dim`` is reserved for marks that carry no information -- em-dashes,
    ellipses, a separator glyph.  If the terminal swallows them entirely,
    nothing is lost: that is precisely the signal ("nothing to see here").
  * Text the user must read uses either the default foreground or a named ANSI
    colour.  Named colours are resolved from the terminal's own palette, so
    they track the user's light/dark theme automatically.  No hex, no
    ``bright_*``, no literal ``white``/``black``.
  * De-emphasis that was purely visual hierarchy -- a secondary table column --
    becomes no style at all.  Column position and the header already supply the
    hierarchy; the data itself renders in the default foreground.

An emptiness marker -- "(none)", "(idle)", "(no active tasks)" -- is NOT a
placeholder under this rule, however much it looks like one.  It is the answer
to the question the row asks ("what views does this suite offer?"), the cell
would read as a rendering bug without it, and a reader scanning for "which of
these is empty?" is reading exactly those cells.  They take ``S_SECONDARY``.

Use the semantic names below rather than raw style strings, so the light-mode
contrast decision stays in one place.
"""

# Marks that are safe to lose: em-dashes, ellipses, a bare "?" standing in for
# an unknown.  These stay dim on purpose -- they should recede.  Nothing in dfm
# uses this today (see the note above about emptiness markers); it is here so
# that the one style allowed to be `dim` has a name and a stated test.
S_PLACEHOLDER = "dim"

# Subordinate lines the user still reads: continuation/detail lines listed
# under a parent row.
S_DETAIL = "cyan"

# Inline field labels ("model:", "workers:"), parenthetical annotations, usage
# hints and legend/footnote lines.  Cyan separates label from value without
# relying on contrast against the background.
S_LABEL = "cyan"

# Readable-but-subordinate values that were only dim to de-emphasise a table
# column.  Rich parses "none" as the null style, so this is usable both as a
# `style=` argument and inside "[secondary]...[/secondary]" markup.
S_SECONDARY = "none"

# Panel and table borders.  A dim border disappears on a light background,
# taking the box with it; a named colour survives both themes.
S_BORDER = "cyan"


# Same vocabulary, exposed as Rich markup tags so console.print("[label]...")
# call sites share the definitions above rather than hard-coding "dim".
DFM_THEME = {
    "placeholder": S_PLACEHOLDER,
    "detail":      S_DETAIL,
    "label":       S_LABEL,
    "secondary":   S_SECONDARY,
    "border":      S_BORDER,
}


def make_console(**kwargs):
    """Return a Rich Console with dfm's theme registered.

    Rich is imported lazily (as everywhere else in dfm) so that importing this
    module stays cheap.
    """
    from rich.console import Console
    from rich.theme import Theme
    return Console(theme=Theme(DFM_THEME), **kwargs)
