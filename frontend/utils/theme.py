"""
theme.py
 
Single source of truth (in Python) for the application's design tokens, and
the helper that injects assets/theme.css into the page. No component should
hardcode a color, radius, or spacing value directly — import it from here so
the whole app stays visually consistent from one place.
 
These constants intentionally mirror the CSS custom properties declared in
assets/theme.css 1:1. If a value changes, change it in both places.
"""
 
from __future__ import annotations
from pathlib import Path
import streamlit as st
 
# --------------------------------------------------------------------------
# COLOR TOKENS
# Synced to match assets/theme.css's :root custom properties exactly. These
# had drifted out of sync with theme.css (e.g. COLOR_PRIMARY here was
# #9FD68C while theme.css's --color-primary is #8FBC6B) — that mismatch
# fed wrong colors into resolve_color(), which metric_card.py and
# header.py use for accent colors and the status badge.
# --------------------------------------------------------------------------
COLOR_BACKGROUND: str = "#0B1522"
COLOR_CARD: str = "#172635"
COLOR_BORDER: str = "#2B4154"
COLOR_PRIMARY: str = "#8FBC6B"
COLOR_DANGER: str = "#D9534F"
COLOR_WARNING: str = "#F2B94B"
COLOR_INFO: str = "#6EA8FE"
COLOR_TEXT_PRIMARY: str = "#F4F6F8"
COLOR_TEXT_SECONDARY: str = "#AEBBC7"
 
# Semantic color lookup used by components that accept a `color` keyword
# (e.g. metric_card) so callers can pass "primary"/"danger"/"warning"/"info"
# instead of repeating hex codes.
SEMANTIC_COLORS: dict[str, str] = {
    "primary": COLOR_PRIMARY,
    "danger": COLOR_DANGER,
    "warning": COLOR_WARNING,
    "info": COLOR_INFO,
}
 
 
def resolve_color(color: str) -> str:
    """Resolve a semantic color name ('primary', 'danger', ...) or a raw hex string to a hex color."""
    if color.startswith("#"):
        return color
    return SEMANTIC_COLORS.get(color, COLOR_PRIMARY)
 
 
# --------------------------------------------------------------------------
# LAYOUT TOKENS
# Synced to match assets/theme.css's :root custom properties exactly.
# SIDEBAR_WIDTH_EXPANDED_PX / SIDEBAR_WIDTH_COLLAPSED_PX and the
# inject_sidebar_width() function that used them have been removed: the
# sidebar has been a single fixed width (--sidebar-width in theme.css)
# with no collapse/expand behavior since sidebar.py stopped calling that
# function, and its docstring referenced a "--sidebar-transition" CSS
# variable that no longer exists anywhere in theme.css.
# --------------------------------------------------------------------------
BORDER_RADIUS_PX: int = 10
CARD_PADDING_PX: int = 16
SIDEBAR_WIDTH_PX: int = 240
HEADER_HEIGHT_PX: int = 72
 
FONT_FAMILY: str = '"Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
 
# --------------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------------
FRONTEND_DIR: Path = Path(__file__).resolve().parent.parent
ASSETS_DIR: Path = FRONTEND_DIR / "assets"
THEME_CSS_PATH: Path = ASSETS_DIR / "theme.css"
LOGO_PATH: Path = ASSETS_DIR / "drdo_logo.png"
 
 
def inject_global_theme() -> None:
    """
    Load assets/theme.css and inject it once per page render. Call this
    first thing in app.py (and in every page, if pages are ever split into
    separate files) before rendering any other component.
    """
    try:
        css = THEME_CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        st.warning(f"Theme stylesheet not found at {THEME_CSS_PATH} — using unstyled defaults.")
        return
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
 
 
def css_marker(class_name: str) -> None:
    """
    Render an invisible marker div immediately before a widget so theme.css
    can target that specific widget via an adjacent-sibling selector
    (e.g. `.medevac-nav-active-marker + div[data-testid="stButton"] button`).
    This is the one reliable, Streamlit-version-stable way to style
    individual st.button calls differently from one another, since
    st.button does not accept a custom CSS class itself.
    """
    st.markdown(f'<div class="{class_name}"></div>', unsafe_allow_html=True)