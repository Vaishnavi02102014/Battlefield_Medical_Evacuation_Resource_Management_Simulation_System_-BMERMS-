"""
patients_service.py

Service layer for the Patients page. This is the ONLY module
frontend/app_pages/patients.py is permitted to import data from — the
page itself must contain no direct backend imports and no SQL, exactly
mirroring the pattern established by dashboard_service.py and
facilities_service.py.

Required layering (unchanged):

    Patients Page (patients.py)
            |
            v
    frontend/services/patients_service.py   <- this file
            |
            v
    backend/database/crud.py
            |
            v
    SQLite (bmerms.db)

Every public function here has the EXACT same name, argument signature,
and return shape (plain dict / list[dict] / str / int / None — never a
dataclass instance) as the mock function it replaces from
data/patients_mock_data.py. patients.py's rendering code (bracket access
like c["severity"], queue_entry["waiting_time"], treatment["current_status"])
is therefore completely unchanged — only the import line moves.

No module-level caching / no st.session_state writes: every function
re-queries the live database on every call. This is deliberate so the
page keeps reflecting the current database state immediately after a
simulation reset (crud.reset_simulation_data()) or any other write,
with nothing to invalidate — the "reset architecture" stays intact
because nothing here caches anything.

--------------------------------------------------------------------------
Backend gap found and fixed (see requirement 10 — flagged before
proposing this change):
--------------------------------------------------------------------------
crud.py had NO function returning a casualty's treatment history.
insert_treatment()/complete_treatment() only write; get_due_treatments()
and get_due_return_to_duty() are tick-scoped bulk queries across every
casualty, not a per-casualty lookup — there was no way to answer
"what treatment(s) has casualty CAS-0001 had?" at all. This is a missing
capability, not a naming/shape mismatch, so it could not be worked around
with existing functions. One minimal, read-only function was added to
crud.py, following its existing conventions exactly (parameterized query,
returns list[Treatment] dataclasses, same docstring style):

    get_treatments_for_casualty(casualty_id: str) -> list[Treatment]

No schema change, no write, ordered by treatment_start DESC. See that
function in crud.py for the exact SQL.

--------------------------------------------------------------------------
Known value-space mismatches (flagged, NOT silently patched here) —
these live in patients.py's own page-local constants, which this task's
scope does not permit editing (only its import line changes), so real
data will render through them exactly as-is:
--------------------------------------------------------------------------
1. STATUS_ACCENT (patients.py) only has color entries for "Waiting",
   "In Treatment", "Recovered", "Returned to Duty". The real schema's
   CASUALTY_STATUSES are "Waiting", "Being Evacuated", "Under Treatment",
   "Transferred", "Recovered", "Returned To Duty" (backend/utils/
   constants.py). "Under Treatment", "Returned To Duty", "Being
   Evacuated", and "Transferred" have no matching key in STATUS_ACCENT,
   so those statuses will render with the default "info" accent instead
   of their intended color. Nothing breaks — it's a cosmetic
   under-coloring, not an error.
2. PRIORITY_ACCENT / PRIORITY_ORDER (patients.py) only define P1/P2/P3.
   The real severity->priority mapping (backend/utils/constants.py,
   SEVERITY_CONFIG) also produces P0 for Critical casualties. A P0
   casualty will render with the default "info" priority badge color
   (cosmetic), AND will sort as priority rank 99 — i.e. LAST, not
   first — in every Priority-sorted view and in
   _default_priority_casualty()'s fallback selection. This is a real
   functional regression once live Critical/P0 casualties exist (the
   live database currently has 8). Flagging this clearly: fixing it
   requires editing patients.py's PRIORITY_ACCENT/PRIORITY_ORDER dicts
   (adding a "P0" entry to each), which is outside this task's
   "imports only" scope for patients.py — recommend a fast follow-up.
3. evacuation_mode values differ cosmetically: the mock used "Air"/
   "Ground"; the real schema uses "Foot"/"Ambulance"/"Helicopter"
   (backend/utils/constants.py, EVACUATION_MODES). patients.py just
   displays this value as plain text with no color map, so this is
   purely a label difference, not a bug.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

# --------------------------------------------------------------------------
# sys.path bootstrap (same pattern as dashboard_service.py / facilities_service.py)
# --------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../DRDO
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.database import crud  # noqa: E402

# Real Treatments.current_status values (see backend/database/init_db.py's
# schema and crud.insert_treatment/complete_treatment) — used only to pick
# the in-progress treatment correctly; see get_latest_treatment() below.
_TREATMENT_STATUS_IN_PROGRESS = "Under Treatment"


# ==========================================================================
# CASUALTIES
# ==========================================================================

def get_all_casualties() -> list[dict]:
    """
    Every casualty in the database, unfiltered — backs the Patient
    Registry (before search/filter/sort), the KPI row, and the Patient
    Distribution donut, all of which need the full dataset per
    patients.py's own docstring ("KPI Summary and Patient Distribution
    ... both still read from the full, unfiltered dataset").

    Wraps crud.get_casualties_filtered() called with no arguments: every
    filter parameter defaults to None, so the underlying query is exactly
    "SELECT * FROM Casualties ... " with no WHERE narrowing — i.e. "all
    casualties" is expressed by the *absence* of filters, not a separate
    "get everything" function. (Deliberately not
    crud.get_recent_casualties(), which defaults to limit=50 and would
    silently truncate the registry/KPIs/distribution once the database
    holds more than 50 casualties — it already does today.)

    Returns
    -------
    list[dict], one per casualty, with the same keys as the Casualty
    dataclass (casualty_id, incident_id, battle_sector, grid_x, grid_y,
    soldier_unit, rank, age, injury_type, severity, priority,
    arrival_time, assigned_facility, bed_id, queue_position,
    evacuation_mode, evacuation_arrival_time, medical_officer, status,
    expected_recovery, return_to_duty).
    """
    casualties = crud.get_casualties_filtered()
    return [asdict(c) for c in casualties]


# ==========================================================================
# FACILITIES
# ==========================================================================

def get_facility_name(facility_id: Optional[int]) -> Optional[str]:
    """
    Resolve a facility_id to its display name (e.g. "Regimental Aid
    Post"). Returns None for a None facility_id (unassigned casualty) or
    an id that doesn't match any facility.

    Wraps crud.get_facility_by_id().
    """
    if facility_id is None:
        return None
    facility = crud.get_facility_by_id(facility_id)
    return facility.facility_name if facility else None


def get_all_facility_names() -> list[str]:
    """
    All facility display names, in facility_id order (RAP, ADS, HMV,
    FDC) — backs the Patient Registry's facility filter dropdown.

    Wraps crud.get_all_facilities().
    """
    return [f.facility_name for f in crud.get_all_facilities()]


# ==========================================================================
# BEDS
# ==========================================================================

def get_bed_number(bed_id: Optional[int]) -> Optional[int]:
    """
    Resolve a bed_id to its bed_number for display (e.g. Bed ID 205 ->
    "22"). Returns None for a None bed_id (not currently admitted to a
    bed) or an id that doesn't match any bed.

    There is no crud function that looks up one bed by bed_id alone
    (only get_beds_for_facility(facility_id), get_available_bed
    (facility_id), and the write-side occupy_bed/release_bed) — and the
    original mock function's signature only takes bed_id, with no
    facility context available at the call site to narrow the search.
    Since Beds is a small table (roughly 820 rows across the 4 fixed
    facilities), this is answered correctly using ONLY existing crud
    functions — no backend change was needed here, unlike the treatment
    history gap above: scan each facility's beds via
    crud.get_beds_for_facility() until the matching bed_id is found.
    """
    if bed_id is None:
        return None
    for facility in crud.get_all_facilities():
        for bed in crud.get_beds_for_facility(facility.facility_id):
            if bed.bed_id == bed_id:
                return bed.bed_number
    return None


# ==========================================================================
# WAITING QUEUE
# ==========================================================================

def get_queue_entry(casualty_id: str) -> Optional[dict]:
    """
    The Waiting_Queue row for one casualty, if they're currently
    queued. Returns None if they aren't (e.g. already admitted to a
    bed, or not yet routed).

    Wraps crud.get_all_queues() (there is no per-casualty queue lookup
    in crud.py) and filters in Python — the Waiting_Queue table is small
    (0 rows in the current database; bounded by facility capacity even
    under load), so this is a single cheap query.

    Returns
    -------
    dict (queue_id, facility_id, casualty_id, priority, arrival_time,
    waiting_time) or None.
    """
    entry = next(
        (q for q in crud.get_all_queues() if q.casualty_id == casualty_id),
        None,
    )
    return asdict(entry) if entry else None


# ==========================================================================
# TREATMENTS
# ==========================================================================

def get_latest_treatment(casualty_id: str) -> Optional[dict]:
    """
    The casualty's current in-progress treatment if one exists, else
    their most recent treatment by treatment_start. Backs the "Current
    Treatment" block in the Patient Detail panel.

    Wraps the newly-added crud.get_treatments_for_casualty(), which
    already returns rows ordered most-recent-first (treatment_start
    DESC), so "most recent" is simply treatments[0].

    Note on "in progress" detection: the original mock used
    `treatment_end is None` as its in-progress signal. That convention
    does not hold in the real schema — crud.insert_treatment() always
    writes a (pre-computed, expected) treatment_end at insert time, so
    treatment_end is never actually NULL for a real row; the real
    in-progress signal is current_status == "Under Treatment" (flipped
    to "Completed" by crud.complete_treatment() when the simulation
    processes it). This function uses that correct, schema-validated
    check instead — this is an internal implementation detail of this
    service function, not a change to patients.py, which only ever reads
    the returned dict's keys (unchanged: treatment_start, treatment_end,
    treatment_duration, current_status).

    Returns
    -------
    dict (treatment_id, casualty_id, facility_id, treatment_start,
    treatment_end, treatment_duration, current_status) or None if the
    casualty has no treatment records at all.
    """
    treatments = crud.get_treatments_for_casualty(casualty_id)
    if not treatments:
        return None

    in_progress = next(
        (t for t in treatments if t.current_status == _TREATMENT_STATUS_IN_PROGRESS),
        None,
    )
    chosen = in_progress if in_progress is not None else treatments[0]
    return asdict(chosen)