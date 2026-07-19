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

Phase 5 - idle resource deployment positions:
- Previously, every idle ("Available") ambulance/helicopter/medical team
  was staged around one single shared point
  (FRONTEND_MAP_LAYOUT["resource_staging_points"]["available"]), which is
  why the battlefield looked unrealistic - all idle units piled up
  around the same spot regardless of type.
- Idle units are now staged across RESOURCE_DEPLOYMENT_LAYOUT below - a
  fixed, deterministic, per-resource-type set of pre-positioned military
  staging points spread across the operational area. No randomness is
  used anywhere in this positioning.
- Busy ("Dispatched") units are completely unaffected by this change -
  they continue to resolve to their real operational position (staged
  near the active incident) exactly as before.
- This is a visualization-only change: it does not touch resource
  availability, dispatch logic, travel time, or any simulation behavior.
  It only changes where an already-idle unit is DRAWN on the map.

Phase 5A - active resources only:
- The tactical map now renders ONLY resources whose status is in
  RENDERED_RESOURCE_STATUSES below (currently just "Dispatched") - idle
  ("Available") ambulances/helicopters/medical teams are no longer drawn
  at all, reducing map clutter so it emphasizes ongoing operations.
- This is filtering only. Idle resources still exist, are still
  "Available" in the database, and still appear normally everywhere else
  (Resource page, Dashboard, Fleet Status, AI resource assessment) - only
  their tactical-map marker is suppressed.
- Reversible in one line: change RENDERED_RESOURCE_STATUSES back to
  ["Available", "Dispatched"] to restore idle-resource rendering. The
  Phase 5 idle-deployment-position logic (RESOURCE_DEPLOYMENT_LAYOUT,
  _resolve_idle_deployment_positions) is left fully intact for that.

Phase 5B - Operational Staging Bases:
- Instead of hiding idle resources with nothing to show for them (as
  Phase 5A does), three permanent aggregate markers now represent
  reserve capacity: Forward Ambulance Staging, Air MEDEVAC Base, and
  Medical Reserve - one per resource type, at fixed positions defined
  in STAGING_BASE_LAYOUT below.
- These are NOT individual-vehicle markers. Each one shows a live
  count of that type's currently "Available" units, computed fresh by
  _build_staging_bases() on every get_map_data() call from the same
  ambulances_db/helicopters_db/medical_teams_db lists Phase 5A already
  filters - no new data source, no caching, always live.
- Individual resource markers still only appear when Dispatched
  (Phase 5A behavior, unchanged) - staging bases are additive, not a
  replacement for that filtering.
- Forward-compatible with Phase 6 (Resource Movement Animation): each
  staging base carries a stable `type` key and a fixed (grid_x, grid_y)
  origin coordinate, so a future animation can look up "where does an
  ambulance/helicopter/medical team originate from" directly off this
  same MapData.staging_bases list, with no further provider changes.

Phase 5C - staging base visual refinement:
- Placement only: STAGING_BASE_LAYOUT positions were re-triangulated
  across the AO (previously all three shared x=50) and a static
  `subtitle` label was added per type for the renderer's tooltip/popup.
  No counting logic, no MapData shape change, no new fields on
  MapData itself - _build_staging_bases()'s available_counts block is
  unchanged. All remaining presentation work (icon, colors, popup/
  tooltip copy, operational-status wording) lives in tactical_map.py.

Phase 6B - live vehicle movement interpolation:
- Dispatched ambulances/helicopters no longer render at the batch
  "parked near the incident" placeholder. get_map_data() now accepts
  an optional `current_time` and, for each dispatched unit, computes a
  live linearly-interpolated position between its Phase 6A origin
  (origin_grid_x/origin_grid_y) and its destination facility, based on
  elapsed simulation time versus its dispatch_time/release_time window.
- This is provider-side interpolation only - no animation, no JS/CSS,
  no Folium changes. Position simply updates once per render() call,
  same as every other layer.
- Falls back to the existing placeholder positioning, per-unit, for
  any vehicle missing required metadata (legacy/unmigrated row,
  unresolved destination, malformed timestamp) or when current_time
  isn't supplied - never crashes, never guesses.
- Medical Teams are unaffected - they have no travel/motion concept
  in the data model and are out of scope for this phase.

Phase 6C - two-leg evacuation journey (Origin -> Incident -> Facility):
- Extends (does not replace) Phase 6B's interpolation. A dispatched
  ambulance/helicopter's journey is now Origin -> Incident location
  (Leg 1), a brief stationary pickup hold at the incident, then
  Incident -> destination Facility (Leg 2) - all within the SAME
  dispatch_time -> release_time window already established in Phase
  6A/6B. Total travel duration (TRANSPORT_TIME) is completely
  untouched; this only changes how that existing duration is visually
  spent across two legs plus a pause, not how long it is.
- Zero new backend metadata: the incident location is just
  Casualty.grid_x/grid_y, which already existed. No schema change, no
  new column, no new query beyond what Phase 6B already introduced.
- The actual interpolation math (_lerp_point) is unchanged from
  Phase 6B and is now called twice per vehicle (once per leg) instead
  of once - not duplicated, reused.
- Same per-unit graceful-fallback contract as Phase 6B: any vehicle
  missing what it needs for the two-leg journey (no resolvable
  incident, no resolvable destination, missing origin, malformed
  timestamps) falls back to the existing placeholder positioning
  exactly as before - never crashes, never guesses.
- Medical Teams remain completely out of scope, unchanged.

Phase 7B - incident lifecycle, refined 7B.1 (concept-driven, not
status-name-driven), refined 7B.2 (mission-based, not location-based -
see below):
- Every incident dict carries an `incident_state` field
  ("Active"/"Resolved"), derived fresh on every get_map_data() call
  from casualties_db - never stored, never cached, no schema change.
  "Active" means at least one of that incident's casualties has not yet
  reached a treatment facility - the evacuation mission is still
  ongoing; "Resolved" means every casualty has. This says nothing about
  medical treatment progress itself, only whether the incident's
  evacuation mission is still ongoing.
- Which specific casualty statuses count as "mission still ongoing" is
  a single, extensible definition - INCIDENT_ACTIVE_STATUSES - not
  hardcoded anywhere else in this file. See that constant's own comment
  block for how to extend it as future phases add new statuses.
- The renderer consumes this field (Phase 7D) but never recomputes or
  infers it.

Phase 7B.2 - incident lifecycle redefined (mission-based):
- The original Phase 7B definition ("still physically on the
  battlefield") assumed an "awaiting pickup" state this simulation
  doesn't model - a casualty moves straight from "Awaiting Transport" to
  "Being Evacuated" to "Under Treatment" the instant a vehicle is
  available. Under the old definition an incident could read as Resolved
  moments after creation, as soon as its first casualty was picked up -
  before the evacuation mission had actually finished.
- INCIDENT_ACTIVE_STATUSES now includes both "Awaiting Transport" AND
  "Being Evacuated" - an incident stays Active for as long as any
  casualty hasn't yet reached a facility, matching how this simulation's
  transport model actually behaves.
- This is now a DIFFERENT, independent definition from
  BATTLEFIELD_PRESENT_STATUSES (Phase 7C, casualty marker visibility) -
  the two concepts answer different questions and are allowed to
  disagree (see _derive_casualties()'s docstring).

Phase 7C - battlefield object visibility (casualty markers only):
- A casualty only gets a map marker while battlefield-present (see
  BATTLEFIELD_PRESENT_STATUSES) - once evacuation begins, the casualty's
  own marker disappears and the transporting vehicle becomes its visible
  representation. As of Phase 7B.2 this is its own dedicated,
  purpose-specific definition - deliberately narrower than, and
  independent from, INCIDENT_ACTIVE_STATUSES (incident lifecycle).
- Scoped entirely to _derive_casualties(). Routes, vehicle positions,
  facilities, and staging bases are unaffected - see _derive_routes(),
  which intentionally keeps its own separate "currently in transit"
  condition, since a route's purpose (show an active transit) differs
  from a casualty marker's purpose (show battlefield presence).
"""

from __future__ import annotations
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
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


# --------------------------------------------------------------------------
# RESOURCE_DEPLOYMENT_LAYOUT (Phase 5)
#
# THE single configuration for idle-resource staging positions on the
# tactical map. Edit the (grid_x, grid_y) points below to adjust where
# idle units are drawn - no other code in this file (or tactical_map.py)
# needs to change.
#
# Each resource type gets its own list of fixed, pre-positioned staging
# points spread across the operational area (AO bounds are 0-100 on both
# axes - see utils.constants.AO_GRID_BOUNDS), loosely following real
# MEDEVAC doctrine relative to the fixed evacuation chain
# (RAP y=8 -> ADS y=25 -> HMV y=55 -> FDC y=85, front line y=2-5):
#
#   - Ambulances : forward staging, just behind the front line / near RAP
#                  depth, spread across the width of the AO so ground
#                  units are pre-positioned close to where casualties
#                  actually occur.
#   - Helicopters: rear staging near HMV depth (fewer, wider-spaced
#                  landing points) - air assets stage further back and
#                  cover more ground per sortie.
#   - Medical Teams: mid-depth staging near ADS, ready to reinforce
#                  whichever facility needs a surge team next.
#
# Idle units of a given type are assigned to these points round-robin (by
# stable list order - ambulance_id / call_sign order from the DB - never
# randomly), then fanned out around whichever point they land on via
# _spread_positions() so co-located units don't overlap. This only
# affects "Available" units; "Dispatched" units keep resolving to their
# real operational position via _resolve_staging_point(), unchanged.
# --------------------------------------------------------------------------
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

    # Bucket unit indices by deployment point (round-robin over stable
    # input order), then spread each bucket around its point.
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
 
 
# --------------------------------------------------------------------------
# CASUALTY BATTLEFIELD PRESENCE (Phase 7C)
#
# Whether a casualty gets its own map marker at all. This is a CONCEPT,
# not a status name: a casualty is battlefield-present if they have not
# yet physically departed the incident location - no vehicle has picked
# them up yet. Once evacuation begins (a vehicle collects them), they
# are no longer physically at the incident, so they stop getting a
# marker of their own - the transporting vehicle becomes their visible
# representation (see _derive_casualties()).
#
# BATTLEFIELD_PRESENT_STATUSES below is THE single definition of that
# specific concept - used ONLY for casualty marker visibility. It is
# deliberately narrower than, and independent from, INCIDENT_ACTIVE_STATUSES
# below (Phase 7B.2) - the two concepts diverged once the simulation's
# actual evacuation model became clear: a casualty can be en route
# ("Being Evacuated") without a marker of its own, while its incident is
# still correctly Active because the evacuation mission isn't finished.
# Do not reuse this constant for incident lifecycle - see
# INCIDENT_ACTIVE_STATUSES for that.
# --------------------------------------------------------------------------
BATTLEFIELD_PRESENT_STATUSES: frozenset[str] = frozenset({
    # A casualty still at the incident, not yet moving toward a
    # facility - no vehicle has picked them up yet. Today's only
    # pre-evacuation status; add further ones on their own line here as
    # future phases introduce them.
    "Awaiting Transport",
})


# --------------------------------------------------------------------------
# INCIDENT LIFECYCLE (Phase 7B, refined 7B.1, refined 7B.2)
#
# Incident-active state, derived dynamically every call - never stored,
# never cached, no schema change. This is a CONCEPT, not a status name,
# and it is deliberately NOT "physical battlefield presence" (that
# concept belongs to casualty marker visibility - see
# BATTLEFIELD_PRESENT_STATUSES above, Phase 7C). An incident is Active
# while at least one of its casualties has not yet reached a treatment
# facility - i.e. the evacuation mission for that incident is still
# underway, whether or not a vehicle has physically collected them yet.
# Once every casualty has reached treatment (or beyond), the evacuation
# mission for that incident is complete and it becomes Resolved. This
# says nothing about medical treatment progress itself, only whether the
# incident's evacuation mission is still ongoing.
#
# Phase 7B.2 refinement: the original definition ("still physically on
# the battlefield") assumed an intermediate "awaiting pickup" state that
# this simulation doesn't model - a casualty goes straight from
# "Awaiting Transport" to "Being Evacuated" to "Under Treatment" the
# instant a vehicle is available, with no separate holding state. Under
# the old definition, an incident could read as Resolved moments after
# being created, as soon as its first casualty was picked up - before
# the evacuation mission had actually finished. The concept is now
# mission-based rather than location-based, matching how this
# simulation's transport model actually behaves.
#
# INCIDENT_ACTIVE_STATUSES below is THE single definition of "the
# evacuation mission for this incident is still ongoing" - every
# casualty status representing "not yet at a treatment facility" belongs
# in this one set, and nothing else in this file (or anywhere else in
# the provider) hardcodes that assumption independently.
# _active_incident_ids() and _derive_incidents() are driven entirely by
# membership in this set, so extending the concept - e.g. a future
# simulation phase introducing new pre-treatment statuses - is a
# one-line addition here, not a change anywhere else.
# --------------------------------------------------------------------------
INCIDENT_ACTIVE_STATUSES: frozenset[str] = frozenset({
    # Not yet moving toward a facility - no vehicle has picked them up
    # yet. The evacuation mission hasn't started moving this casualty.
    "Awaiting Transport",
    # En route to a facility - the evacuation mission for this casualty
    # is actively underway, even though (per Phase 7C) they no longer
    # have a battlefield marker of their own once picked up.
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

    Phase 7B (refined 7B.2): each incident also gets an `incident_state`
    field - "Active" if any of its casualties have not yet reached a
    treatment facility, i.e. the evacuation mission is still ongoing (see
    INCIDENT_ACTIVE_STATUSES / _active_incident_ids()), otherwise
    "Resolved". Derived fresh from casualties_db (already passed into
    get_map_data() - no new query) on every call; never stored, never
    cached. The renderer consumes this field but never recomputes it -
    see tactical_map.py's Phase 7D note.
    """
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
    """
    Casualties get a battlefield marker ONLY while they are still
    physically present at the incident - Phase 7C's battlefield/medical
    separation: a casualty that has entered a vehicle, or is inside a
    facility, is no longer a battlefield object, even though it still
    exists and continues through treatment. The transporting vehicle (see
    _resolve_dispatched_positions()) is that casualty's visible
    representation from the moment evacuation begins onward.

    Uses BATTLEFIELD_PRESENT_STATUSES - this function's own dedicated
    "still physically at the incident" definition. As of Phase 7B.2, this
    is intentionally DIFFERENT from, and independent of,
    INCIDENT_ACTIVE_STATUSES (which drives incident_state in
    _derive_incidents()): a casualty who is "Being Evacuated" no longer
    gets a marker here, but still keeps their incident Active, because
    the evacuation mission for that incident isn't finished yet even
    though that specific casualty has already been picked up. Marker
    visibility and incident_state are deliberately allowed to disagree -
    they answer two different questions ("is this casualty still
    physically here?" vs. "is this incident's evacuation mission still
    ongoing?").
    """

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
  
 
# --------------------------------------------------------------------------
# STAGING_BASE_LAYOUT (Phase 5B, placement refined in Phase 5C)
#
# THE single configuration for the three aggregate Operational Staging
# Base markers. Unlike RESOURCE_DEPLOYMENT_LAYOUT above (which spreads
# INDIVIDUAL idle-unit markers across multiple points and is currently
# unused while Phase 5A hides idle units), this defines exactly ONE
# fixed position per resource type representing where that type's
# entire reserve is staged. These positions are also the intended
# origin point for Phase 6's vehicle-movement animation.
#
# Phase 5C: previously all three sat on one shared vertical centerline
# (x=50), which read as three stacked dots rather than real
# infrastructure. Placement is triangulated across the AO, following
# battlefield logistics rather than a single line.
#
# Phase 7A: re-tuned again - the Phase 5C positions put Forward Ambulance
# Staging only ~15 units from RAP and Medical Reserve only ~20 units from
# ADS (on a 0-100 grid), which read as visually overlapping/crowded at
# render time. All three staging bases now sit on the AO's open west
# flank (clear of the RAP-ADS-HMV-FDC column entirely) except Air MEDEVAC
# Base, which stays on the east flank as before - every staging base is
# now >26 grid units from every facility AND from the other two staging
# bases (verified pairwise), while keeping the same doctrinal intent:
#   - Forward Ambulance Staging: forward deployment, west flank, near
#     RAP's shallow depth without sitting close enough to overlap it.
#   - Medical Reserve: central support position at the depth between
#     ADS and HMV, pushed onto the open west flank rather than sitting
#     directly beside ADS on the evacuation-chain column.
#   - Air MEDEVAC Base: rear operational area, east flank - clearly
#     separated from the hospital column, its own dedicated aviation
#     support area rather than another point near HMV/FDC.
# (Facility reference depths: front line y=2-5, RAP y=8, ADS y=25,
# HMV y=55, FDC y=85 - see FACILITY_CONFIG.)
#
# `subtitle` is a short, static, doctrine-flavored descriptor used by the
# renderer for both the tooltip and the popup (see
# tactical_map._add_staging_bases_layer) - purely a display label, not
# involved in count computation.
# --------------------------------------------------------------------------
STAGING_BASE_LAYOUT: dict[str, dict] = {
    "ambulance": {
        "label": "Forward Ambulance Staging",
        "subtitle": "Ground Evacuation Reserve",
        "resource_label": "Ambulances",
        "grid_x": 5.0,
        "grid_y": 30.0,
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
        "grid_x": 88.0,
        "grid_y": 52.0,
    },
}


def _build_staging_bases(ambulances_db: list, helicopters_db: list, medical_teams_db: list) -> list[dict]:
    """
    Build the three Operational Staging Base marker objects, one per
    resource type, each carrying a LIVE count of that type's currently
    "Available" (idle) units.

    Counts are computed fresh from the same *_db lists get_map_data()
    already receives every render - no separate query, no cached/stale
    state, and no dependency on RENDERED_RESOURCE_STATUSES (staging-base
    counts must reflect availability regardless of whether individual
    idle markers are being rendered). This counting logic is unchanged
    from Phase 5B - Phase 5C only refines placement/labels above and
    presentation in tactical_map.py.

    Each returned dict includes `type` ("ambulance"/"helicopter"/
    "medical_team") and its fixed (grid_x, grid_y) origin - the shape a
    future Phase 6 animation would key off of to find each resource
    type's departure point.
    """
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


# --------------------------------------------------------------------------
# RENDERED_RESOURCE_STATUSES (Phase 5A)
#
# THE single switch controlling which resource statuses get a tactical-map
# marker at all. Only ambulances/helicopters/medical teams whose status is
# in this list are included in MapData - anything else (currently
# "Available") is filtered out entirely before markers are ever built, so
# the map emphasizes active operations rather than idle fleet.
#
# This does NOT affect resource availability, dispatch eligibility, or any
# other simulation state - crud still reports every resource normally to
# the Resource page, Dashboard, Fleet Status, and AI assessment. It only
# controls what get_map_data() includes in the MapData it hands to the
# renderer.
#
# Reversible in one line: add "Available" back to this list to resume
# rendering idle resources (they'll reuse the existing Phase 5
# RESOURCE_DEPLOYMENT_LAYOUT / _resolve_idle_deployment_positions logic
# below without any further changes).
# --------------------------------------------------------------------------
RENDERED_RESOURCE_STATUSES: list[str] = ["Dispatched"]


# --------------------------------------------------------------------------
# Phase 6B - live vehicle movement interpolation
#
# Three small helpers, each doing exactly one thing, chained together by
# get_map_data() below:
#   1. _build_facility_id_to_position() - ONE crud query for the whole
#      call (crud.get_all_facilities()), building facility_id -> (x, y).
#      Never called per-vehicle.
#   2. _build_casualty_destination_lookup() - casualty_id -> (x, y),
#      built once from casualties_db (already passed into get_map_data())
#      plus the facility map from step 1. Zero additional queries.
#   3. _interpolate_dispatched_position() - pure O(1) computation per
#      vehicle: origin + destination + dispatch_time/release_time +
#      current_time -> a live (x, y), or None if anything required is
#      missing/invalid (the caller then falls back to the existing
#      placeholder positioning for that one vehicle).
#
# Overall cost per get_map_data() call: 1 query (step 1) + O(casualties)
# (step 2) + O(dispatched vehicles) (step 3) - never O(vehicles) queries.
# --------------------------------------------------------------------------

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
    """
    casualty_id -> incident/pickup location (grid_x, grid_y) - Phase 6C's
    Leg 1 destination and Leg 2 origin. Built once from casualties_db
    (already passed into get_map_data()): every Casualty row already
    carries its own grid_x/grid_y (the incident location it was
    generated at), so this requires ZERO new backend metadata and zero
    new queries - reusing existing data, exactly as instructed.
    """
    return {
        casualty.casualty_id: (casualty.grid_x, casualty.grid_y)
        for casualty in casualties_db
        if casualty.grid_x is not None and casualty.grid_y is not None
    }


# Phase 6C: how long a vehicle visibly pauses at the incident to simulate
# casualty loading. Simple and configurable - no animation, no countdown,
# the vehicle just holds position for this many simulated seconds. Capped
# by MAX_PICKUP_FRACTION_OF_TRIP so an unusually short total trip (e.g. a
# Helicopter->RAP hop) can never have pickup consume the whole window and
# leave no time to actually travel either leg.
PICKUP_DURATION_SECONDS: float = 120.0
MAX_PICKUP_FRACTION_OF_TRIP: float = 0.3


def _lerp_point(
    start: tuple[float, float],
    end: tuple[float, float],
    progress: float,
) -> tuple[float, float]:
    """
    The one shared linear-interpolation primitive. Given an already-
    clamped [0.0, 1.0] progress fraction, returns the point that fraction
    of the way from `start` to `end`. Used by both travel legs in
    _interpolate_dispatched_position() below - the actual interpolation
    math exists in exactly this one place, per Phase 6C's requirement to
    reuse rather than duplicate Phase 6B's approach.
    """
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
    """
    Compute a single dispatched vehicle's live position across its full
    two-leg journey (Phase 6C): Origin -> Incident (Leg 1), a brief
    stationary pickup hold at the incident, then Incident -> destination
    Facility (Leg 2). Returns None (never raises) if anything required is
    missing or invalid - the caller then falls back to the existing
    placeholder positioning for that one vehicle (legacy rows, unmigrated
    databases, unresolved incident/destination, malformed timestamps, or
    current_time simply not having been supplied yet all degrade
    gracefully rather than crash or guess).

    Both legs share the SAME total window Phase 6B already established:
    dispatch_time -> release_time (== TRANSPORT_TIME[vehicle_type][facility_code],
    completely untouched by this phase). This function only decides how
    that existing duration is visually spent - split proportionally to
    each leg's straight-line distance, with PICKUP_DURATION_SECONDS
    (clamped to MAX_PICKUP_FRACTION_OF_TRIP of the total) reserved at the
    incident in between. No travel time changed, no new backend metadata
    used - just origin_grid_x/origin_grid_y (Phase 6A), Casualty.grid_x/
    grid_y (already existed), and the destination facility position
    (Phase 6B).
    """
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
    """
    Resolve a live position for every Dispatched unit in `units`, in the
    same order as `units`. Tries _interpolate_dispatched_position() per
    unit first (now the full two-leg Phase 6C journey); any unit it can't
    resolve (missing metadata, no resolvable incident/destination,
    current_time not supplied) falls back to the pre-Phase-6B placeholder
    - staged near the active incident, spread so co-located fallback
    units don't overlap. Interpolated and fallback units can coexist in
    the same call; each is handled per-unit, not as an all-or-nothing
    batch.
    """
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
    THE single map data provider. Packages simulation.py's existing mock
    state into one fully-resolved MapData object — the only thing
    render_tactical_map() depends on.
 
    Args:
        facility_status: simulation.py's existing FACILITY_STATUS list.
        resource_status: simulation.py's existing RESOURCE_STATUS list.
        mission_log_entries: simulation.py's existing MISSION_LOG_ENTRIES
                              list (used to derive incidents — see
                              _derive_incidents()).
        current_time: the live simulation clock's current_time (Phase 6B).
                      Optional and defaulting to None so this remains
                      backward compatible with any existing caller that
                      hasn't been updated yet — when None, dispatched
                      ambulances/helicopters simply keep the pre-Phase-6B
                      placeholder positioning (see
                      _resolve_dispatched_positions()) instead of
                      interpolating. Pass clock.current_time to enable
                      live movement.
 
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
 
    incidents = _derive_incidents(incidents_db, casualties_db)
    casualties = _derive_casualties(casualties_db)
    routes = _derive_routes(casualties_db)
    staging_bases = _build_staging_bases(ambulances_db, helicopters_db, medical_teams_db)

    # Phase 6B/6C: built once per call (one crud query total, not per-
    # vehicle - see _build_facility_id_to_position()'s docstring), and
    # only when there's actually a current_time to interpolate against.
    # When current_time is None, skip this entirely -
    # _resolve_dispatched_positions() will fall back to placeholder
    # positioning for every unit anyway. casualty_incident_position
    # (Phase 6C's Leg 1 destination / Leg 2 origin) needs no crud query
    # at all - it's built straight from casualties_db's own grid_x/grid_y.
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
            # Idle ambulances: fixed, deterministic deployment slots
            # (RESOURCE_DEPLOYMENT_LAYOUT) instead of one shared point.
            positions = _resolve_idle_deployment_positions("ambulance", units)
        else:
            # Dispatched ambulances (Phase 6B): live interpolated position
            # per unit, falling back to the pre-Phase-6B placeholder
            # (staged near the active incident) for any unit missing the
            # metadata needed to interpolate. See
            # _resolve_dispatched_positions()'s docstring.
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
            # Idle helicopters: fixed, deterministic deployment slots
            # (RESOURCE_DEPLOYMENT_LAYOUT) instead of one shared point.
            positions = _resolve_idle_deployment_positions("helicopter", units)
        else:
            # Dispatched helicopters (Phase 6B): live interpolated
            # position per unit, falling back to the pre-Phase-6B
            # placeholder (staged near the active incident) for any unit
            # missing the metadata needed to interpolate. See
            # _resolve_dispatched_positions()'s docstring.
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