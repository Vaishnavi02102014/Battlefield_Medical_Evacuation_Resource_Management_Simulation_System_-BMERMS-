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

No backend imports of any kind (unchanged from before the move).
# Visualization-only evacuation chain.
# Routes are intentionally frontend-generated and do not require
# backend route tables, GIS pathfinding, or route APIs.
"""

from __future__ import annotations
import math
import re
from dataclasses import dataclass, field

from components.map_constants import FRONTEND_MAP_LAYOUT

# Used only when assigning severity to derived mock casualties (see
# _derive_casualties below) — provider-only, not used by any renderer.
CASUALTY_SEVERITY_CYCLE: list[str] = ["Critical", "Severe", "Moderate", "Minor"]

# Frontend-only fallback used only if an Incident-category mission log
# entry doesn't mention a numeric casualty count in its text.
DEFAULT_CASUALTY_COUNT_PER_INCIDENT: int = 2

# Deterministic evacuation chain (matches backend's real RAP->ADS->HMV
# progression) with each leg's transport mode — provider-derived mock
# values only, not a new simulation state.
EVACUATION_CHAIN: list[dict] = [
    {"segment": "Incident to RAP", "facility_code": "RAP", "transport_mode": "Ground"},
    {"segment": "RAP to ADS", "facility_code": "ADS", "transport_mode": "Ground"},
    {"segment": "ADS to HMV", "facility_code": "HMV", "transport_mode": "Air"},
]


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
 
 
def _spread_positions(base_grid_x: float, base_grid_y: float, count: int, radius: float = 5.0) -> list[tuple[float, float]]:
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
 
 
def _derive_incidents(mission_log_entries: list[dict]) -> list[dict]:
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
    known_sectors = FRONTEND_MAP_LAYOUT["sector_anchors"].keys()
    incidents = []
    for entry in mission_log_entries:
        if entry.get("category") != "Incident":
            continue
        matched_sector = next((sector for sector in known_sectors if sector in entry["description"]), None)
        if matched_sector is None:
            continue
        grid_x, grid_y = FRONTEND_MAP_LAYOUT["sector_anchors"][matched_sector]
        # Casualty count for the popup/casualty markers: the mission log
        # only carries prose, so the number is picked out of the existing
        # description text (e.g. "4 casualties confirmed") with a simple
        # pattern match rather than inventing a separate figure. Falls
        # back to DEFAULT_CASUALTY_COUNT_PER_INCIDENT if no number is
        # mentioned.
        casualty_match = re.search(r"(\d+)\s+casualt", entry["description"], re.IGNORECASE)
        casualty_count = int(casualty_match.group(1)) if casualty_match else DEFAULT_CASUALTY_COUNT_PER_INCIDENT
        incidents.append({
            "battle_sector": matched_sector,
            "description": entry["description"],
            "casualty_count": casualty_count,
            "grid_x": grid_x,
            "grid_y": grid_y,
        })
    return incidents
 
 
def _derive_casualties(incidents: list[dict]) -> list[dict]:
    """
    Minimal visualization-only casualty representation, derived here
    inside the provider — not a second global simulation state. The mock
    state has no individual Casualty objects, only each incident's
    casualty_count (see _derive_incidents), so that many points are
    plotted clustered around the incident's own location, with severity
    assigned by cycling a fixed order (CASUALTY_SEVERITY_CYCLE) —
    deterministic, never random. This list exists only for the duration
    of one get_map_data() call and is not stored anywhere else; it
    disappears entirely once backend integration supplies real Casualty
    rows with their own grid_x/grid_y/severity.
    """
    casualties = []
    casualty_sequence = 1
    for incident in incidents:
        positions = _spread_positions(
            incident["grid_x"], incident["grid_y"], incident["casualty_count"], radius=3.5,
        )
        for index, (grid_x, grid_y) in enumerate(positions):
            casualties.append({
                "casualty_ref": f"CAS-{casualty_sequence:03d}",
                "severity": CASUALTY_SEVERITY_CYCLE[index % len(CASUALTY_SEVERITY_CYCLE)],
                "battle_sector": incident["battle_sector"],
                "grid_x": grid_x,
                "grid_y": grid_y,
            })
            casualty_sequence += 1
    return casualties
 
 
def _derive_routes(incidents: list[dict]) -> list[dict]:
    """
    Evacuation route segments (Incident -> RAP -> ADS -> HMV), derived
    entirely inside the provider from data already resolved here — the
    incident's own location plus FRONTEND_MAP_LAYOUT's facility
    positions. Not a new simulation state: EVACUATION_CHAIN is a fixed,
    deterministic presentation of the same evacuation order the backend
    already documents (FACILITY_ORDER), with transport mode assigned
    per-leg, never randomly.
    """
    routes = []
    for incident in incidents:
        previous_point = (incident["grid_x"], incident["grid_y"])
        for leg in EVACUATION_CHAIN:
            facility_name = FRONTEND_MAP_LAYOUT["facility_code_to_name"][leg["facility_code"]]
            facility_y, facility_x = FRONTEND_MAP_LAYOUT["facility_positions"][facility_name]
            routes.append({
                "segment": leg["segment"],
                "destination": facility_name,
                "transport_mode": leg["transport_mode"],
                "battle_sector": incident["battle_sector"],
                "start": previous_point,
                "end": (facility_x, facility_y),
            })
            previous_point = (facility_x, facility_y)
    return routes
 
 
def _resolve_staging_point(staging_key: str, incidents: list[dict]) -> tuple[float, float]:
    """Resolve a resource_staging_points value ('RAP'/'ADS'/'FDC'/'INCIDENT') to grid (x, y)."""
    if staging_key == "INCIDENT":
        if incidents:
            return incidents[0]["grid_x"], incidents[0]["grid_y"]
        return FRONTEND_MAP_LAYOUT["center"][1], FRONTEND_MAP_LAYOUT["center"][0]
    facility_name = FRONTEND_MAP_LAYOUT["facility_code_to_name"][staging_key]
    facility_y, facility_x = FRONTEND_MAP_LAYOUT["facility_positions"][facility_name]
    return facility_x, facility_y
 
 
def _derive_resource_units(resource_entry: dict, call_sign_prefix: str, incidents: list[dict]) -> list[dict]:
    """Expand one RESOURCE_STATUS entry's available/busy/returning/maintenance counts into individual, positioned units."""
    units = []
    unit_index = 1
    for status_key, count in (
        ("available", resource_entry.get("available", 0)),
        (
            "busy",
            resource_entry.get(
                "busy",
                resource_entry.get("dispatched", 0),
            ),
        ),
    ):
        staging_key = FRONTEND_MAP_LAYOUT["resource_staging_points"].get(
            status_key,
            "INCIDENT",
        )
        base_x, base_y = _resolve_staging_point(staging_key, incidents)
        for grid_x, grid_y in _spread_positions(base_x, base_y, count):
            units.append({
                "call_sign": f"{call_sign_prefix}-{unit_index:02d}",
                "status": status_key.capitalize(),
                "grid_x": grid_x,
                "grid_y": grid_y,
            })
            unit_index += 1
    return units
 
 
def get_map_data(facility_status: list[dict], resource_status: list[dict], mission_log_entries: list[dict]) -> MapData:
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
        position = FRONTEND_MAP_LAYOUT["facility_positions"].get(facility["name"])
        if position is None:
            continue
        grid_y, grid_x = position
        facilities.append({**facility, "grid_x": grid_x, "grid_y": grid_y})
 
    incidents = _derive_incidents(mission_log_entries)
    casualties = _derive_casualties(incidents)
    routes = _derive_routes(incidents)
 
    resource_by_name = {entry["name"]: entry for entry in resource_status}
    ambulances = (
        _derive_resource_units(resource_by_name["Ambulances"], "AMB", incidents)
        if "Ambulances" in resource_by_name else []
    )
    helicopters = (
        _derive_resource_units(resource_by_name["Helicopters"], "HELI", incidents)
        if "Helicopters" in resource_by_name else []
    )
    medical_teams = (
        _derive_resource_units(resource_by_name["Medical Teams"], "MED-TEAM", incidents)
        if "Medical Teams" in resource_by_name else []
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