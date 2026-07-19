"""
panel.py
 
Reusable panel container. Every content section (a table, a chart, a form)
sits inside one of these so spacing, border, and shadow stay consistent
across the whole app instead of every page inventing its own container.
 
Usage:
    from components.panel import panel
 
    with panel("Facility Status", toolbar="Last updated 2 min ago"):
        st.write("panel body goes here — any Streamlit widgets")
 
Implementation note: an earlier draft of this component tried to open an
HTML <div> in one st.markdown() call and close it in a later one, hoping
Streamlit widgets rendered in between would end up visually "inside" it.
That does NOT work — each st.markdown() call is its own isolated DOM node,
so the browser auto-closes the unclosed <div> at that call's own boundary,
and anything rendered afterwards is a sibling, not a child. The reliable
fix is to use Streamlit's own native bordered container (st.container
(border=True), available from Streamlit 1.29+) as the actual box, and
theme its default border/shadow via CSS in theme.css targeting
div[data-testid="stVerticalBlockBorderWrapper"]. Everything written inside
the `with panel(...):` block — including this component's own header
markup — is rendered as a genuine child of that one container, so it's
guaranteed to render inside the box.
 
Note: the "stVerticalBlockBorderWrapper" test id has been stable across
recent Streamlit releases but is not a public API; if a future Streamlit
version renames it, update the selector in theme.css (search for that
string) — the panel() function itself would not need to change.
 
Streamlit 1.51.0 rendering note: the header markup below is built as one
flush-left string with no embedded newlines, not an indented multi-line
f-string. st.markdown() runs its content through a real Markdown parser
before unsafe_allow_html is honored, and a line indented 4+ spaces at the
start of a block (as an earlier, indented version of this markup did) is
classified as an indented code block and rendered as literal escaped text
regardless of unsafe_allow_html. Verified by reproducing that exact markup
and feeding it through a real Markdown parser (mistune): it came back
wrapped in <pre><code> with HTML-escaped entities — the "raw HTML on
screen" symptom. The flush-left, no-blank-line form here was re-verified
the same way to render clean, unescaped HTML.
"""
 
from __future__ import annotations
from contextlib import contextmanager
from typing import Optional
import html
import streamlit as st
 
 
@contextmanager
def panel(title: str, toolbar: Optional[str] = None):
    """
    Context manager that renders a themed panel. Anything written inside
    the `with` block becomes the panel body, as a true child of the
    underlying bordered container (see module docstring for why that
    matters).
 
    Args:
        title: Panel heading, e.g. "Facility Status".
        toolbar: Optional short right-aligned text (e.g. a timestamp or
                 filter summary). Not for buttons — use components.buttons
                 above or below the panel for actions.
    """
    safe_title = html.escape(title)
    toolbar_html = f'<span class="medevac-panel-toolbar">{html.escape(toolbar)}</span>' if toolbar else ""
 
    header_html = (
        '<div class="medevac-panel-header">'
        f'<span class="medevac-panel-title">{safe_title}</span>'
        f'{toolbar_html}'
        '</div>'
    )
 
    container = st.container(border=True)
    with container:
        st.markdown(header_html, unsafe_allow_html=True)
        yield container