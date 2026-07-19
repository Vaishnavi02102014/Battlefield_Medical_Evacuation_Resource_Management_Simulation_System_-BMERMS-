"""
resources_service.py
 
Service layer for the Resources page. This is the only module
frontend/app_pages/resources.py imports data from; the page itself
contains no direct backend imports and no SQL, mirroring the pattern
used by dashboard_service.py, facilities_service.py, and
patients_service.py.
 
Layering:
 
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
 
Every public function has the same name and return shape resources.py's
rendering code expects. No module-level caching and no
st.session_state writes occur in this file: every function re-queries
the live database on every call, so the page reflects current database
state immediately after a simulation reset
(crud.reset_simulation_data() resets Ambulances/Helicopters/Medical_Teams
back to "Available"/unassigned).
 
Dispatch Timeline — current architectural limitation:
    No historical dispatch event log exists in the schema. Ambulances /
    Helicopters / Medical_Teams store only current status, release_time,
    and assigned_facility; once a unit is released back to "Available",
    any record of when it was dispatched is gone
    (crud.release_ambulance()/release_helicopter() null out
    release_time). Dispatch events are also described in
    st.session_state.mission_log, but that log is not persisted
    (deque(maxlen=200), lives only in the running frontend session, and
    is cleared on every app restart — see
    backend/simulation/mission_log.py), so it is not a suitable source
    for an hourly dispatch-history view. get_dispatch_history() below
    returns [] to reflect that no such history currently exists, rather
    than displaying fabricated figures. resources.py's
    _render_dispatch_timeline() has an empty-state branch ("No dispatch
    activity recorded.") for this case.
 
Import bootstrap note: same pattern as the other three services —
Streamlit only adds frontend/ to sys.path, not the project root, so the
root is added once below before importing backend.*.
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
 
    Combines two existing crud functions: crud.get_all_facilities() (4
    rows) and crud.count_dispatched_teams_for_facility() (one COUNT(*)
    per facility, 4 total queries).
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
    {available, total} per resource type. dispatched = total - available,
    the only two statuses resource_manager.py ever sets on these tables
    (via dispatch_ambulance/dispatch_helicopter or
    release_ambulance/release_helicopter); no code path sets "Under
    Maintenance" today.
 
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
 
    available_teams/deployed_teams wrap
    crud.get_resource_availability_counts(), the same as
    get_fleet_status(). facilities_supported uses
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
    computed from get_fleet_status()/get_medical_team_status() rather
    than a separate query, so it always stays consistent with those.
 
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
# 4. DISPATCH HISTORY — see module docstring: no historical log exists
# ==========================================================================
 
def get_dispatch_history() -> list[dict]:
    """
    Backs the Dispatch Timeline. No historical dispatch event log exists
    in the current schema (see module docstring), so this returns [] to
    reflect that accurately rather than displaying fabricated figures.
    resources.py's _render_dispatch_timeline() renders this as "No
    dispatch activity recorded."
 
    Returns
    -------
    list[dict]: always [] until the schema gains a persisted dispatch
    history table.
    """
    return []
 
 
# ==========================================================================
# 5. RESOURCE AVAILABILITY
# ==========================================================================
 
def get_resource_availability() -> list[dict]:
    """
    Compact available/total per resource pool, derived from
    get_fleet_status()/get_medical_team_status() rather than a separate
    query, so it always agrees with those.
 
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
 