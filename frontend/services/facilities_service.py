"""
facilities_service.py

Service layer for the Facilities page. This is the ONLY module
frontend/app_pages/facilities.py is permitted to import data from — the
page itself must contain no direct backend imports and no SQL, exactly
mirroring the pattern established by
frontend/services/dashboard_service.py.

Required layering (unchanged):

    Facilities Page (facilities.py)
            |
            v
    frontend/services/facilities_service.py   <- this file
            |
            v
    backend/database/crud.py  (+ one narrow, documented exception below)
            |
            v
    SQLite (bmerms.db)

Every function here is a thin, read-only wrapper: no business logic is
duplicated from crud.py. Functions call existing CRUD functions and
reshape/label the results into the plain dict shapes the Facilities page
widgets expect.

Import bootstrap note: Streamlit only auto-adds this app's own directory
(frontend/) to sys.path, not the project root. backend/ is a sibling of
frontend/, not a child of it, so the project root must also be on
sys.path before `backend.*` imports will resolve. This is the same
bootstrap already used in dashboard_service.py.

Documented exception — average treatment duration:
    backend/database/crud.py has no existing function that aggregates
    Treatments.treatment_duration per facility (it only has per-casualty
    insert/complete/due-lookup helpers). Per this integration's explicit
    constraints, crud.py and the rest of backend/ must NOT be modified,
    and no files outside this service and facilities.py may be touched.
    Rather than fabricate this figure or silently drop the requirement,
    this file makes one narrow, read-only exception: it imports
    `get_connection` from backend.database.db (the same connection
    helper crud.py itself uses internally) and issues a single
    parameterized SELECT AVG(...) query, scoped to one private helper
    function (_average_treatment_hours). No write, no schema change, and
    no other file does this — every other field on this page still goes
    through crud.py exactly as required.
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

from backend.database import crud  # noqa: E402
from backend.database.db import get_connection  # noqa: E402  (see module docstring exception)
from backend.utils.constants import (  # noqa: E402
    FACILITY_STATUS_OPERATIONAL,
    FACILITY_STATUS_HIGH_LOAD,
    FACILITY_STATUS_CRITICAL,
)

# ==========================================================================
# Internal helpers
# ==========================================================================

def _average_treatment_hours(facility_id: int) -> str:
    """
    Average Treatments.treatment_duration for one facility, formatted for
    display. Returns "N/A" if the facility has no treatment records yet
    (per spec requirement 10) rather than 0 or a fabricated value.

    See the module docstring for why this one query bypasses crud.py.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT AVG(treatment_duration) AS avg_duration FROM Treatments WHERE facility_id = ?",
            (facility_id,),
        ).fetchone()

    avg_duration = row["avg_duration"] if row is not None else None
    if avg_duration is None:
        return "N/A"
    return f"{avg_duration:.1f} hrs"


def _build_facility_record(facility) -> dict:
    """
    Shared mapper from a crud.Facility dataclass to the flat dict shape
    both get_facility_overview() and get_facility_detail() return, so the
    two stay perfectly consistent (same keys, same values) for the same
    facility.

    Field mapping:
        name          <- facility.facility_code
        facility_type <- facility.facility_name
        facility_code <- facility.facility_code
        capacity      <- facility.capacity
        occupied      <- facility.occupied_beds
        queue         <- facility.queue_length     (already maintained by
                                                      crud._recompute_facility_counts,
                                                      no separate query needed)
        avg_treatment <- Treatments.treatment_duration average, see
                          _average_treatment_hours(); "N/A" if none exist
        medical_teams <- crud.count_dispatched_teams_for_facility();
                          0 if none are dispatched
        status        <- facility.facility_status
    """
    return {
        "name": facility.facility_code,
        "facility_type": facility.facility_name,
        "facility_code": facility.facility_code,
        "capacity": facility.capacity,
        "occupied": facility.occupied_beds,
        "queue": facility.queue_length,
        "avg_treatment": _average_treatment_hours(facility.facility_id),
        "medical_teams": crud.count_dispatched_teams_for_facility(
            facility.facility_id
        ),
        "status": facility.facility_status,
    }


# ==========================================================================
# 1. KPI SUMMARY
# ==========================================================================

def get_kpi_summary() -> dict:
    """
    Backs the Facilities page's 6 KPI cards.

    Wraps crud.get_all_facilities() and aggregates in Python — there is
    no separate crud aggregate for facility-level KPIs (unlike the
    Dashboard's crud.get_dashboard_stats()), so this function owns that
    aggregation, over already-fetched Facility rows only (no per-KPI
    query).

    Returns
    -------
    dict with keys:
        total_facilities      : int
        operational_facilities: int   (facility_status == "Operational")
        heavy_load_facilities : int   (facility_status in {"High Load", "Critical"})
        available_beds        : int   (sum of available_beds across facilities)
        occupied_beds         : int   (sum of occupied_beds across facilities)
        waiting_casualties    : int   (sum of queue_length across facilities)
    """
    facilities = crud.get_all_facilities()

    return {
        "total_facilities": len(facilities),
        "operational_facilities": sum(
            1 for f in facilities if f.facility_status == FACILITY_STATUS_OPERATIONAL
        ),
        "heavy_load_facilities": sum(
            1
            for f in facilities
            if f.facility_status in (FACILITY_STATUS_HIGH_LOAD, FACILITY_STATUS_CRITICAL)
        ),
        "available_beds": sum(f.available_beds for f in facilities),
        "occupied_beds": sum(f.occupied_beds for f in facilities),
        "waiting_casualties": sum(f.queue_length for f in facilities),
    }


# ==========================================================================
# 2. FACILITY OVERVIEW
# ==========================================================================

def get_facility_overview() -> list[dict]:
    """
    Backs the Operational Facility Overview table.

    Wraps crud.get_all_facilities() (already ordered by facility_id, i.e.
    RAP, ADS, HMV, FDC) and maps each row through _build_facility_record().

    Returns
    -------
    list[dict], one entry per facility, each with keys:
        name, facility_type, capacity, occupied, queue, avg_treatment,
        medical_teams, status
    (exactly the fields required by spec item 7)
    """
    facilities = crud.get_all_facilities()
    return [_build_facility_record(f) for f in facilities]


# ==========================================================================
# 3. FACILITY DETAIL
# ==========================================================================

def get_facility_detail(facility_name: str) -> Optional[dict]:
    """
    Backs the Facility Detail panel for one selected facility.

    Looks up the facility by its display name (facility_name — the same
    value get_facility_overview() puts in each record's "name" field, and
    what the Facilities page's table selection returns), then maps it
    through the same _build_facility_record() used by the overview, so
    detail and overview are always consistent for the same facility.

    Parameters
    ----------
    facility_name : str
        The facility's display name, e.g. "Regimental Aid Post".

    Returns
    -------
    dict (same shape as one get_facility_overview() entry), or None if
    facility_name is falsy or does not match any known facility.
    """
    if not facility_name:
        return None

    facilities = crud.get_all_facilities()
    facility = next(
        (
            f
            for f in facilities
            if f.facility_code == facility_name
        ),
        None,
    )
    if facility is None:
        return None

    return _build_facility_record(facility)