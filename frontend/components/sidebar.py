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


































# OLD
# """
# sidebar.py

# The one sidebar used identically on every page. Owns its own collapse state
# and current-page state in st.session_state, so calling render_sidebar()
# from any page reproduces the exact same sidebar, already remembering
# whatever the person last did with it.

# Usage (from a page):
#     from components.sidebar import render_sidebar

#     current_page = render_sidebar()
#     if current_page == "Dashboard":
#         ...  # render_sidebar() just tells you what's selected; this
#              # foundation does not render any page content itself.
# """

# from __future__ import annotations
# import streamlit as st

# from utils.theme import css_marker

# # Fixed nav order. Each entry is (page_name, icon). Icons are plain emoji
# # characters, which is the one icon mechanism guaranteed to render with
# # zero extra dependencies and zero network access in any Streamlit version.
# NAV_ITEMS: list[tuple[str, str]] = [
#     ("Dashboard", "⌂"),
#     ("Simulation", "◎"),
#     ("Facilities", "▣"),
#     ("Battlefield Map", "⌖"),
#     ("Resources", "◫"),
#     ("Patients", "◉"),
#     ("Analytics", "◧"),
#     ("Reports", "☰"),
#     ("Alerts", "⚠"),
# ]

# BRAND_NAME = "BMERMS"
# BRAND_SUBTITLE = "Medical Evacuation Command"


# def render_sidebar(default_page: str = "Dashboard") -> str:
#     """
#     Render the full sidebar (brand, collapse toggle, nav, Emergency
#     Response, footer links) and return the currently selected page name.

#     This function owns two pieces of session_state:
#         - "sidebar_collapsed" (bool) — persists the collapse toggle.
#         - "current_page" (str) — persists which nav item is active.
#     Both survive Streamlit reruns automatically since session_state is
#     only initialized once (via setdefault) and this function is the only
#     place that mutates either value.
#     """
#     st.session_state.setdefault("current_page", default_page)

#     with st.sidebar:
#         st.markdown('<div class="medevac-sidebar-divider"></div>', unsafe_allow_html=True)
    
#         current_page = st.session_state["current_page"]
#         for name, icon in NAV_ITEMS:
#             label = f"{icon}  {name}"
#             if name == current_page:
#                 css_marker("medevac-nav-active-marker")
#             if st.button(label, key=f"nav_btn_{name}", use_container_width=True):
#                 st.session_state["current_page"] = name
#                 st.rerun()

#         st.markdown('<div class="medevac-sidebar-divider"></div>', unsafe_allow_html=True)

#         # Pushes the Emergency Response button toward the bottom of the
#         # sidebar. Relies on theme.css making the sidebar's own content
#         # block a flex column (see the ".medevac-sidebar-spacer" rule) so
#         # this spacer's flex-grow has a flex parent to grow inside of.
#         # Verify visually against your installed Streamlit version — the
#         # underlying container test id has been stable but is not a
#         # guaranteed public API.
#     return st.session_state["current_page"]
