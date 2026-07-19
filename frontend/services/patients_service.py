"""
patients_service.py
 
Service layer for the Patients page. This is the only module
frontend/app_pages/patients.py imports data from; the page itself
contains no direct backend imports and no SQL, mirroring the pattern
used by dashboard_service.py and facilities_service.py.
 
Layering:
 
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
 
Every public function returns a plain dict / list[dict] / str / int /
None (never a dataclass instance), matching the field names patients.py
reads via bracket access (e.g. c["severity"], queue_entry["waiting_time"],
treatment["current_status"]).
 
No module-level caching and no st.session_state writes occur in this
file: every function re-queries the live database on each call, so the
page reflects current database state immediately after any write,
including a simulation reset (crud.reset_simulation_data()).
 
crud.py includes get_treatments_for_casualty(casualty_id), a read-only,
parameterized lookup ordered by treatment_start DESC, used by
get_latest_treatment() below.
 
1. STATUS_ACCENT (patients.py) defines colors only for "Waiting", "In
   Treatment", "Recovered", "Returned to Duty". The schema's
   CASUALTY_STATUSES also include "Under Treatment", "Returned To Duty",
   "Being Evacuated", and "Transferred" (backend/utils/constants.py),
   none of which have a matching key, so those statuses render with the
   default "info" accent instead of a status-specific color. This is a
   cosmetic limitation, not a functional error.
2. PRIORITY_ACCENT / PRIORITY_ORDER (patients.py) define only P1/P2/P3.
   The severity-to-priority mapping in backend/utils/constants.py
   (SEVERITY_CONFIG) also produces P0 for Critical casualties. A P0
   casualty currently renders with the default "info" priority badge
   color, and sorts as priority rank 99 (last) in every priority-sorted
   view, including _default_priority_casualty()'s fallback selection.
   This is a functional defect: Critical/P0 casualties are sorted to the
   back of priority views instead of the front. It is present in the
   live data today and is not limited to any particular record count.
   Fixing it requires adding a "P0" entry to both dicts in patients.py.
3. evacuation_mode values differ cosmetically from the labels
   patients.py's UI was originally built around: the schema's
   EVACUATION_MODES are "Foot"/"Ambulance"/"Helicopter"
   (backend/utils/constants.py). patients.py displays this value as
   plain text with no color map, so this is a label difference only.
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
 
# Real Treatments.current_status value that marks an in-progress
# treatment (see backend/database/init_db.py's schema and
# crud.insert_treatment/complete_treatment) — used by
# get_latest_treatment() below to pick the active treatment correctly.
_TREATMENT_STATUS_IN_PROGRESS = "Under Treatment"
 
 
# ==========================================================================
# CASUALTIES
# ==========================================================================
 
def get_all_casualties() -> list[dict]:
    """
    Every casualty in the database, unfiltered. Backs the Patient
    Registry (before search/filter/sort), the KPI row, and the Patient
    Distribution donut, which all read from the full dataset.
 
    Wraps crud.get_casualties_filtered() with no arguments, so every
    filter parameter defaults to None and the underlying query returns
    all casualties with no WHERE narrowing. This deliberately does not
    use crud.get_recent_casualties(), which defaults to limit=50 and
    would truncate the registry/KPIs/distribution once the database
    holds more than 50 casualties.
 
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
    Resolves a facility_id to its display name (e.g. "Regimental Aid
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
    FDC). Backs the Patient Registry's facility filter dropdown.
 
    Wraps crud.get_all_facilities().
    """
    return [f.facility_name for f in crud.get_all_facilities()]
 
 
# ==========================================================================
# BEDS
# ==========================================================================
 
def get_bed_number(bed_id: Optional[int]) -> Optional[int]:
    """
    Resolves a bed_id to its bed_number for display (e.g. bed ID 205 ->
    "22"). Returns None for a None bed_id (not currently admitted to a
    bed) or an id that doesn't match any bed.
 
    There is no single crud function that looks up one bed by bed_id
    alone, only get_beds_for_facility(facility_id),
    get_available_bed(facility_id), and the write-side occupy_bed/
    release_bed. Since Beds is a small table (roughly 820 rows across
    the 4 fixed facilities), this scans each facility's beds via
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
    The Waiting_Queue row for one casualty, if they're currently queued.
    Returns None if they aren't (e.g. already admitted to a bed, or not
    yet routed).
 
    Wraps crud.get_all_queues() (there is no per-casualty queue lookup in
    crud.py) and filters in Python; the Waiting_Queue table is small and
    bounded by facility capacity even under load, so this is a cheap
    query.
 
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
 
    Wraps crud.get_treatments_for_casualty(), which returns rows ordered
    most-recent-first (treatment_start DESC), so "most recent" is
    treatments[0].
 
    In-progress detection uses current_status == "Under Treatment"
    (flipped to "Completed" by crud.complete_treatment() once the
    simulation processes it), since crud.insert_treatment() always
    writes a pre-computed treatment_end at insert time, so treatment_end
    is never actually null for a real row.
 
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