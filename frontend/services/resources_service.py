"""
resources_service.py

Service layer for the Resources page. This is the ONLY module
frontend/app_pages/resources.py is permitted to import data from — the
page itself must contain no direct backend imports and no SQL, exactly
mirroring the pattern established by dashboard_service.py,
facilities_service.py, and patients_service.py.

Required layering (unchanged):

    Resources Page (resources.py)
            |
            v
    frontend/services/resources_service.py   <- this file
            |
            v
    backend/database/crud.py
            |
            v
    SQLite (bmerms.db)

Every public function here has the EXACT same name and return shape as
the mock function it replaces in the old resources.py "MOCK DATA LAYER"
block. resources.py's rendering code is therefore completely unchanged —
only the data functions move from being defined inline in resources.py
to being imported from here.

No crud.py changes were needed for this integration — every widget
except one (see below) is fully answerable with two existing functions:
crud.get_resource_availability_counts() and
crud.count_dispatched_teams_for_facility(). Requirement 12 ("don't
regenerate crud.py unless absolutely necessary") is satisfied trivially:
nothing was added.

No module-level caching / no st.session_state writes: every function
re-queries the live database on every call, so the page reflects the
current database state immediately after a simulation reset
(crud.reset_simulation_data() resets Ambulances/Helicopters/Medical_Teams
back to "Available" / unassigned) — the reset architecture stays intact
because nothing here caches anything.

--------------------------------------------------------------------------
Missing backend support found (flagged per requirement 7, before
proposing any change) — Dispatch Timeline:
--------------------------------------------------------------------------
There is no historical dispatch event log anywhere in the schema.
Ambulances / Helicopters / Medical_Teams only store CURRENT status,
release_time, and assigned_facility — once a vehicle is released back to
"Available", any record of when it was dispatched is gone
(crud.release_ambulance()/release_helicopter() null out release_time).
The only place a dispatch event is ever described at all is
st.session_state.mission_log, which is explicitly non-persisted
(deque(maxlen=200), lives in the frontend, cleared on every app restart)
per backend/simulation/mission_log.py's own docstring — not a backend
data source suitable for an "hourly dispatch history" chart, and adding
a new table to fix this would violate requirement 9 (no schema changes).

No backend change is proposed for this gap: get_dispatch_history() below
returns [] (truthful — no such history exists) rather than continuing to
show fabricated hourly numbers. resources.py's own
_render_dispatch_timeline() already has a graceful empty-state branch
("No dispatch activity recorded.") for an empty list, so this required
zero UI changes. See requirement 11 answer in the integration summary
for the full "live vs. placeholder" widget breakdown.

Import bootstrap note: same pattern as the other three services —
Streamlit only auto-adds frontend/ to sys.path, not the project root, so
the root is added once below before importing backend.*.
"""

from __future__ import annotations

import sys
from pathlib import Path

# --------------------------------------------------------------------------
# sys.path bootstrap (same pattern as dashboard_service.py / facilities_service.py / patients_service.py)
# --------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../DRDO
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.database import crud  # noqa: E402


# ==========================================================================
# Internal helpers
# ==========================================================================

def _facilities_supported_count() -> int:
    """
    Number of distinct facilities currently supported by at least one
    dispatched medical team.

    There is no single crud aggregate for this, but it's fully
    answerable by combining two existing functions — no backend change
    needed: crud.get_all_facilities() (4 rows, cheap) and
    crud.count_dispatched_teams_for_facility() (one COUNT(*) per
    facility, so 4 total queries).
    """
    return sum(
        1
        for facility in crud.get_all_facilities()
        if crud.count_dispatched_teams_for_facility(facility.facility_id) > 0
    )


# ==========================================================================
# 1. FLEET STATUS
# ==========================================================================

def get_fleet_status() -> dict:
    """
    Vehicle fleet counts, mirroring Ambulance.status/Helicopter.status
    ("Available" | "Dispatched").

    Wraps crud.get_resource_availability_counts(), which returns
    {available, total} per resource type. dispatched = total - available
    (the only two statuses ever set on these tables in practice — see
    resource_manager.py, which only ever calls
    dispatch_ambulance/dispatch_helicopter or
    release_ambulance/release_helicopter; nothing ever sets
    "Under Maintenance" today).

    Returns
    -------
    dict:
        {
          "ambulances": {"available": int, "dispatched": int},
          "helicopters": {"available": int, "dispatched": int},
        }
    """
    counts = crud.get_resource_availability_counts()
    ambulances = counts.get("ambulances", {"available": 0, "total": 0})
    helicopters = counts.get("helicopters", {"available": 0, "total": 0})

    return {
        "ambulances": {
            "available": ambulances.get("available", 0),
            "dispatched": max(ambulances.get("total", 0) - ambulances.get("available", 0), 0),
        },
        "helicopters": {
            "available": helicopters.get("available", 0),
            "dispatched": max(helicopters.get("total", 0) - helicopters.get("available", 0), 0),
        },
    }


# ==========================================================================
# 2. MEDICAL TEAM STATUS
# ==========================================================================

def get_medical_team_status() -> dict:
    """
    Mirrors MedicalTeam.status and assigned_facility.

    available_teams/deployed_teams wrap crud.get_resource_availability_counts()
    exactly like get_fleet_status() does. facilities_supported uses
    _facilities_supported_count() above.

    Returns
    -------
    dict: {"available_teams": int, "deployed_teams": int, "facilities_supported": int}
    """
    counts = crud.get_resource_availability_counts()
    teams = counts.get("medical_teams", {"available": 0, "total": 0})
    available = teams.get("available", 0)
    deployed = max(teams.get("total", 0) - available, 0)

    return {
        "available_teams": available,
        "deployed_teams": deployed,
        "facilities_supported": _facilities_supported_count(),
    }


# ==========================================================================
# 3. RESOURCE SUMMARY (KPI row)
# ==========================================================================

def get_resource_summary() -> dict:
    """
    Aggregate counts for the KPI row. resource_utilization_percent is
    computed from get_fleet_status()/get_medical_team_status() (not a
    separate query), so it always stays consistent with those — same
    formula the original mock used, now operating on live data.

    Returns
    -------
    dict with keys: total_ambulances, available_ambulances,
    total_helicopters, available_helicopters, total_medical_teams,
    available_medical_teams, deployed_medical_teams,
    resource_utilization_percent.
    """
    fleet = get_fleet_status()
    teams = get_medical_team_status()

    total_ambulances = fleet["ambulances"]["available"] + fleet["ambulances"]["dispatched"]
    total_helicopters = fleet["helicopters"]["available"] + fleet["helicopters"]["dispatched"]
    total_medical_teams = teams["available_teams"] + teams["deployed_teams"]

    total_units = total_ambulances + total_helicopters + total_medical_teams
    dispatched_units = (
        fleet["ambulances"]["dispatched"] + fleet["helicopters"]["dispatched"] + teams["deployed_teams"]
    )
    utilization_percent = round((dispatched_units / total_units) * 100) if total_units else 0

    return {
        "total_ambulances": total_ambulances,
        "available_ambulances": fleet["ambulances"]["available"],
        "total_helicopters": total_helicopters,
        "available_helicopters": fleet["helicopters"]["available"],
        "total_medical_teams": total_medical_teams,
        "available_medical_teams": teams["available_teams"],
        "deployed_medical_teams": teams["deployed_teams"],
        "resource_utilization_percent": utilization_percent,
    }


# ==========================================================================
# 4. DISPATCH HISTORY — see module docstring: no backend data exists
# ==========================================================================

def get_dispatch_history() -> list[dict]:
    """
    No historical dispatch event log exists anywhere in the backend (see
    module docstring). Returns [] — truthful "no data", not fabricated
    numbers. resources.py's _render_dispatch_timeline() already renders
    this as "No dispatch activity recorded." with no code changes
    required on that end.

    Returns
    -------
    list[dict]: always [] until the backend gains persisted dispatch
    history (would require a new table — out of scope, see module
    docstring).
    """
    return []


# ==========================================================================
# 5. RESOURCE AVAILABILITY
# ==========================================================================

def get_resource_availability() -> list[dict]:
    """
    Compact available/total per resource pool, derived from
    get_fleet_status()/get_medical_team_status() (not a separate query),
    so it always agrees with those — same shape/formula the original
    mock used.

    Returns
    -------
    list[dict], one per resource pool, each {"label": str, "available": int, "total": int}.
    """
    fleet = get_fleet_status()
    teams = get_medical_team_status()
    return [
        {
            "label": "Ambulances",
            "available": fleet["ambulances"]["available"],
            "total": fleet["ambulances"]["available"] + fleet["ambulances"]["dispatched"],
        },
        {
            "label": "Helicopters",
            "available": fleet["helicopters"]["available"],
            "total": fleet["helicopters"]["available"] + fleet["helicopters"]["dispatched"],
        },
        {
            "label": "Medical Teams",
            "available": teams["available_teams"],
            "total": teams["available_teams"] + teams["deployed_teams"],
        },
    ]