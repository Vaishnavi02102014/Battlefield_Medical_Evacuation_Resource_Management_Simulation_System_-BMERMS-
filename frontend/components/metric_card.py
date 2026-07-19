"""
metric_card.py
 
Reusable KPI card. Every dashboard metric (Today's Casualties, Beds
Occupied, Average Waiting Time, ...) renders through this one component so
every card looks identical regardless of which page or data source feeds it.
 
This is a pure display component (renders HTML via st.markdown) — it has no
knowledge of the simulation/database layer. Callers pass already-computed
values in.
"""
 
from __future__ import annotations
from typing import Optional, Union
import html
import streamlit as st
 
from utils.theme import resolve_color
 
 
def metric_card(
    title: str,
    value: Union[str, int, float],
    subtitle: Optional[str] = None,
    icon: Optional[str] = None,
    color: str = "primary",
    delta: Optional[Union[str, int, float]] = None,
) -> None:
    """
    Render one KPI card.
 
    Args:
        title: Short label, e.g. "Today's Casualties".
        value: The headline number/string, e.g. 47.
        subtitle: Optional small descriptive line under the value.
        icon: Optional emoji/character shown top-right of the title row.
        color: Semantic accent color — "primary" | "danger" | "warning" | "info",
               or a raw hex string (e.g. "#9FD68C").
        delta: Optional trend value. A leading "+" or positive number renders
               green with an up arrow; a leading "-" or negative number
               renders red with a down arrow; "0" or "0%" renders neutral.
 
    Streamlit 1.51.0 rendering note: st.markdown() runs its content through
    a real Markdown parser before unsafe_allow_html is honored. A line
    indented 4+ spaces starting a block (as the previous multi-line,
    indented f-string here did) is classified as an indented code block and
    rendered as literal escaped text, regardless of unsafe_allow_html. This
    was verified by reproducing the exact previous markup and feeding it
    through a real Markdown parser (mistune): it came back wrapped in
    <pre><code> with HTML-escaped entities — the exact "raw HTML on screen"
    symptom. The fix is structural: build the markup as one flush-left
    string with no embedded newlines, re-verified the same way to render
    clean, unescaped HTML.
    """
    accent = resolve_color(color)
    safe_title = html.escape(title)
    safe_value = html.escape(str(value))
    icon_html = f'<span class="medevac-metric-icon">{icon}</span>' if icon else ""
    subtitle_html = f'<div class="medevac-metric-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
    delta_html = _render_delta(delta)
 
    card_html = (
        f'<div class="medevac-metric-card" style="--metric-accent: {accent};">'
        '<div class="medevac-metric-top">'
        f'<span class="medevac-metric-title">{safe_title}</span>'
        f'{icon_html}'
        '</div>'
        f'<div class="medevac-metric-value">{safe_value}</div>'
        f'{subtitle_html}'
        f'{delta_html}'
        '</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)
 
 
def _render_delta(delta: Optional[Union[str, int, float]]) -> str:
    if delta is None:
        return ""
 
    text = str(delta).strip()
    direction = "flat"
    arrow = "→"
 
    numeric_text = text.replace("%", "").replace("+", "")
    try:
        numeric_value = float(numeric_text)
        if numeric_value > 0:
            direction, arrow = "up", "↑"
        elif numeric_value < 0:
            direction, arrow = "down", "↓"
    except ValueError:
        # Non-numeric delta text (e.g. "stable") — leave as flat/neutral.
        pass
 
    safe_text = html.escape(text)
    return f'<div class="medevac-metric-delta {direction}">{arrow} {safe_text}</div>'