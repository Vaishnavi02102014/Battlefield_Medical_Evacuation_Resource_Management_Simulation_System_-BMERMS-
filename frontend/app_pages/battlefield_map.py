"""
battlefield_map.py

Placeholder page for the Battlefield Map section. This exists only to prove the
page_router wiring end to end — real Battlefield Map UI arrives in a later phase.
"""

import streamlit as st


def render() -> None:
    """Render the Battlefield Map page (placeholder only)."""
    st.markdown(
        '<div style="color: var(--color-text-secondary); padding: 12px 4px;">'
        '<h3 style="color: var(--color-text-primary); margin-bottom: 4px;">Battlefield Map Coming Soon</h3>'
        'This section will be implemented in an upcoming phase.'
        '</div>',
        unsafe_allow_html=True,
    )
