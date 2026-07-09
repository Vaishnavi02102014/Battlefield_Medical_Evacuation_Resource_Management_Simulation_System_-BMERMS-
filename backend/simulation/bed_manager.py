"""
bed_manager.py

Responsible ONLY for allocating and releasing beds, and promoting the next
waiting casualty into a freed bed. Talks to the database via database/crud.py
(this is the business-logic layer sitting on top of persistence, per the
approved architecture — simulation modules are allowed to call crud.py;
they must never write raw SQL themselves).
"""

from __future__ import annotations
from datetime import timedelta
from typing import Optional

from backend.database import crud
from backend.simulation.simulation_clock import SimulationClock
from backend.utils.constants import MEDICAL_TEAM_TREATMENT_REDUCTION_PER_TEAM, MEDICAL_TEAM_MAX_TREATMENT_REDUCTION


def _effective_treatment_hours(facility_id: int, base_hours: float) -> float:
    """
    Apply the dispatched-medical-team speed bonus to a facility's nominal
    treatment duration. Each dispatched team at this facility shaves a
    percentage off treatment time (capped), representing added hands-on-deck
    - a real, measurable effect rather than only a status flag on the team.
    """
    team_count = crud.count_dispatched_teams_for_facility(facility_id)
    reduction = min(team_count * MEDICAL_TEAM_TREATMENT_REDUCTION_PER_TEAM, MEDICAL_TEAM_MAX_TREATMENT_REDUCTION)
    return base_hours * (1 - reduction)


def assign_or_queue(
    facility_id: int,
    casualty_id: str,
    priority: str,
    arrival_time_str: str,
    treatment_duration_hours: float,
    clock: SimulationClock,
) -> dict:
    """
    Try to seat a casualty immediately. If a bed is free, occupy it, start a
    Treatment record, and mark the casualty Under Treatment. If not, put the
    casualty in that facility's waiting queue and mark them Waiting.

    Treatment duration is adjusted by any dispatched medical teams at this
    facility (see _effective_treatment_hours) before computing the release
    time, so surge staffing genuinely speeds throughput and indirectly
    shortens queue delay - not just a cosmetic status change.

    Returns a small dict describing what happened, used by decision_engine
    to build the Mission Log entry.
    """
    bed = crud.get_available_bed(facility_id)

    if bed is not None:
        effective_hours = _effective_treatment_hours(facility_id, treatment_duration_hours)
        release_time = clock.current_time + timedelta(hours=effective_hours)
        release_time_str = release_time.strftime("%Y-%m-%d %H:%M")

        crud.occupy_bed(bed.bed_id, casualty_id, clock.formatted_datetime(), release_time_str)
        crud.update_casualty_facility_and_bed(casualty_id, facility_id, bed.bed_id, "Under Treatment")
        crud.insert_treatment(
            casualty_id=casualty_id,
            facility_id=facility_id,
            treatment_start=clock.formatted_datetime(),
            treatment_end=release_time_str,
            treatment_duration=round(effective_hours, 2),
        )
        return {"status": "Under Treatment", "bed_id": bed.bed_id, "bed_number": bed.bed_number}

    crud.enqueue_casualty(facility_id, casualty_id, priority, arrival_time_str)
    crud.update_casualty_facility_and_bed(casualty_id, facility_id, None, "Waiting")
    return {"status": "Waiting", "bed_id": None, "bed_number": None}


def release_bed_and_promote(bed_id: int, facility_id: int, clock: SimulationClock) -> Optional[dict]:
    """
    Free a bed, then immediately pull the highest-priority waiting casualty
    (if any) for that facility into it.

    Returns a dict describing the promoted casualty, or None if the queue
    was empty.
    """
    crud.release_bed(bed_id)

    next_entry = crud.dequeue_next_casualty(facility_id)
    if next_entry is None:
        return None

    casualty = crud.get_casualty(next_entry.casualty_id)
    facility = crud.get_facility_by_id(facility_id)
    if casualty is None or facility is None:
        return None

    result = assign_or_queue(
        facility_id=facility_id,
        casualty_id=casualty.casualty_id,
        priority=casualty.priority,
        arrival_time_str=next_entry.arrival_time,
        treatment_duration_hours=facility.treatment_duration_hours,
        clock=clock,
    )
    return {"casualty_id": casualty.casualty_id, "facility_code": facility.facility_code, **result}
