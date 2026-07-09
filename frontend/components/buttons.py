"""
buttons.py

Reusable, themed button components. All three variants wrap Streamlit's
native st.button (so click handling, keys, and on_click callbacks all work
normally) — they only apply consistent theme styling on top, via CSS rules
already declared in assets/theme.css.

Primary and Secondary use st.button's built-in `type` parameter ("primary"/
"secondary"), which Streamlit already renders with distinct DOM attributes
we re-skin in CSS. Danger has no native third `type`, so it's themed via the
css_marker() adjacent-sibling trick (see utils/theme.py).
"""

from __future__ import annotations
from typing import Any, Callable, Optional
import streamlit as st

from utils.theme import css_marker


def primary_button(
    label: str,
    key: Optional[str] = None,
    on_click: Optional[Callable] = None,
    use_container_width: bool = True,
    **kwargs: Any,
) -> bool:
    """Themed primary action button (military-green fill). Returns True on the click that triggers a rerun."""
    return st.button(
        label, key=key, type="primary", on_click=on_click,
        use_container_width=use_container_width, **kwargs,
    )


def secondary_button(
    label: str,
    key: Optional[str] = None,
    on_click: Optional[Callable] = None,
    use_container_width: bool = True,
    **kwargs: Any,
) -> bool:
    """Themed secondary action button (outlined, neutral)."""
    return st.button(
        label, key=key, type="secondary", on_click=on_click,
        use_container_width=use_container_width, **kwargs,
    )


def danger_button(
    label: str,
    key: Optional[str] = None,
    on_click: Optional[Callable] = None,
    use_container_width: bool = True,
    **kwargs: Any,
) -> bool:
    """Themed danger/destructive-action button (red fill). Use for irreversible or high-severity actions."""
    css_marker("medevac-danger-marker")
    return st.button(
        label, key=key, type="secondary", on_click=on_click,
        use_container_width=use_container_width, **kwargs,
    )
