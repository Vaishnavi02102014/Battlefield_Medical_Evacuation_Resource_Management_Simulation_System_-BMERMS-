"""
resource_manager.py

Responsible for the three trackable resource pools: Ambulances, Helicopters,
Medical Teams.

Vehicle dispatch model (v1, deliberately simple): dispatching an ambulance
or helicopter holds it "Dispatched" for a fixed transit duration
(utils.constants.EVACUATION_TRANSIT_MINUTES) representing a pickup-and-return
round trip, then it is automatically released back to the available pool.
This avoids modeling full vehicle routing while still making fleet
availability fluctuate meaningfully on the dashboard.

Medical team model (v1): when a facility's waiting queue grows past a surge
threshold, dispatch one available medical team to that facility. When the
queue drops back below half the threshold, release one dispatched team from
that facility. This is a light-touch resource-management signal, not a
detailed staffing simulation.
"""

from __future__ import annotations
from datetime import timedelta
import random

from backend.database import crud
from backend.simulation.simulation_clock import SimulationClock
from backend.simulation.mission_log import MissionLogEntry, make_entry, CATEGORY_RESOURCE
from backend.utils.constants import EVACUATION_TRANSIT_MINUTES

SURGE_QUEUE_THRESHOLD: int = 10
SURGE_RELEASE_THRESHOLD: int = 4


def dispatch_transport(
    severity: str,
    clock: SimulationClock,
    casualty_arrival_time,
    rng: random.Random,
) -> tuple[str, int | None, int]:
    """
    Choose and dispatch a transport resource appropriate to casualty severity.

    Critical / Serious -> prefer Helicopter, fall back to Ambulance, fall back to Foot.
    Moderate           -> prefer Ambulance, fall back to Foot.
    Mild               -> mostly Foot, occasionally Ambulance if one is idle.

    Returns (evacuation_mode, resource_id_or_None, transit_minutes). transit_minutes
    is the simulated time the casualty will take to reach the assigned facility -
    this is what actually gates when they occupy a bed (see decision_engine.py),
    not merely a status flag on the vehicle. The resource is linked to its
    casualty separately (decision_engine calls attach_casualty_to_* after the
    casualty row exists, to satisfy the foreign key).
    """
    if severity in ("Critical", "Serious"):
        heli = crud.get_available_helicopter()
        if heli is not None:
            transit = EVACUATION_TRANSIT_MINUTES["Helicopter"]
            release_time = casualty_arrival_time + timedelta(minutes=transit)
            crud.dispatch_helicopter(
                heli.helicopter_id,
                release_time.strftime("%Y-%m-%d %H:%M")
            )
            return "Helicopter", heli.helicopter_id, transit

        amb = crud.get_available_ambulance()
        if amb is not None:
            transit = EVACUATION_TRANSIT_MINUTES["Ambulance"]
            release_time = casualty_arrival_time + timedelta(minutes=transit)
            crud.dispatch_ambulance(
                amb.ambulance_id,
                release_time.strftime("%Y-%m-%d %H:%M")
            )
            return "Ambulance", amb.ambulance_id, transit

        return "Foot", None, EVACUATION_TRANSIT_MINUTES["Foot"]

    if severity == "Moderate":
        amb = crud.get_available_ambulance()
        if amb is not None:
            transit = EVACUATION_TRANSIT_MINUTES["Ambulance"]
            release_time = casualty_arrival_time + timedelta(minutes=transit)
            crud.dispatch_ambulance(
                amb.ambulance_id,
                release_time.strftime("%Y-%m-%d %H:%M")
            )
            return "Ambulance", amb.ambulance_id, transit
        return "Foot", None, EVACUATION_TRANSIT_MINUTES["Foot"]

    # Mild: occasional ambulance use if idle capacity exists, otherwise foot.
    if rng.random() < 0.2:
        amb = crud.get_available_ambulance()
        if amb is not None:
            transit = EVACUATION_TRANSIT_MINUTES["Ambulance"]
            release_time = casualty_arrival_time + timedelta(minutes=transit)
            crud.dispatch_ambulance(
                amb.ambulance_id,
                release_time.strftime("%Y-%m-%d %H:%M")
            )
            return "Ambulance", amb.ambulance_id, transit
    return "Foot", None, EVACUATION_TRANSIT_MINUTES["Foot"]


def attach_casualty_to_resource(evacuation_mode: str, resource_id: int | None, casualty_id: str) -> None:
    """Link a just-dispatched resource to the casualty it's carrying, once that casualty row exists."""
    if resource_id is None:
        return
    if evacuation_mode == "Helicopter":
        crud.attach_casualty_to_helicopter(resource_id, casualty_id)
    elif evacuation_mode == "Ambulance":
        crud.attach_casualty_to_ambulance(resource_id, casualty_id)


def release_due_transport(clock: SimulationClock) -> None:
    """Return any ambulance/helicopter whose transit time has elapsed to the available pool."""
    current_time_str = clock.formatted_datetime()
    for ambulance in crud.get_due_ambulances(current_time_str):
        crud.release_ambulance(ambulance.ambulance_id)
    for helicopter in crud.get_due_helicopters(current_time_str):
        crud.release_helicopter(helicopter.helicopter_id)


def manage_medical_team_surge(facility_id: int, queue_length: int, clock: SimulationClock) -> MissionLogEntry | None:
    """
    Dispatch or release a medical team for one facility based on its queue
    length. Dispatched teams measurably speed up treatment at that facility
    (see bed_manager._effective_treatment_hours) — this is not a cosmetic
    status flag. Returns a Mission Log entry if an action was taken, else None.
    """
    if queue_length >= SURGE_QUEUE_THRESHOLD:
        team = crud.get_available_medical_team()
        if team is not None:
            crud.dispatch_medical_team(team.team_id, facility_id)
            facility = crud.get_facility_by_id(facility_id)
            facility_code = facility.facility_code if facility else str(facility_id)
            return make_entry(
                timestamp=clock.formatted_datetime(),
                category=CATEGORY_RESOURCE,
                message=f"{team.team_name} dispatched to {facility_code} (queue surge, faster treatment now in effect)",
                facility=facility_code,
            )
        return None

    if queue_length <= SURGE_RELEASE_THRESHOLD:
        dispatched = crud.get_dispatched_teams_for_facility(facility_id)
        if dispatched:
            team = dispatched[0]
            crud.release_medical_team(team.team_id)
            facility = crud.get_facility_by_id(facility_id)
            facility_code = facility.facility_code if facility else str(facility_id)
            return make_entry(
                timestamp=clock.formatted_datetime(),
                category=CATEGORY_RESOURCE,
                message=f"{team.team_name} released from {facility_code} (queue cleared)",
                facility=facility_code,
            )
    return None
