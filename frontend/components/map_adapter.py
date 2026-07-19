"""
map_adapter.py

Provider side of the tactical map's provider/renderer split (see
tactical_map.py's module docstring).

get_map_data(...) is the one provider: it takes live backend data
(facility/resource status, incidents, casualties, ambulances,
helicopters, medical teams) and returns a single MapData object with
every coordinate resolved. render_tactical_map() in tactical_map.py
has no knowledge of where MapData came from - it only renders what
it's given.

Facility marker positions, and every position derived from them
(evacuation route endpoints, interpolated vehicle destinations, and
staging-point resolution), are drawn from FRONTEND_MAP_LAYOUT in
components/map_constants.py rather than from the backend's own
Facility.grid_x/grid_y columns. This is a deliberate, independently
maintained coordinate set tuned for the rendered map canvas; it is not
sourced from the database. Incidents, casualties, and resource
positions are sourced from live backend data.

Idle ("Available") ambulances, helicopters, and medical teams are not
individually rendered; three aggregate Operational Staging Base
markers (STAGING_BASE_LAYOUT) represent reserve capacity per resource
type, each showing a live count computed fresh on every
get_map_data() call. Dispatched vehicles render at a position
linearly interpolated between their origin and destination across two
legs (Origin -> Incident -> Facility), based on elapsed simulation
time versus each vehicle's dispatch_time/release_time window, falling
back to a fixed near-incident position for any vehicle missing the
metadata needed to interpolate.
"""

from __future__ import annotations
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from backend.database import crud
from backend.utils.constants import VEHICLE_INITIAL_POSITIONS

from components.map_constants import FRONTEND_MAP_LAYOUT
logger = logging.getLogger(__name__)


@dataclass
class MapData:
    """
    Everything render_tactical_map() needs, fully resolved (coordinates
    included) — the single object the renderer depends on. Built by
    get_map_data() today from frontend mock state; a future backend-
    integrated provider should return this exact same shape.
    """
    facilities: list[dict] = field(default_factory=list)
    incidents: list[dict] = field(default_factory=list)
    ambulances: list[dict] = field(default_factory=list)
    helicopters: list[dict] = field(default_factory=list)
    medical_teams: list[dict] = field(default_factory=list)
    casualties: list[dict] = field(default_factory=list)
    routes: list[dict] = field(default_factory=list)
    staging_bases: list[dict] = field(default_factory=list)
 
 
def _spread_positions(base_grid_x: float, base_grid_y: float, count: int, radius: float = 10.0) -> list[tuple[float, float]]:
    """
    Deterministic (never random) placement for `count` units around one
    staging point, so multiple units at the same facility/incident don't
    render as a single overlapping marker. Same input always produces the
    same output.
    """
    if count <= 0:
        return []
    if count == 1:
        return [(base_grid_x, base_grid_y)]
    positions = []
    for index in range(count):
        angle = (2 * math.pi / count) * index
        positions.append((
            base_grid_x + radius * math.cos(angle),
            base_grid_y + radius * math.sin(angle),
        ))
    return positions



RESOURCE_DEPLOYMENT_LAYOUT: dict[str, list[tuple[float, float]]] = {
    "ambulance": [
        (20.0, 14.0),
        (50.0, 12.0),
        (80.0, 14.0),
    ],
    "helicopter": [
        (35.0, 42.0),
        (68.0, 42.0),
    ],
    "medical_team": [
        (30.0, 22.0),
        (65.0, 30.0),
    ],
}


def _resolve_idle_deployment_positions(resource_type_key: str, units: list) -> list[tuple[float, float]]:
    """
    Resolve fixed, deterministic map positions for a list of IDLE units of
    one resource type, using RESOURCE_DEPLOYMENT_LAYOUT.

    Units are assigned to deployment points round-robin by their position
    in `units` (i.e. by stable DB ordering - never randomly), then units
    sharing the same point are fanned out via _spread_positions() so they
    don't overlap. Returned positions are in the SAME order as `units`,
    so the caller can zip(units, positions) exactly as before.

    Falls back to the AO center (FRONTEND_MAP_LAYOUT["center"]) if
    `resource_type_key` has no entry in RESOURCE_DEPLOYMENT_LAYOUT, so an
    unrecognized resource type degrades gracefully instead of raising.
    """
    deployment_points = RESOURCE_DEPLOYMENT_LAYOUT.get(resource_type_key)
    if not deployment_points:
        logger.warning(
            "No RESOURCE_DEPLOYMENT_LAYOUT entry for resource_type_key=%r; "
            "falling back to the AO center for %d idle unit(s).",
            resource_type_key,
            len(units),
        )
        center_y, center_x = FRONTEND_MAP_LAYOUT["center"]
        return _spread_positions(center_x, center_y, len(units))

    point_count = len(deployment_points)
    positions: list[tuple[float, float] | None] = [None] * len(units)

    buckets: dict[int, list[int]] = {point_index: [] for point_index in range(point_count)}
    for unit_index in range(len(units)):
        buckets[unit_index % point_count].append(unit_index)

    for point_index, unit_indices in buckets.items():
        if not unit_indices:
            continue
        point_x, point_y = deployment_points[point_index]
        spread = _spread_positions(point_x, point_y, len(unit_indices))
        for unit_index, position in zip(unit_indices, spread):
            positions[unit_index] = position

    return positions
 
BATTLEFIELD_PRESENT_STATUSES: frozenset[str] = frozenset({
    "Awaiting Transport",
})

INCIDENT_ACTIVE_STATUSES: frozenset[str] = frozenset({
    "Awaiting Transport",
    "Being Evacuated",
})


def _active_incident_ids(casualties_db: list) -> set[str]:
    """
    Set of incident_ids whose evacuation mission is still ongoing - at
    least one associated casualty has not yet reached a treatment
    facility (see INCIDENT_ACTIVE_STATUSES). Built once per
    get_map_data() call from casualties_db (already passed in - no new
    query), then used as an O(1) lookup per incident in
    _derive_incidents(). Note: casualties_db
    (crud.get_active_casualties()) already excludes Recovered/Returned
    To Duty casualties - an incident whose casualties have ALL reached
    those statuses simply won't appear here at all, which correctly
    resolves it with no special-casing needed.
    """
    return {
        casualty.incident_id
        for casualty in casualties_db
        if casualty.status in INCIDENT_ACTIVE_STATUSES
    }


def _derive_incidents(
        incidents_db: list,
        casualties_db: list,
    ) -> list[dict]:
    active_incident_ids = _active_incident_ids(casualties_db)
    incidents = []

    for incident in incidents_db:
        incident_state = "Active" if incident.incident_id in active_incident_ids else "Resolved"
        incidents.append({
            "incident_id": incident.incident_id,
            "battle_sector": incident.battle_sector,
            "description": (
                f"{incident.event_type} reported in "
                f"Sector {incident.battle_sector} — "
                f"{incident.number_of_casualties} casualties"
            ),
            "casualty_count": incident.number_of_casualties,
            "grid_x": incident.grid_x,
            "grid_y": incident.grid_y,
            "incident_state": incident_state,
        })
    return incidents
 
 
def _derive_casualties(
        casualties_db: list
) -> list[dict]:
    severity_map = {
        "Critical": "Critical",
        "Serious": "Severe",
        "Moderate": "Moderate",
        "Mild": "Minor",
    }

    casualties = []

    for casualty in casualties_db:
        if casualty.status not in BATTLEFIELD_PRESENT_STATUSES:
            continue
        casualties.append({
            "casualty_ref": casualty.casualty_id,
            "severity": severity_map[
                casualty.severity
            ],
            "battle_sector": casualty.battle_sector,
            "grid_x": casualty.grid_x,
            "grid_y": casualty.grid_y,
        })

    return casualties

def _derive_routes(
    casualties_db: list,
) -> list[dict]:

    routes = []

    for casualty in casualties_db:
        if casualty.status != "Being Evacuated":
            continue

        if casualty.assigned_facility is None:
            continue

        facility = FRONTEND_MAP_LAYOUT["facility_positions"]

        destination = crud.get_facility_by_id(
            casualty.assigned_facility
        )

        if destination is None:
            logger.warning(
                "Assigned facility_id=%r for casualty %r "
                "does not exist. Route skipped.",
                casualty.assigned_facility,
                casualty.casualty_id,
            )
            continue

        facility_position = facility.get(
            destination.facility_code
        )

        if facility_position is None:
            logger.warning(
                "No tactical map coordinates found for "
                "facility_code=%r while deriving route "
                "for casualty %r.",
                destination.facility_code,
                casualty.casualty_id,
            )
            continue

        facility_y, facility_x = facility_position

        routes.append(
            {
                "segment": (
                    f"{casualty.casualty_id} "
                    f"Evacuation"
                ),
                "destination": destination.facility_code,
                "transport_mode": (
                    "Air"
                    if casualty.evacuation_mode
                    == "Helicopter"
                    else "Ground"
                ),
                "battle_sector": casualty.battle_sector,
                "start": (
                    casualty.grid_x,
                    casualty.grid_y,
                ),
                "end": (
                    facility_x,
                    facility_y,
                ),
            }
        )

    return routes

def _resolve_staging_point(staging_key: str, incidents: list[dict]) -> tuple[float, float]:
    """Resolve a resource_staging_points value ('RAP'/'ADS'/'FDC'/'INCIDENT') to grid (x, y)."""
    if staging_key == "INCIDENT":
        if incidents:
            return incidents[0]["grid_x"], incidents[0]["grid_y"]
        return FRONTEND_MAP_LAYOUT["center"][1], FRONTEND_MAP_LAYOUT["center"][0]
    facility_name = FRONTEND_MAP_LAYOUT["facility_code_to_name"][
        staging_key
    ]
    facility_y, facility_x = FRONTEND_MAP_LAYOUT[
        "facility_positions"
    ][staging_key]
    return facility_x, facility_y
  
STAGING_BASE_LAYOUT: dict[str, dict] = {
    "ambulance": {
        "label": "Forward Ambulance Staging",
        "subtitle": "Ground Evacuation Reserve",
        "resource_label": "Ambulances",
        "grid_x": VEHICLE_INITIAL_POSITIONS["Ambulance"]["grid_x"],
        "grid_y": VEHICLE_INITIAL_POSITIONS["Ambulance"]["grid_y"],
    },
    "medical_team": {
        "label": "Medical Reserve",
        "subtitle": "Deployable Medical Teams",
        "resource_label": "Medical Teams",
        "grid_x": 25.0,
        "grid_y": 45.0,
    },
    "helicopter": {
        "label": "Air MEDEVAC Base",
        "subtitle": "Air Evacuation Reserve",
        "resource_label": "Helicopters",
        "grid_x": VEHICLE_INITIAL_POSITIONS["Helicopter"]["grid_x"],
        "grid_y": VEHICLE_INITIAL_POSITIONS["Helicopter"]["grid_y"],
    },
}


def _build_staging_bases(ambulances_db: list, helicopters_db: list, medical_teams_db: list) -> list[dict]:
    available_counts = {
        "ambulance": sum(1 for unit in ambulances_db if unit.status == "Available"),
        "helicopter": sum(1 for unit in helicopters_db if unit.status == "Available"),
        "medical_team": sum(1 for unit in medical_teams_db if unit.status == "Available"),
    }

    staging_bases = []
    for resource_type, layout in STAGING_BASE_LAYOUT.items():
        staging_bases.append({
            "type": resource_type,
            "label": layout["label"],
            "subtitle": layout["subtitle"],
            "resource_label": layout["resource_label"],
            "available_count": available_counts[resource_type],
            "grid_x": layout["grid_x"],
            "grid_y": layout["grid_y"],
        })
    return staging_bases

RENDERED_RESOURCE_STATUSES: list[str] = ["Dispatched"]

def _build_facility_id_to_position() -> dict[int, tuple[float, float]]:
    """
    facility_id -> (grid_x, grid_y) for every facility, via ONE
    crud.get_all_facilities() call - never called per-vehicle. Reuses
    the exact same FRONTEND_MAP_LAYOUT["facility_positions"] source the
    facilities/routes layers already use, so a vehicle's interpolated
    destination always agrees with where that facility's own marker is
    drawn.
    """
    facility_positions: dict[int, tuple[float, float]] = {}
    for facility in crud.get_all_facilities():
        position = FRONTEND_MAP_LAYOUT["facility_positions"].get(facility.facility_code)
        if position is None:
            continue
        facility_y, facility_x = position
        facility_positions[facility.facility_id] = (facility_x, facility_y)
    return facility_positions


def _build_casualty_destination_lookup(
    casualties_db: list,
    facility_id_to_position: dict[int, tuple[float, float]],
) -> dict[str, tuple[float, float]]:
    """
    casualty_id -> destination (grid_x, grid_y), built once from
    casualties_db (already passed into get_map_data() - no new query)
    plus the facility map _build_facility_id_to_position() already
    resolved. A dispatched vehicle's destination is found by looking up
    its `assigned_casualty` in this dict - O(1), not a query.
    """
    destinations: dict[str, tuple[float, float]] = {}
    for casualty in casualties_db:
        if casualty.assigned_facility is None:
            continue
        position = facility_id_to_position.get(casualty.assigned_facility)
        if position is not None:
            destinations[casualty.casualty_id] = position
    return destinations


def _build_casualty_incident_position_lookup(casualties_db: list) -> dict[str, tuple[float, float]]:
    return {
        casualty.casualty_id: (casualty.grid_x, casualty.grid_y)
        for casualty in casualties_db
        if casualty.grid_x is not None and casualty.grid_y is not None
    }

PICKUP_DURATION_SECONDS: float = 120.0
MAX_PICKUP_FRACTION_OF_TRIP: float = 0.3


def _lerp_point(
    start: tuple[float, float],
    end: tuple[float, float],
    progress: float,
) -> tuple[float, float]:
    start_x, start_y = start
    end_x, end_y = end
    return (
        start_x + (end_x - start_x) * progress,
        start_y + (end_y - start_y) * progress,
    )


def _interpolate_dispatched_position(
    vehicle,
    incident_position: Optional[tuple[float, float]],
    destination_position: Optional[tuple[float, float]],
    current_time: Optional[datetime],
) -> Optional[tuple[float, float]]:
    if current_time is None or incident_position is None or destination_position is None:
        return None
    if vehicle.origin_grid_x is None or vehicle.origin_grid_y is None:
        return None
    if not vehicle.dispatch_time or not vehicle.release_time:
        return None

    try:
        dispatch_dt = datetime.strptime(vehicle.dispatch_time, "%Y-%m-%d %H:%M")
        release_dt = datetime.strptime(vehicle.release_time, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None

    total_seconds = (release_dt - dispatch_dt).total_seconds()
    if total_seconds <= 0:
        # Degenerate/invalid window (e.g. release_time <= dispatch_time) -
        # can't compute a meaningful fraction. Treat as "already arrived"
        # rather than divide by zero or guess.
        return destination_position

    origin_position = (vehicle.origin_grid_x, vehicle.origin_grid_y)

    # Split the trip's travel time between the two legs proportionally to
    # each leg's straight-line distance, so a vehicle starting right next
    # to the incident doesn't spend an unrealistic half its trip crawling
    # a short first leg. Falls back to an even 50/50 split only in the
    # degenerate case where both legs have zero length.
    leg1_distance = math.hypot(
        incident_position[0] - origin_position[0],
        incident_position[1] - origin_position[1],
    )
    leg2_distance = math.hypot(
        destination_position[0] - incident_position[0],
        destination_position[1] - incident_position[1],
    )
    total_distance = leg1_distance + leg2_distance
    leg1_fraction = (leg1_distance / total_distance) if total_distance > 0 else 0.5

    pickup_seconds = min(PICKUP_DURATION_SECONDS, total_seconds * MAX_PICKUP_FRACTION_OF_TRIP)
    travel_seconds = total_seconds - pickup_seconds
    leg1_seconds = travel_seconds * leg1_fraction
    leg2_seconds = travel_seconds - leg1_seconds
    pickup_end_seconds = leg1_seconds + pickup_seconds

    elapsed_seconds = (current_time - dispatch_dt).total_seconds()
    elapsed_seconds = max(0.0, min(total_seconds, elapsed_seconds))  # clamp: no overshoot/undershoot

    if elapsed_seconds <= leg1_seconds:
        leg_progress = (elapsed_seconds / leg1_seconds) if leg1_seconds > 0 else 1.0
        return _lerp_point(origin_position, incident_position, leg_progress)

    if elapsed_seconds <= pickup_end_seconds:
        # Pickup / loading hold - no animation, no countdown, just stay
        # exactly at the incident location for this window.
        return incident_position

    remaining_seconds = elapsed_seconds - pickup_end_seconds
    leg_progress = (remaining_seconds / leg2_seconds) if leg2_seconds > 0 else 1.0
    return _lerp_point(incident_position, destination_position, leg_progress)


def _resolve_dispatched_positions(
    units: list,
    casualty_incident_position: dict[str, tuple[float, float]],
    casualty_destination: dict[str, tuple[float, float]],
    current_time: Optional[datetime],
    incidents: list[dict],
) -> list[tuple[float, float]]:
    positions: list[Optional[tuple[float, float]]] = [None] * len(units)
    fallback_indices: list[int] = []

    for index, vehicle in enumerate(units):
        incident_position = casualty_incident_position.get(vehicle.assigned_casualty)
        destination = casualty_destination.get(vehicle.assigned_casualty)
        position = _interpolate_dispatched_position(
            vehicle, incident_position, destination, current_time
        )
        if position is not None:
            positions[index] = position
        else:
            fallback_indices.append(index)

    if fallback_indices:
        base_x, base_y = _resolve_staging_point(
            FRONTEND_MAP_LAYOUT["resource_staging_points"]["busy"],
            incidents,
        )
        fallback_positions = _spread_positions(base_x, base_y, len(fallback_indices))
        for fallback_index, position in zip(fallback_indices, fallback_positions):
            positions[fallback_index] = position

    return positions


def get_map_data(
    facility_status,
    resource_status,
    incidents_db,
    casualties_db,
    ambulances_db,
    helicopters_db,
    medical_teams_db,
    current_time: Optional[datetime] = None,
) -> MapData:
    """
    The single map data provider. Builds one fully-resolved MapData object
    from live backend inputs - the only thing render_tactical_map() depends
    on.

    Args:
        facility_status: list[dict], facility records (see
                        facilities_service.get_facility_overview()).
        resource_status: list[dict], resource records (see
                        dashboard.py's _build_resource_status()).
        incidents_db: list, from crud.get_recent_incidents().
        casualties_db: list[Casualty], from crud.get_active_casualties().
        ambulances_db: list[Ambulance], from crud.get_all_ambulances().
        helicopters_db: list[Helicopter], from crud.get_all_helicopters().
        medical_teams_db: list[MedicalTeam], from crud.get_all_medical_teams().
        current_time: optional live simulation clock time (clock.current_time).
                    When None, dispatched ambulances/helicopters render at
                    a fixed near-incident position instead of an
                    interpolated one.
    """
    facilities = []
    for facility in facility_status:
        position = FRONTEND_MAP_LAYOUT["facility_positions"].get(facility["facility_code"])
        if position is None:
            logger.warning(
                "No tactical map coordinates found for "
                "facility_code=%r (%r). Facility will not be rendered.",
                facility.get("facility_code"),
                facility.get("name"),
            )
            continue
        grid_y, grid_x = position
        facilities.append({**facility, "grid_x": grid_x, "grid_y": grid_y})
 
    incidents = _derive_incidents(incidents_db, casualties_db)
    casualties = _derive_casualties(casualties_db)
    routes = _derive_routes(casualties_db)
    staging_bases = _build_staging_bases(ambulances_db, helicopters_db, medical_teams_db)

    if current_time is not None:
        facility_id_to_position = _build_facility_id_to_position()
        casualty_destination = _build_casualty_destination_lookup(casualties_db, facility_id_to_position)
        casualty_incident_position = _build_casualty_incident_position_lookup(casualties_db)
    else:
        casualty_destination = {}
        casualty_incident_position = {}

    ambulances = []

    for status in RENDERED_RESOURCE_STATUSES:
        units = [
            a for a in ambulances_db
            if a.status == status
        ]

        if not units:
            continue

        if status == "Available":
            positions = _resolve_idle_deployment_positions("ambulance", units)
        else:
            positions = _resolve_dispatched_positions(
                units,
                casualty_incident_position,
                casualty_destination,
                current_time,
                incidents,
            )

        for ambulance, (grid_x, grid_y) in zip(
            units,
            positions,
        ):
            ambulances.append(
                {
                    "call_sign": ambulance.call_sign,
                    "status": ambulance.status,
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                }
            )

    helicopters = []

    for status in RENDERED_RESOURCE_STATUSES:
        units = [
            h for h in helicopters_db
            if h.status == status
        ]

        if not units:
            continue

        if status == "Available":
            positions = _resolve_idle_deployment_positions("helicopter", units)
        else:
            positions = _resolve_dispatched_positions(
                units,
                casualty_incident_position,
                casualty_destination,
                current_time,
                incidents,
            )

        for helicopter, (grid_x, grid_y) in zip(
            units,
            positions,
        ):
            helicopters.append(
                {
                    "call_sign": helicopter.call_sign,
                    "status": helicopter.status,
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                }
            )

    medical_teams = []

    for status in RENDERED_RESOURCE_STATUSES:
        units = [
            t for t in medical_teams_db
            if t.status == status
        ]

        if not units:
            continue

        if status == "Available":
            # Idle medical teams: fixed, deterministic deployment slots
            # (RESOURCE_DEPLOYMENT_LAYOUT) instead of one shared point.
            positions = _resolve_idle_deployment_positions("medical_team", units)
        else:
            # Busy medical teams keep their existing real operational
            # position - staged near the active incident - unchanged.
            base_x, base_y = _resolve_staging_point(
                FRONTEND_MAP_LAYOUT["resource_staging_points"]["busy"],
                incidents,
            )
            positions = _spread_positions(
                base_x,
                base_y,
                len(units),
            )

        for team, (grid_x, grid_y) in zip(
            units,
            positions,
        ):
            medical_teams.append(
                {
                    "call_sign": team.team_name,
                    "status": team.status,
                    "grid_x": grid_x,
                    "grid_y": grid_y,
                }
            )

    return MapData(
        facilities=facilities,
        incidents=incidents,
        ambulances=ambulances,
        helicopters=helicopters,
        medical_teams=medical_teams,
        casualties=casualties,
        routes=routes,
        staging_bases=staging_bases,
    )