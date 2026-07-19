"""
resource_manager.py

Responsible for the three trackable resource pools: Ambulances, Helicopters,
Medical Teams.

Vehicle dispatch model: dispatching an ambulance or helicopter marks it
"Dispatched" for a transit duration determined by vehicle type and
destination facility (utils.constants.TRANSPORT_TIME). When a vehicle's
transit time elapses, it is either immediately re-dispatched to the
highest-priority casualty currently waiting in the transport queue, or
released back to the available pool if no casualty is waiting.

Medical team model: when a facility's waiting queue grows past a surge
threshold, an available medical team is dispatched to that facility. When
the queue drops back below a lower release threshold, one dispatched team
is released from that facility. This is a light-touch resource-management
signal, not a detailed staffing simulation.

Movement metadata: dispatching a vehicle also records dispatch_time and
its origin position (origin_grid_x/origin_grid_y) on the vehicle row at
the moment of dispatch. This is read-only metadata describing where and
when the vehicle's current trip began; it does not influence dispatch
policy, queue behavior, availability, or timing.
"""
 
from __future__ import annotations
import random
from backend.database import crud
from backend.simulation.simulation_clock import SimulationClock
from backend.simulation.mission_log import MissionLogEntry, make_entry, CATEGORY_RESOURCE
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
 
from backend.simulation import transport_queue
from backend.utils.constants import (
    TRANSPORT_TIME,
    SEVERITY_LIST,
)
 
SURGE_QUEUE_THRESHOLD: int = 10
SURGE_RELEASE_THRESHOLD: int = 4
 
@dataclass(frozen=True)
class TransportResult:
    dispatched: bool
    casualty_id: str
    facility_code: str
    status: str
    evacuation_mode: Optional[str] = None
    resource_id: Optional[int] = None
    transit_minutes: Optional[int] = None
    evacuation_arrival_time: Optional[str] = None
 
_HELICOPTER_ELIGIBLE_SEVERITIES = (
    "Critical",
    "Serious",
)
 
 
def _redispatch_released_vehicle(vehicle_type: str, vehicle, clock: SimulationClock) -> Optional[TransportResult]:
    """
    Attempt to immediately re-dispatch a vehicle that has just completed
    its mission to the highest-priority casualty waiting in the transport
    queue - reusing that EXACT vehicle instance. This does NOT call
    _select_available_vehicle(): the vehicle has already been chosen (it's
    the one that just finished its trip), so re-selecting from the wider
    available pool would risk grabbing a different, unrelated vehicle
    while this one sits idle. Only the caller decides whether to fall back
    to releasing this vehicle to the available pool - that happens if and
    only if this function returns None (see release_due_transport()).
 
    Scans the four severity queues in fixed priority order (Critical ->
    Serious -> Moderate -> Mild) via SEVERITY_LIST, and attempts to
    dispatch the front (earliest-enqueued) entry of the first eligible
    non-empty queue. A Helicopter only ever considers the Critical/Serious
    queues - it must never be handed to a Moderate/Mild casualty, matching
    the same policy enforced in _select_available_vehicle().
 
    Failure-safe queue handling: the candidate entry is read with
    peek_front() (not removed) and only popped with pop_front() AFTER
    _dispatch_vehicle() succeeds. If dispatch raises for any reason (CRUD
    exception, invalid facility, unexpected runtime error), the queue
    entry is left exactly where it was and this function returns None -
    the casualty is never lost, and the caller falls back to releasing the
    vehicle to the available pool.
 
    The casualty row already exists in the DB at this point (it was
    inserted, as "Awaiting Transport", back when it was originally
    enqueued), so - unlike the initial-dispatch path - this function
    attaches the vehicle to the casualty and flips its status immediately,
    rather than deferring attachment to a caller.
 
    Lifecycle synchronization: this writes status, evacuation_mode, and
    evacuation_arrival_time together via crud.update_casualty_evacuation(),
    the same atomic transition the immediate-dispatch path produces. This
    keeps a queued-then-redispatched casualty's row identical in shape to
    one dispatched immediately at triage, so
    process_arrived_evacuations()'s "evacuation_arrival_time <= now" gate
    picks it up normally instead of the casualty being silently invisible
    forever (a NULL evacuation_arrival_time never satisfies that
    comparison).
 
    Returns the TransportResult for the casualty that was re-dispatched,
    or None if no eligible waiting casualty was found (or dispatch failed)
    for this vehicle.
    """
    if vehicle_type == "Helicopter":
        eligible_severities = [s for s in SEVERITY_LIST if s in _HELICOPTER_ELIGIBLE_SEVERITIES]
    else:
        eligible_severities = list(SEVERITY_LIST)
 
    for severity in eligible_severities:
        entry = transport_queue.peek_front(severity)
        if entry is None:
            continue
 
        try:
            result = _dispatch_vehicle(
                vehicle_type=vehicle_type,
                vehicle=vehicle,
                casualty_id=entry.casualty_id,
                facility_code=entry.facility_code,
                dispatch_time=clock.current_time,
            )
            attach_casualty_to_resource(result.evacuation_mode, result.resource_id, entry.casualty_id)
            crud.update_casualty_evacuation(
                entry.casualty_id,
                status=result.status,
                evacuation_mode=result.evacuation_mode,
                evacuation_arrival_time=result.evacuation_arrival_time,
            )
        except Exception:
            # Dispatch failed for this candidate - the entry was only
            # peeked, never popped, so it is still safely at the front of
            # its queue. Do not try another severity this cycle; let the
            # caller fall back to releasing the vehicle to the available
            # pool instead.
            return None
 
        # Only remove the entry from the queue after a successful dispatch.
        transport_queue.pop_front(severity)
        return result
 
    return None
 
def _select_available_vehicle(severity: str):
    """
    Vehicle-selection policy - the ONLY place this decision is made.
    Both immediate dispatch (dispatch_transport) and re-dispatch after a
    vehicle release (_redispatch_released_vehicle) call this helper, so the
    policy can never drift between the two call sites.
 
    Critical / Serious -> Helicopter first, then Ambulance.
    Moderate / Mild     -> Ambulance only. Helicopters are never considered.
 
    Returns (vehicle_type, vehicle_row) for the first available match, or
    (None, None) if nothing is currently available for this severity.
    This function only looks up availability - it never marks anything
    Dispatched. That happens in _dispatch_vehicle().
    """
    if severity not in SEVERITY_LIST:
        raise ValueError(f"Unknown severity '{severity}'. Expected one of {SEVERITY_LIST}.")
 
    if severity in _HELICOPTER_ELIGIBLE_SEVERITIES:
        heli = crud.get_available_helicopter()
        if heli is not None:
            return "Helicopter", heli
 
    amb = crud.get_available_ambulance()
    if amb is not None:
        return "Ambulance", amb
 
    return None, None
 
def _dispatch_vehicle(
    vehicle_type: str,
    vehicle,
    casualty_id: str,
    facility_code: str,
    dispatch_time: datetime,
) -> TransportResult:
    """
    Commit an already-selected, available vehicle to a casualty.

    Looks up the transit time for the given vehicle type and destination
    facility, computes the release/arrival time, marks the vehicle
    Dispatched via CRUD, and returns a TransportResult. Contains no queue
    logic; it is called identically by the immediate-dispatch path and the
    re-dispatch-after-release path, so dispatch mechanics exist in exactly
    one place.

    This function does not call attach_casualty_to_resource(). For a
    newly-triaged casualty, the casualty row does not exist yet at this
    point (see dispatch_transport() / decision_engine.py), so attachment
    happens after the row is inserted. For a re-dispatched casualty drawn
    from the transport queue, the row already exists, so the caller
    attaches the resource immediately (see _redispatch_released_vehicle()).

    This is also the single place dispatch timestamp and dispatch origin
    are captured:
        - dispatch_time: the `dispatch_time` parameter this function
        receives (the moment this trip departs).
        - origin (origin_grid_x/origin_grid_y): `vehicle.grid_x`/
        `vehicle.grid_y`, the vehicle's currently stored position.
        Origin is read only from the vehicle's own row, never from any
        presentation-layer configuration, so this module has no
        dependency on the frontend.

    Neither value influences any dispatch decision; both are recorded as
    read-only metadata for movement visualization.
    """
    transit = TRANSPORT_TIME[vehicle_type][facility_code]
    release_time = dispatch_time + timedelta(minutes=transit)
    release_time_str = release_time.strftime("%Y-%m-%d %H:%M")
    dispatch_time_str = dispatch_time.strftime("%Y-%m-%d %H:%M")
    origin_grid_x = vehicle.grid_x
    origin_grid_y = vehicle.grid_y
 
    if vehicle_type == "Helicopter":
        resource_id = vehicle.helicopter_id
        crud.dispatch_helicopter(
            resource_id,
            release_time_str,
            dispatch_time=dispatch_time_str,
            origin_grid_x=origin_grid_x,
            origin_grid_y=origin_grid_y,
        )
    else:
        resource_id = vehicle.ambulance_id
        crud.dispatch_ambulance(
            resource_id,
            release_time_str,
            dispatch_time=dispatch_time_str,
            origin_grid_x=origin_grid_x,
            origin_grid_y=origin_grid_y,
        )
 
    return TransportResult(
        dispatched=True,
        casualty_id=casualty_id,
        facility_code=facility_code,
        status="Being Evacuated",
        evacuation_mode=vehicle_type,
        resource_id=resource_id,
        transit_minutes=transit,
        evacuation_arrival_time=release_time_str,
    )
 
 
def dispatch_transport(
    casualty_id: str,
    severity: str,
    facility_code: str,
    clock: SimulationClock,
    casualty_arrival_time: datetime,
    rng: Optional[random.Random] = None,
) -> TransportResult:
    """
    Request transport for a newly-triaged casualty.

    1. Determine the eligible vehicle type for this severity
    (_select_available_vehicle).
    2. If a vehicle is available, dispatch it immediately (_dispatch_vehicle).
    3. If none is available, enqueue the casualty in the transport queue and
    return a result indicating it is Awaiting Transport.

    Parameters:
        casualty_id must already be generated (e.g. via
        crud.get_next_casualty_id()) before this function is called, since a
        queued casualty needs an id to be enqueued under even though its
        database row may not exist yet.

        facility_code identifies the destination facility; transit time is
        looked up as TRANSPORT_TIME[vehicle_type][facility_code], so travel
        duration depends on both vehicle type and destination.

        rng is accepted for call-site compatibility but is not used inside
        this function.

    The resource is linked to its casualty separately by the caller
    (attach_casualty_to_resource) once the casualty row exists in the
    database; this function only selects, dispatches, and marks the vehicle.
    """
    vehicle_type, vehicle = _select_available_vehicle(severity)
 
    if vehicle is not None:
        return _dispatch_vehicle(vehicle_type, vehicle, casualty_id, facility_code, casualty_arrival_time)
 
    transport_queue.enqueue(
        severity=severity,
        casualty_id=casualty_id,
        facility_code=facility_code,
        queued_at=casualty_arrival_time.strftime("%Y-%m-%d %H:%M"),
    )
    return TransportResult(
        dispatched=False,
        casualty_id=casualty_id,
        facility_code=facility_code,
        status="Awaiting Transport",
    )
 
 
def attach_casualty_to_resource(evacuation_mode: str, resource_id: int | None, casualty_id: str) -> None:
    """Link a just-dispatched resource to the casualty it's carrying, once that casualty row exists."""
    if resource_id is None:
        return
    if evacuation_mode == "Helicopter":
        crud.attach_casualty_to_helicopter(resource_id, casualty_id)
    elif evacuation_mode == "Ambulance":
        crud.attach_casualty_to_ambulance(resource_id, casualty_id)
 
 
def release_due_transport(clock: SimulationClock) -> None:
    """
    Process every ambulance/helicopter whose transit time has elapsed.
 
    For each one, first attempt to immediately re-dispatch that SAME
    vehicle to the highest-priority casualty waiting in the transport
    queue (Critical -> Serious -> Moderate -> Mild, FIFO within a
    severity; Helicopters only ever consider the Critical/Serious queues).
    Only if no eligible waiting casualty is found does the vehicle get
    returned to the available pool via crud.release_ambulance()/
    release_helicopter(). A vehicle that is immediately re-dispatched is
    never released to the available pool - it goes straight from one
    mission to the next.
    """
    current_time_str = clock.formatted_datetime()
 
    for ambulance in crud.get_due_ambulances(current_time_str):
        redispatch_result = _redispatch_released_vehicle("Ambulance", ambulance, clock)
        if redispatch_result is None:
            crud.release_ambulance(ambulance.ambulance_id)
 
    for helicopter in crud.get_due_helicopters(current_time_str):
        redispatch_result = _redispatch_released_vehicle("Helicopter", helicopter, clock)
        if redispatch_result is None:
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