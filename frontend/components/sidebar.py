"""
sidebar.py
 
The one sidebar used identically on every page. Static and permanently
visible at a fixed width (see assets/theme.css's --sidebar-width) — there
is no collapse/expand behavior, no toggle button, and no slide animation.
Owns current-page state in st.session_state, so calling render_sidebar()
from any page reproduces the exact same sidebar, already remembering
whatever the person last clicked.
 
Usage (from a page):
    from components.sidebar import render_sidebar
 
    current_page = render_sidebar()
    if current_page == "Dashboard":
        ...  # render_sidebar() just tells you what's selected; this
             # foundation does not render any page content itself.
"""
 
from __future__ import annotations
import streamlit as st
 
from utils.theme import css_marker
 
# Fixed nav order. Each entry is (page_name, icon). Icons are plain emoji
# characters, which is the one icon mechanism guaranteed to render with
# zero extra dependencies and zero network access in any Streamlit version.
NAV_ITEMS: list[tuple[str, str]] = [
    ("Dashboard", "⌂"),
    ("Simulation", "◎"),
    ("Facilities", "▣"),
    ("Resources", "◫"),
    ("Patients", "◉"),
    ("Analytics", "◧"),
]
 
BRAND_NAME = "BMERMS"
BRAND_SUBTITLE = "Medical Evacuation Command"
 
 
def render_sidebar(default_page: str = "Dashboard") -> str:
    """
    Render the static sidebar (nav items only) and return the currently
    selected page name.
 
    This function owns one piece of session_state:
        - "current_page" (str) — persists which nav item is active.
    It survives Streamlit reruns automatically since session_state is only
    initialized once (via setdefault) and this function is the only place
    that mutates it.
    """
    st.session_state.setdefault("current_page", default_page)
 
    with st.sidebar:
        st.markdown('<div class="medevac-sidebar-divider"></div>', unsafe_allow_html=True)
 
        current_page = st.session_state["current_page"]
        for name, icon in NAV_ITEMS:
            label = f"{icon}  {name}"
            if name == current_page:
                css_marker("medevac-nav-active-marker")
            if st.button(label, key=f"nav_btn_{name}", use_container_width=True):
                st.session_state["current_page"] = name
                st.rerun()
 
        st.markdown('<div class="medevac-sidebar-divider"></div>', unsafe_allow_html=True)
 
    return st.session_state["current_page"]