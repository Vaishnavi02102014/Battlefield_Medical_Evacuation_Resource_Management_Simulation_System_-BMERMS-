"""
header.py
 
Reusable top header bar. Shown once per page, directly under the sidebar's
content area. Pure display component — it takes already-computed values as
arguments, so it has no dependency on the simulation/database backend.
"""
 
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
import html
import streamlit as st
 
from utils.theme import resolve_color
 
STATUS_COLOR_MAP: dict[str, str] = {
    "Operational": "primary",
    "Busy": "warning",
    "High Load": "warning",
    "Critical": "danger",
}
 
 
def render_header(
    current_date: Optional[date] = None,
    simulation_day: Optional[int] = None,
    simulation_time: Optional[str] = None,
    operational_status: str = "Operational",
) -> None:
    """
    Render the header bar.
 
    Args:
        current_date: Real-world date to display. Defaults to today.
        simulation_day: Simulated day number (e.g. from SimulationClock.simulation_day).
                        Shown as "—" if not supplied (e.g. before simulation starts).
        simulation_time: Simulated clock time string (e.g. "09:15").
                         Shown as "—" if not supplied.
        operational_status: One of STATUS_COLOR_MAP's keys. Any other string
                             is shown as-is with the neutral/info color.
 
    Root cause of the "raw HTML printed as text" bug (fixed here):
    st.markdown() runs its content through a real Markdown parser before
    unsafe_allow_html is honored. Markdown's "indented code block" rule
    triggers on any line indented 4+ spaces that follows a blank line —
    regardless of unsafe_allow_html — and renders that content as literal
    escaped text instead of parsing it as HTML. The previous version of
    this function built the HTML with dedent(f\"\"\"...\"\"\"), but dedent()
    only strips the SHARED minimum indentation across all lines; nested
    tags (indented deeper than the outermost <div>) kept 4/8/12+ spaces of
    leading whitespace, and blank lines separated the elements. That
    combination is exactly what triggers the indented-code-block rule.
    This was verified by reproducing the exact dedent() output and feeding
    it through a real Markdown parser (mistune): nested content came back
    wrapped in <pre><code> with HTML-escaped entities, matching the
    reported symptom exactly. The fix is structural: build the string with
    zero leading whitespace on every line and no blank line anywhere
    inside it, which was re-verified the same way to produce clean,
    unescaped HTML output.
    """
    display_date = (current_date or datetime.now().date()).strftime("%d %b %Y")
    display_day = f"Day {simulation_day}" if simulation_day is not None else "—"
    display_time = simulation_time if simulation_time else "—"
 
    status_key = STATUS_COLOR_MAP.get(operational_status, "info")
    status_color = resolve_color(status_key)
    safe_status = html.escape(operational_status)
 
    header_html = (
        '<div class="medevac-header">'
        '<div class="medevac-header-left">'
        '<div class="medevac-brand-title">BMERMS</div>'
        '<div class="medevac-brand-subtitle">'
        "Battlefield Medical Evacuation &amp; Resource Management System"
        "</div>"
        "</div>"
        '<div class="medevac-header-right">'
        '<div class="medevac-header-item">'
        '<span class="medevac-header-item-label">DATE</span>'
        f'<span class="medevac-header-item-value">{display_date}</span>'
        "</div>"
        '<div class="medevac-header-item">'
        '<span class="medevac-header-item-label">SIM DAY</span>'
        f'<span class="medevac-header-item-value">{display_day}</span>'
        "</div>"
        '<div class="medevac-header-item">'
        '<span class="medevac-header-item-label">SIM TIME</span>'
        f'<span class="medevac-header-item-value">{display_time}</span>'
        "</div>"
        f'<span class="medevac-status-badge" style="color:{status_color};">'
        '<span class="medevac-status-dot"></span>'
        f"{safe_status}"
        "</span>"
        "</div>"
        "</div>"
    )
 
    st.markdown(header_html, unsafe_allow_html=True)






































