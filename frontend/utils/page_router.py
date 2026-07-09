"""
page_router.py

Single source of truth mapping each sidebar nav name to that page's
render() function. This exists so app.py never grows an if/elif chain as
pages are added — it just looks up the current page name here and calls
whatever it maps to.

The nav names here MUST stay in sync with components/sidebar.py's
NAV_ITEMS list — that list is what the person actually clicks, this
dictionary is what turns their click into rendered content.
"""

from typing import Callable

from app_pages import (
    dashboard,
    simulation,
    facilities,
    resources,
    patients,
    analytics,
)

PAGE_ROUTES: dict[str, Callable[[], None]] = {
    "Dashboard": dashboard.render,
    "Simulation": simulation.render,
    "Facilities": facilities.render,
    "Resources": resources.render,
    "Patients": patients.render,
    "Analytics": analytics.render,
}


def render_page(page_name: str) -> None:
    """
    Render whichever page is currently selected in the sidebar.

    Falls back to the Dashboard page if page_name isn't a recognized key
    (defensive only — this should not happen as long as sidebar.py's
    NAV_ITEMS and PAGE_ROUTES above are kept in sync).
    """
    render_fn = PAGE_ROUTES.get(page_name, dashboard.render)
    render_fn()
