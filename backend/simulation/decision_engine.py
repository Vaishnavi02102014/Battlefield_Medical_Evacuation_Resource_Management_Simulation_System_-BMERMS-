"""
decision_engine.py

Sits between casualty generation and bed allocation in the hierarchy:

    Scenario -> Operation -> Incident -> Casualty -> Decision Engine
    -> Treatment -> Recovery -> Return To Duty

For each generated casualty, the Decision Engine:
    1. Applies the fixed severity -> priority -> facility mapping.
    2. Dispatches an appropriate transport resource (resource_manager) and
       computes how long that transport actually takes.
    3. Persists the casualty with status "Being Evacuated" and an
       evacuation_arrival_time — they do NOT occupy a bed or queue slot
       until that transit time has actually elapsed. This is what makes
       resource dispatch affect the simulation's timing, rather than only
       flip a status flag on the vehicle.
    4. Once transit time elapses (process_arrived_evacuations, called every
       tick by simulation_controller), hands off to bed_manager to seat the
       casualty or queue them.

The severity -> facility mapping is a fixed rule from the specification and
must never be changed here.
"""

from __future__ import annotations
from dataclasses import dataclass
import random

from backend.database import crud
from backend.simulation.casualty_generator import CasualtyDraft
from backend.simulation.simulation_clock import SimulationClock
from backend.simulation import bed_manager, resource_manager
from backend.simulation.mission_log import MissionLogEntry, make_entry, CATEGORY_DISPATCH, CATEGORY_ADMISSION, CATEGORY_QUEUE
from backend.utils.constants import SEVERITY_CONFIG


@dataclass
class DecisionResult:
    casualty_id: str
    severity: str
    priority: str
    facility_code: str
    evacuation_mode: str | None
    status: str          # "Being Evacuated" at creation time
    log_entry: MissionLogEntry


def process_casualty(
    draft: CasualtyDraft,
    incident_id: str,
    clock: SimulationClock,
    rng: random.Random,
) -> DecisionResult:
    """
    Route one generated casualty through triage and transport dispatch.
    The casualty is persisted as "Being Evacuated" with an
    evacuation_arrival_time; bed/queue placement happens later, once that
    transit time elapses (see process_arrived_evacuations).
    """
    severity_rule = SEVERITY_CONFIG[draft.severity]
    priority = severity_rule["priority"]
    facility_code = severity_rule["facility_code"]

    facility = crud.get_facility_by_code(facility_code)
    if facility is None:
        raise RuntimeError(f"Facility code '{facility_code}' not found — database not seeded correctly.")

    casualty_id = crud.get_next_casualty_id()
    arrival_time_str = draft.arrival_time.strftime("%Y-%m-%d %H:%M")

    transport_result = resource_manager.dispatch_transport(
        casualty_id=casualty_id,
        severity=draft.severity,
        facility_code=facility_code,
        clock=clock,
        casualty_arrival_time=draft.arrival_time,
    )

    crud.insert_casualty(
        {
            "casualty_id": casualty_id,
            "incident_id": incident_id,
            "battle_sector": draft.battle_sector,
            "grid_x": draft.grid_x,
            "grid_y": draft.grid_y,
            "soldier_unit": draft.soldier_unit,
            "rank": draft.rank,
            "age": draft.age,
            "injury_type": draft.injury_type,
            "severity": draft.severity,
            "priority": priority,
            "arrival_time": arrival_time_str,
            "assigned_facility": facility.facility_id,
            "bed_id": None,
            "queue_position": None,
            "medical_officer": None,
            "evacuation_mode": transport_result.evacuation_mode,
            "evacuation_arrival_time": transport_result.evacuation_arrival_time,
            "status": transport_result.status,
            "expected_recovery": None,
            "return_to_duty": None,
        }
    )

    if transport_result.dispatched:
        resource_manager.attach_casualty_to_resource(
            transport_result.evacuation_mode,
            transport_result.resource_id,
            casualty_id,
        )

    if transport_result.dispatched:
        log_entry = make_entry(
            timestamp=clock.formatted_datetime(),
            category=CATEGORY_DISPATCH,
            message=(
                f"{casualty_id} ({draft.severity}, {priority}) picked up by "
                f"{transport_result.evacuation_mode}, en route to {facility_code} "
                f"(ETA {transport_result.transit_minutes} min)"
            ),
            facility=facility_code,
            severity=draft.severity,
        )
    else:
        log_entry = make_entry(
            timestamp=clock.formatted_datetime(),
            category=CATEGORY_DISPATCH,
            message=(
                f"{casualty_id} ({draft.severity}, {priority}) awaiting transport to "
                f"{facility_code} - no vehicle available, queued"
            ),
            facility=facility_code,
            severity=draft.severity,
        )

    return DecisionResult(
        casualty_id=casualty_id,
        severity=draft.severity,
        priority=priority,
        facility_code=facility_code,
        evacuation_mode=transport_result.evacuation_mode,
        status=transport_result.status,
        log_entry=log_entry,
    )


def process_arrived_evacuations(clock: SimulationClock) -> list[MissionLogEntry]:
    """
    Find every "Being Evacuated" casualty whose transit time has elapsed and
    hand them off to bed_manager for seating or queueing. Called every tick
    by simulation_controller — this is where transit time actually takes
    effect on the simulation, not at dispatch time.
    """
    entries: list[MissionLogEntry] = []
    for casualty in crud.get_due_evacuations(clock.formatted_datetime()):
        facility = crud.get_facility_by_id(casualty.assigned_facility)
        if facility is None:
            continue

        outcome = bed_manager.assign_or_queue(
            facility_id=facility.facility_id,
            casualty_id=casualty.casualty_id,
            priority=casualty.priority,
            arrival_time_str=casualty.arrival_time,
            treatment_duration_hours=facility.treatment_duration_hours,
            clock=clock,
        )

        if outcome["status"] == "Under Treatment":
            entries.append(
                make_entry(
                    timestamp=clock.formatted_datetime(),
                    category=CATEGORY_ADMISSION,
                    message=f"{casualty.casualty_id} arrived at {facility.facility_code}, admitted to bed {outcome['bed_number']}",
                    facility=facility.facility_code,
                    severity=casualty.severity,
                )
            )
        else:
            entries.append(
                make_entry(
                    timestamp=clock.formatted_datetime(),
                    category=CATEGORY_QUEUE,
                    message=f"{casualty.casualty_id} arrived at {facility.facility_code}, queued (no beds available)",
                    facility=facility.facility_code,
                    severity=casualty.severity,
                )
            )
    return entries

