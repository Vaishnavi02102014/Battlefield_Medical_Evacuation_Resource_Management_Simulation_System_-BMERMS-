"""
map_adapter.py

Provider side of the tactical map's provider/renderer split (see
tactical_map.py's module docstring for the full split description).

get_map_data(...) is the ONE provider. It takes simulation.py's existing
mock state (FACILITY_STATUS, RESOURCE_STATUS, MISSION_LOG_ENTRIES) and
returns a single MapData object with every coordinate already resolved.
This is the ONLY module that knows where map data comes from.

render_tactical_map() in tactical_map.py has no idea whether the MapData
it receives was built from frontend mock state or, later, from live
backend queries -- it just renders whatever it's given. When backend
integration happens, only this module (or a new provider with the same
MapData return shape) needs to change.

Moved verbatim out of tactical_map.py -- no logic changed, no behavior
changed. Everything below was provider/derivation code there too; only
its file location is new.

Backend integration status:

- Facilities, incidents, casualties, resources, and evacuation routes
  are now derived from live backend state.
- This module remains the single provider that converts backend objects
  into renderer-ready MapData.
- render_tactical_map() remains completely source-agnostic.
"""

from __future__ import annotations
import logging
import math
import re
from dataclasses import dataclass, field
from backend.database import crud

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
 
 
def _derive_incidents(
        incidents_db: list
    ) -> list[dict]:
    """
    Derive incident markers from simulation.py's own MISSION_LOG_ENTRIES
    — its "Incident"-category entries — instead of maintaining a second,
    separately-hardcoded incident list. The mission log entry's own
    description is used verbatim as the popup text, so that narrative
    exists in exactly one place (the mission log), not two.
 
    The mission log only carries free text, not a structured battle
    sector or coordinates, so a sector name is matched by simple
    substring search against the known sector list — the map layout
    dict's sector_anchors keys — which is how a plot position is
    resolved. An entry that doesn't mention a known sector by name is
    skipped rather than guessed at.
    """
    incidents = []

    for incident in incidents_db:
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
        if casualty.status != "Being Evacuated":
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
  
 
def get_map_data(
    facility_status,
    resource_status,
    incidents_db,
    casualties_db,
    ambulances_db,
    helicopters_db,
    medical_teams_db,
) -> MapData:
    """
    THE single map data provider. Packages simulation.py's existing mock
    state into one fully-resolved MapData object — the only thing
    render_tactical_map() depends on.
 
    Args:
        facility_status: simulation.py's existing FACILITY_STATUS list.
        resource_status: simulation.py's existing RESOURCE_STATUS list.
        mission_log_entries: simulation.py's existing MISSION_LOG_ENTRIES
                              list (used to derive incidents — see
                              _derive_incidents()).
 
    Today this simply packages frontend mock state plus the frontend-only
    FRONTEND_MAP_LAYOUT coordinates. Later, an alternate provider (or this
    same function, rewritten) can build the identical MapData shape from
    live backend queries instead — render_tactical_map() would not need
    to change at all.
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
 
    incidents = _derive_incidents(incidents_db)
    casualties = _derive_casualties(casualties_db)
    routes = _derive_routes(casualties_db)

    ambulances = []

    for status in ["Available", "Dispatched"]:
        units = [
            a for a in ambulances_db
            if a.status == status
        ]

        if not units:
            continue

        staging_key = (
            "available"
            if status == "Available"
            else "busy"
        )

        base_x, base_y = _resolve_staging_point(
            FRONTEND_MAP_LAYOUT["resource_staging_points"][staging_key],
            incidents,
        )

        positions = _spread_positions(
            base_x,
            base_y,
            len(units),
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

    for status in ["Available", "Dispatched"]:
        units = [
            h for h in helicopters_db
            if h.status == status
        ]

        if not units:
            continue

        staging_key = (
            "available"
            if status == "Available"
            else "busy"
        )

        base_x, base_y = _resolve_staging_point(
            FRONTEND_MAP_LAYOUT["resource_staging_points"][staging_key],
            incidents,
        )

        positions = _spread_positions(
            base_x,
            base_y,
            len(units),
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

    for status in ["Available", "Dispatched"]:
        units = [
            t for t in medical_teams_db
            if t.status == status
        ]

        if not units:
            continue

        staging_key = (
            "available"
            if status == "Available"
            else "busy"
        )

        base_x, base_y = _resolve_staging_point(
            FRONTEND_MAP_LAYOUT["resource_staging_points"][staging_key],
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
    )