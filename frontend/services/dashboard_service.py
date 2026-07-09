"""
dashboard_service.py

Service layer for the Dashboard page. This is the ONLY module
frontend/app_pages/dashboard.py is permitted to import data from — the
page itself must contain no direct backend imports and no SQL.

Required layering (unchanged):

    Dashboard Page (dashboard.py)
            |
            v
    frontend/services/dashboard_service.py   <- this file
            |
            v
    backend/database/crud.py  (+ st.session_state, for Mission Log only)
            |
            v
    SQLite (bmerms.db)

Every function here is a thin, read-only wrapper: no SQL is written in
this file, and no business logic is duplicated from crud.py. Functions
only call existing CRUD functions and reshape/label the results into the
plain dict/list shapes the Dashboard widgets expect.

Scope (per integration task): only the five functions below are
implemented. AI Tactical Recommendation and Battlefield Map integration
are explicitly out of scope for this pass and are not touched here.

Import bootstrap note: Streamlit only auto-adds this app's own directory
(frontend/) to sys.path (see frontend/app.py's docstring), not the
project root. backend/ is a sibling of frontend/, not a child of it, so
the project root must also be on sys.path before `backend.*` imports will
resolve. That bootstrap is done once, below, in this file only — no other
frontend file needs to change for this integration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# sys.path bootstrap (see module docstring above)
# --------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../DRDO
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st  # noqa: E402  (import order intentional: after sys.path bootstrap)

from backend.database import crud  # noqa: E402
from backend.utils.constants import FACILITY_ORDER, SEVERITY_LIST  # noqa: E402
try:
    from backend.simulation.mission_log import (
        CATEGORY_INCIDENT,
        CATEGORY_DISPATCH,
        CATEGORY_ADMISSION,
        CATEGORY_QUEUE,
        CATEGORY_RECOVERY,
        CATEGORY_RETURN_TO_DUTY,
        CATEGORY_RESOURCE,
    )
except ImportError:
    CATEGORY_INCIDENT = "Incident"
    CATEGORY_DISPATCH = "Dispatch"
    CATEGORY_ADMISSION = "Admission"
    CATEGORY_QUEUE = "Queue"
    CATEGORY_RECOVERY = "Recovery"
    CATEGORY_RETURN_TO_DUTY = "Return To Duty"
    CATEGORY_RESOURCE = "Resource"


# ==========================================================================
# 1. KPI SUMMARY
# ==========================================================================

def get_kpi_summary() -> dict:
    """
    Backs the 6 KPI cards.

    Wraps crud.get_dashboard_stats() (a single existing aggregate query)
    and relabels it for the Dashboard's KPI row. "Total Soldiers" has been
    replaced with "Total Casualties Processed", backed by
    stats["total_casualties"] — there is no roster/troop-strength table in
    the schema, so this is the only truthful headline count available.

    Returns
    -------
    dict with keys:
        total_casualties_processed : int
        in_treatment               : int
        waiting_in_queue           : int
        recovered                  : int
        returned_to_duty           : int
        active_incidents           : int
    """
    stats = crud.get_dashboard_stats()
    return {
        "total_casualties_processed": stats.get("total_casualties", 0),
        "in_treatment": stats.get("in_treatment", 0),
        "waiting_in_queue": stats.get("waiting_total", 0),
        "recovered": stats.get("recovered", 0),
        "returned_to_duty": stats.get("returned_to_duty", 0),
        "active_incidents": stats.get("active_incidents", 0),
    }


# ==========================================================================
# 2. EVACUATION WORKFLOW
# ==========================================================================

def get_evacuation_workflow() -> list[dict]:
    """
    Backs the Battlefield Evacuation Workflow strip's facility stages
    (RAP -> ADS -> HMV -> FDC). The static "Battlefield" and "Recovery"
    endpoint bookends are structural, not data-backed, and stay in
    dashboard.py.

    Wraps crud.get_all_facilities() and orders the result explicitly
    against backend.utils.constants.FACILITY_ORDER rather than trusting
    row/insertion order.

    Returns
    -------
    list[dict], one entry per facility, each:
        code             : str   e.g. "RAP"
        name             : str   e.g. "RAP" (short code, matches on-screen label)
        facility_name    : str   e.g. "Regimental Aid Post" (full name, optional use)
        occupied         : int
        capacity         : int
        occupancy_label  : str   e.g. "58 / 100"
    """
    facilities = crud.get_all_facilities()
    by_code = {f.facility_code: f for f in facilities}

    stages: list[dict] = []
    for code in FACILITY_ORDER:
        facility = by_code.get(code)
        if facility is None:
            continue
        stages.append(
            {
                "code": facility.facility_code,
                "name": facility.facility_code,
                "facility_name": facility.facility_name,
                "occupied": facility.occupied_beds,
                "capacity": facility.capacity,
                "occupancy_label": f"{facility.occupied_beds} / {facility.capacity}",
            }
        )
    return stages


# ==========================================================================
# 3. ASSET INVENTORY
# ==========================================================================

# Fixed, presentation-only icon lookup for the three known resource types.
# Not derived from the database — matches the icons the mock data used.
_ASSET_ICON_MAP: dict[str, str] = {
    "Ambulances": "◈",
    "Helicopters": "△",
    "Medical Teams": "✚",
}

# (service key in crud.get_resource_availability_counts(), display label)
_ASSET_TYPES: list[tuple[str, str]] = [
    ("ambulances", "Ambulances"),
    ("helicopters", "Helicopters"),
    ("medical_teams", "Medical Teams"),
]


def get_asset_inventory() -> list[dict]:
    """
    Backs the Asset Inventory panel (Ambulances / Helicopters / Medical
    Teams).

    Wraps crud.get_resource_availability_counts(), which returns
    {available, total} per resource type. Per integration spec:
        busy        = total - available
        maintenance = 0 (no status in the schema is ever set to
                      "Under Maintenance" by any simulation/CRUD code
                      today, so this is reported honestly as 0 rather
                      than fabricated)

    Returns
    -------
    list[dict], one entry per resource type, each:
        name        : str   e.g. "Ambulances"
        icon        : str
        available   : int
        busy        : int
        maintenance : int   (always 0, see note above)
        total       : int
    """
    counts = crud.get_resource_availability_counts()

    inventory: list[dict] = []
    for counts_key, label in _ASSET_TYPES:
        data = counts.get(counts_key, {"available": 0, "total": 0})
        available = data.get("available", 0)
        total = data.get("total", 0)
        busy = max(total - available, 0)
        inventory.append(
            {
                "name": label,
                "icon": _ASSET_ICON_MAP.get(label, "■"),
                "available": available,
                "busy": busy,
                "maintenance": 0,
                "total": total,
            }
        )
    return inventory


# ==========================================================================
# 4. TRIAGE SEVERITY DISTRIBUTION
# ==========================================================================

def get_triage_severity_distribution() -> dict:
    """
    Backs the Triage Severity Chart.

    Wraps crud.get_severity_distribution() (already the exact
    {severity: count} shape a chart needs) and fills in any severity from
    the closed SEVERITY_LIST that currently has zero casualties, so the
    chart always renders all four categories instead of only whichever
    ones happen to have rows today.

    Returns
    -------
    dict[str, int], keyed by severity ("Critical", "Serious", "Moderate",
    "Mild"), in that fixed order.
    """
    distribution = crud.get_severity_distribution()
    return {severity: distribution.get(severity, 0) for severity in SEVERITY_LIST}


# ==========================================================================
# 5. MISSION LOG
# ==========================================================================

# Icon lookup keyed on the closed category set defined in
# backend/simulation/mission_log.py, so it stays in sync with the only
# producer of Mission Log entries.
_MISSION_LOG_ICON_MAP: dict[str, str] = {
    CATEGORY_INCIDENT: "▲",
    CATEGORY_DISPATCH: "►",
    CATEGORY_ADMISSION: "✚",
    CATEGORY_QUEUE: "▣",
    CATEGORY_RECOVERY: "✓",
    CATEGORY_RETURN_TO_DUTY: "★",
    CATEGORY_RESOURCE: "◆",
}


def _entry_field(entry, dict_key: str, attr_key: Optional[str] = None):
    """
    Read one field from a Mission Log entry, which may be either a
    MissionLogEntry dataclass instance or a plain dict (both shapes are
    valid producers per mission_log.py / simulation_controller.py).
    """
    attr_key = attr_key or dict_key
    if isinstance(entry, dict):
        return entry.get(dict_key)
    return getattr(entry, attr_key, None)


def get_mission_log(limit: int = 5) -> list[dict]:
    """
    Backs the Mission Log panel.

    Mission Log entries are intentionally NOT persisted to the database
    (see backend/simulation/mission_log.py's own docstring) — they live in
    st.session_state.mission_log, a deque populated by
    SimulationController.run_tick(). This function reads that
    session_state container defensively and returns [] whenever it is
    absent or empty (e.g. before the simulation has produced any activity
    yet), rather than raising.

    Returns
    -------
    list[dict], most-recent-first, each entry:
        time        : str   "HH:MM"
        category    : str
        description : str
        icon        : str
    """
    entries = st.session_state.get("mission_log") if hasattr(st, "session_state") else None
    if not entries:
        return []

    ordered = list(entries)[::-1]  # most recent first

    result: list[dict] = []
    for entry in ordered[:limit]:
        timestamp = _entry_field(entry, "timestamp") or ""
        category = _entry_field(entry, "category") or ""
        message = _entry_field(entry, "message", "message") or _entry_field(entry, "description")

        time_label = timestamp.split(" ")[-1] if timestamp else ""

        result.append(
            {
                "time": time_label,
                "category": category,
                "description": message or "",
                "icon": _MISSION_LOG_ICON_MAP.get(category, "•"),
            }
        )
    return result