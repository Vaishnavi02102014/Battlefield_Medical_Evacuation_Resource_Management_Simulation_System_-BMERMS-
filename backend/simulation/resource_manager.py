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
 
Phase 6A - movement metadata (not animation): _dispatch_vehicle() now also
records dispatch_time and origin (origin_grid_x/origin_grid_y) on the
vehicle row at the moment of dispatch - read-only metadata for a future
movement-visualization phase. This does not change dispatch policy, queue
behavior, availability, or timing in any way; see _dispatch_vehicle()'s
docstring for the full rationale.
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
    Commit an already-selected, already-available vehicle to a casualty.
    Responsible ONLY for: looking up destination-based travel time,
    computing the release/arrival time, marking the vehicle Dispatched via
    CRUD, and returning a TransportResult. No queue logic lives here - this
    is called identically by the immediate-dispatch path and the
    re-dispatch-after-release path, so dispatch mechanics exist in exactly
    one place.
 
    Note: this does NOT call attach_casualty_to_resource(). For a
    brand-new casualty, the casualty row does not exist yet at this point
    (FK constraint - see dispatch_transport()/decision_engine.py), so
    attachment must happen after the row is inserted. For a re-dispatched
    (previously queued) casualty, the row already exists, so the caller
    attaches immediately - see _redispatch_released_vehicle().
 
    Phase 6A - movement metadata: this is also THE single place dispatch
    timestamp and dispatch origin are captured, per architecture
    requirements (single dispatch commit point, no duplicate logic
    elsewhere). Both come from data already in hand here - no new query,
    no new coupling:
        - dispatch_time: the `dispatch_time` parameter this function
          already receives (the moment this trip departs).
        - origin (origin_grid_x/origin_grid_y): `vehicle.grid_x`/
          `vehicle.grid_y` - the vehicle's own currently-stored position,
          already present on the `vehicle` row/object passed in. This
          deliberately does NOT read from any presentation-layer staging
          config (e.g. map_adapter.STAGING_BASE_LAYOUT) - doing so would
          make this backend module depend on the frontend, inverting the
          established architecture. Instead, origin is simply "wherever
          this vehicle was last known to be." Today nothing yet writes to
          Ambulances/Helicopters.grid_x/grid_y, so origin will be NULL
          until a later phase begins maintaining that field (e.g. seeding
          it, or updating it on arrival) - a known, intentional, and
          nullable "not yet known" state, not a bug. Once something does
          maintain it, this function starts capturing real coordinates
          automatically, with no changes needed here.
    Neither value influences any dispatch decision - both are recorded
    purely as read-only metadata for future movement visualization.
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
 
    New v2 behaviour:
        1. Determine the eligible vehicle for this severity (_select_available_vehicle).
        2. If one is available, dispatch immediately (_dispatch_vehicle).
        3. If none is available, enqueue the casualty in the transport queue
           and return a result indicating it is Awaiting Transport.
 
    This function never returns "Foot" - Foot evacuation no longer exists.
 
    Note on parameters: `casualty_id` and `facility_code` are new,
    required parameters versus the v1 signature - both are necessary for
    v2 (queue entries must carry a casualty_id, and travel time now
    depends on the destination facility). `rng` is retained only for
    call-site compatibility with the existing decision_engine.py caller;
    it is no longer used internally, since the randomized Mild/Foot
    fallback has been removed entirely.
 
    BREAKING API CHANGE vs. Version 1 - decision_engine.py must be
    updated in Phase 1B.3 to call this function with the new signature:
        - `casualty_id` must already exist (e.g. via crud.get_next_casualty_id())
          BEFORE this function is called, since a queued casualty needs an
          id to be enqueued under even though its DB row may not exist yet.
        - `facility_code` is now required because travel time is looked up
          as TRANSPORT_TIME[vehicle_type][facility_code] - destination now
          determines duration, not just vehicle type - so the caller must
          resolve the destination facility before requesting transport.
    decision_engine.py must also be updated to consume the returned
    TransportResult object instead of unpacking a
    (evacuation_mode, resource_id, transit_minutes) tuple.
 
    The resource is linked to its casualty separately by the caller
    (attach_casualty_to_resource), once the casualty row exists in the DB,
    exactly as in v1 - this function only decides and marks the vehicle.
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