"""
tactical_map.py
 
Dedicated, reusable Battlefield Map component for the Simulation page.
Kept out of simulation.py per "avoid putting all map logic inside
simulation.py... create a dedicated reusable Battlefield Map component."
 
ARCHITECTURE — provider / renderer split
-----------------------------------------------------------------------
get_map_data(...)      the ONE provider — now defined in
                        components/map_adapter.py and imported here.
                        Takes simulation.py's existing mock state
                        (FACILITY_STATUS, RESOURCE_STATUS,
                        MISSION_LOG_ENTRIES) and returns a single MapData
                        object with every coordinate already resolved.
                        This is the ONLY function that knows where data
                        comes from.
render_tactical_map(map_data)
                        the renderer, defined in this file. Takes ONE
                        MapData object and draws it. It has no idea
                        whether that MapData was built from frontend mock
                        state or, later, from live backend queries — it
                        just renders whatever it's given. When backend
                        integration happens, only map_adapter.py's
                        get_map_data() (or a new provider with the same
                        MapData return shape) needs to change; this
                        function does not.
 
Nothing in this file duplicates a "simulation concept" that already
exists in simulation.py: incidents are DERIVED from MISSION_LOG_ENTRIES's
own "Incident"-category entries (not a second, separately-maintained
incident list), and facility/resource identity, names, and stats are
read directly from FACILITY_STATUS/RESOURCE_STATUS, never copied.
 
Scope for this phase: interactive map, Facilities, Incident, Ambulances,
Helicopters, Medical Teams, Operational Staging Bases (Phase 5B),
layer control, popups, an in-map legend, and a Center Map control. NOT
this phase: Evacuation Routes, live tracking, animation, or backend
integration — still entirely frontend-only.
 
No backend imports of any kind.
"""
 
from __future__ import annotations

import folium
from branca.element import MacroElement, Template
import streamlit as st
from streamlit_folium import st_folium

from components.buttons import secondary_button
from components.map_constants import FRONTEND_MAP_LAYOUT
from components.map_adapter import MapData, get_map_data
 
 
# --------------------------------------------------------------------------
# COLOR PALETTE (Phase 7A: consolidated to hex)
#
# Previously each layer had a Folium *named* color (feeding folium.Icon)
# PLUS a separate "approximate hex" swatch for the legend, which could
# drift out of sync. Now that markers are custom DivIcon badges (see
# _build_badge_icon()/_build_staging_base_icon() below), any hex value
# works directly as a marker's fill color - so each layer has exactly
# ONE color value, used for both the marker AND the legend swatch. This
# is the single biggest lever for goal 6 (visual consistency): one
# source of truth per color, not two.
# --------------------------------------------------------------------------
LAYER_COLOR: dict[str, str] = {
    "facility": "#2A81CB", "incident": "#CB2B3E", "ambulance": "#2AAD27",
    "helicopter": "#CB8427", "medical_team": "#3D6570",
}
LAYER_ICON_SYMBOL: dict[str, str] = {
    "facility": "plus-square", "incident": "exclamation-triangle", "ambulance": "ambulance",
    "helicopter": "plane", "medical_team": "user-md",
}
# Backward-compatible alias - the legend reads swatches from the exact
# same dict markers are colored from now, so this is just LAYER_COLOR
# under its previous name; nothing computes a second, separate value.
LEGEND_SWATCH_COLOR: dict[str, str] = LAYER_COLOR

# Facility marker color by operational status (icon symbol stays
# "plus-square" for all three - only color changes, so a facility always
# reads as "a facility," with color carrying the urgency signal).
FACILITY_STATUS_COLOR: dict[str, str] = {
    "Operational": "#2AAD27", "Busy": "#CB8427", "High Load": "#CB8427", "Critical": "#CB2B3E",
}

# Resource unit marker color by status, applied uniformly across
# Ambulances/Helicopters/Medical Teams so the same colors always mean the
# same statuses regardless of resource type. "Available" keeps each
# layer's own base type color (None below means "use the base").
RESOURCE_STATUS_COLOR: dict[str, str | None] = {
    "Available": None, "Busy": "#8B5FBF", "Returning": "#6FA8D6", "Maintenance": "#6B7280",
}

# Casualty severity -> color. Minor->Critical is an escalating color
# ladder - also drives marker SIZE (see MARKER_SIZE_PX below), so the
# most severe casualties are simultaneously the reddest AND the largest.
CASUALTY_SEVERITY_COLOR: dict[str, str] = {
    "Minor": "#8FBC6B", "Moderate": "#CB8427", "Severe": "#E0774F", "Critical": "#8B1E1E",
}
CASUALTY_ICON_SYMBOL: str = "plus"

# Operational Staging Base markers (Phase 5B, refined 5C/7A) - aggregate
# reserve infrastructure. Phase 7A gives staging bases their own DISTINCT
# MARKER SHAPE (a diamond badge - see _build_staging_base_icon()), not
# just a different color/icon glyph on the same teardrop pin every other
# layer uses. That shape difference is what actually solves "staging
# bases look too similar to medical facilities": the previous fix (black
# + a unique "flag" glyph) still used the identical pin silhouette
# Facilities use, so at a glance - before reading the glyph - they read
# as "yet another pin." A diamond never does.
STAGING_BASE_COLOR: str = "#2B2B2B"
STAGING_BASE_ICON_SYMBOL: str = "flag"

# Operational-status wording shown in the staging-base popup, derived
# purely from the already-computed available_count (no new counting
# logic - see map_adapter._build_staging_bases). Colors reuse the same
# muted green/red already used for casualty severity, so status doesn't
# introduce a new bright color into the palette.
STAGING_BASE_STATUS_COLOR: dict[str, str] = {
    "READY": "#8FBC6B", "DEPLETED": "#8B1E1E",
}


# Evacuation route styling by transport mode - color + dash pattern so
# Ground/Air are distinguishable even without hovering for the popup.
# Phase 7A: routes are now the lowest tier in the visual hierarchy (see
# MARKER_SIZE_PX/z-order below) - thinner and slightly translucent so
# they read as background connective context, not competing with markers.
ROUTE_TRANSPORT_STYLE: dict[str, dict] = {
    "Ground": {"color": "#4A6FA5", "dash_array": None},
    "Air": {"color": "#8B5FBF", "dash_array": "8,6"},
}
ROUTE_LEGEND_COLOR: dict[str, str] = {"Ground": "#4A6FA5", "Air": "#8B5FBF"}
ROUTE_LINE_WEIGHT: float = 2.0
ROUTE_LINE_OPACITY: float = 0.65

# --------------------------------------------------------------------------
# MARKER SIZE HIERARCHY (Phase 7A, goals 1 & 2)
#
# THE single place the map's entire visual hierarchy is expressed as
# numbers. Every _add_*_layer() function below reads its marker size from
# here - nothing hardcodes its own size - so the hierarchy is tunable in
# one spot and every layer stays proportionally consistent (goal 6).
#
# Priority order (largest -> smallest), matching the requested hierarchy:
#   Active Incidents > Casualties (severity-scaled) > Moving Vehicles
#   (Ambulances/Helicopters - everything currently rendered IS actively
#   dispatched, since idle units are hidden per Phase 5A) > Medical
#   Teams (facility-support resource, not a moving vehicle, so sized
#   nearer Facilities) > Medical Facilities > Operational Staging Bases.
# Routes carry no marker size - see ROUTE_LINE_WEIGHT/OPACITY above,
# their own de-emphasis mechanism as a line layer rather than a point.
# --------------------------------------------------------------------------
MARKER_SIZE_PX: dict[str, int] = {
    "incident": 44,
    "casualty_critical": 36,
    "casualty_severe": 32,
    "casualty_moderate": 28,
    "casualty_minor": 24,
    "vehicle": 32,
    "medical_team": 26,
    "facility": 28,
    "staging_base": 26,
}
# Fixed ratio of glyph size to badge size, used by every badge - the
# actual mechanism behind "standardize icon proportions" (goal 6): one
# ratio, applied everywhere, rather than each layer picking its own.
ICON_GLYPH_RATIO: float = 0.44

# --------------------------------------------------------------------------
# INCIDENT STATE STYLE (Phase 7D)
#
# THE single place Active vs. Resolved visual treatment is defined for
# incidents. The provider (map_adapter.py) already computes
# incident["incident_state"] (Phase 7B) - this renderer CONSUMES that
# value only; it never recomputes or infers it from casualty data itself.
#
# Active keeps today's baseline (full "incident" size tier, full color,
# full opacity, a bold border) - already the largest, most emphatic
# marker on the map per the Phase 7A hierarchy, so no change is needed
# there to "attract attention." Resolved is deliberately de-emphasized
# via several subtle, non-animated cues at once (smaller size, a muted
# same-family color rather than a new bright one, reduced opacity, a
# thinner border) so it visibly recedes into operational background
# context without disappearing or introducing any civilian-bright color,
# flashing, or animation.
# --------------------------------------------------------------------------
INCIDENT_STATE_STYLE: dict[str, dict] = {
    "Active": {
        "size_px": MARKER_SIZE_PX["incident"],
        "color": LAYER_COLOR["incident"],
        "opacity": 1.0,
        "border_px": 3,
        "border_color": "#0F1520",
    },
    "Resolved": {
        "size_px": round(MARKER_SIZE_PX["incident"] * 0.7),
        "color": "#8B4F55",
        "opacity": 0.55,
        "border_px": 1,
        "border_color": "#3A2426",
    },
}
 
 
# --------------------------------------------------------------------------
# MARKER BUILDERS (Phase 7A)
#
# Two shape families, deliberately different, per goal 4:
#   - _build_badge_icon(): a circular badge. Used by every "actor/point
#     of interest" layer - Facilities, Incidents, Casualties, Ambulances,
#     Helicopters, Medical Teams. This is the shared, consistent family
#     goal 6 asks for: one shape, one size mechanism, one glyph-to-badge
#     ratio (ICON_GLYPH_RATIO), across all six of those layers.
#   - _build_staging_base_icon(): a diamond badge (a square rotated 45
#     degrees, with the inner glyph counter-rotated so it stays upright).
#     Used ONLY by Operational Staging Bases, so they read as permanent
#     support infrastructure at a glance - a different silhouette, not
#     just a different color, which is what actually fixes goal 4.
#
# Both replace folium.Icon() (Leaflet's AwesomeMarkers), which renders
# every marker at one fixed pixel size with no size parameter at all -
# the reason goal 2 (marker sizing) requires this change. Popups and
# tooltips attach to folium.Marker exactly as before; only the `icon=`
# argument changes from an Icon to a DivIcon.
# --------------------------------------------------------------------------
 
def _build_badge_icon(icon_symbol: str, color: str, size_px: int) -> folium.DivIcon:
    """Circular badge marker: a Font Awesome glyph centered on a solid-color circle, sized in pixels."""
    icon_px = round(size_px * ICON_GLYPH_RATIO)
    html = (
        f'<div style="'
        f'width:{size_px}px;height:{size_px}px;'
        f'background:{color};'
        f'border:2px solid #0F1520;'
        f'border-radius:50%;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.55);'
        f'display:flex;align-items:center;justify-content:center;'
        f'">'
        f'<i class="fa fa-{icon_symbol}" style="font-size:{icon_px}px;color:#F4F6F8;"></i>'
        f'</div>'
    )
    half = size_px // 2
    return folium.DivIcon(html=html, icon_size=(size_px, size_px), icon_anchor=(half, half))
 
 
def _build_staging_base_icon(icon_symbol: str, color: str, size_px: int) -> folium.DivIcon:
    """
    Diamond badge marker (a rotated square) for Operational Staging
    Bases only - a distinct SHAPE family from every other layer's
    circular badge, so staging bases never read as "another facility" or
    "another vehicle," satisfying goal 4 directly. The inner glyph is
    counter-rotated so it displays upright despite the diamond rotation.
    """
    icon_px = round(size_px * ICON_GLYPH_RATIO)
    html = (
        f'<div style="'
        f'width:{size_px}px;height:{size_px}px;'
        f'background:{color};'
        f'border:2px solid #F4F6F8;'
        f'transform:rotate(45deg);'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.55);'
        f'display:flex;align-items:center;justify-content:center;'
        f'">'
        f'<i class="fa fa-{icon_symbol}" style="font-size:{icon_px}px;color:#F4F6F8;transform:rotate(-45deg);"></i>'
        f'</div>'
    )
    half = size_px // 2
    return folium.DivIcon(html=html, icon_size=(size_px, size_px), icon_anchor=(half, half))
 
 
def _build_incident_icon(icon_symbol: str, style: dict) -> folium.DivIcon:
    """
    Circular badge for Active/Resolved incidents (Phase 7D) - a dedicated
    builder, deliberately separate from _build_badge_icon(), so this
    phase's opacity/border-weight differentiation can never affect
    Facilities/Casualties/Vehicles/Medical Teams, which keep using
    _build_badge_icon() completely unchanged.
 
    `style` is one entry from INCIDENT_STATE_STYLE - size, color, opacity,
    and border weight all come from there, never computed here. This
    function only turns that already-decided style into a marker; it does
    not decide Active vs. Resolved itself.
    """
    size_px = style["size_px"]
    icon_px = round(size_px * ICON_GLYPH_RATIO)
    html = (
        f'<div style="'
        f'width:{size_px}px;height:{size_px}px;'
        f'background:{style["color"]};'
        f'opacity:{style["opacity"]};'
        f'border:{style["border_px"]}px solid {style["border_color"]};'
        f'border-radius:50%;'
        f'box-shadow:0 1px 3px rgba(0,0,0,0.55);'
        f'display:flex;align-items:center;justify-content:center;'
        f'">'
        f'<i class="fa fa-{icon_symbol}" style="font-size:{icon_px}px;color:#F4F6F8;"></i>'
        f'</div>'
    )
    half = size_px // 2
    return folium.DivIcon(html=html, icon_size=(size_px, size_px), icon_anchor=(half, half))
 
 
def _popup_html(title: str, accent_color: str, lines: list[str]) -> str:
    """
    Standardized popup content wrapper (goal 6) - every layer's popup
    calls this instead of hand-assembling its own <b>/<br> markup, so
    font, size, spacing, and title-accent styling are identical across
    Facilities, Incidents, Vehicles, Casualties, Staging Bases, and
    Routes. Only `title`, `accent_color` (that layer's own color token),
    and the content `lines` differ per layer - none of them re-declare
    typography.
    """
    body = "<br>".join(lines)
    return (
        f'<div style="font-family:sans-serif;font-size:12.5px;line-height:1.65;'
        f'color:#1A1A1A;min-width:150px;">'
        f'<div style="font-weight:700;font-size:13.5px;color:{accent_color};'
        f'margin-bottom:4px;">{title}</div>'
        f'{body}'
        f'</div>'
    )
 
 
def _build_base_map() -> folium.Map:
    bounds = FRONTEND_MAP_LAYOUT["bounds"]

    tactical_map = folium.Map(
        location=list(FRONTEND_MAP_LAYOUT["center"]),
        zoom_start=3,
        min_zoom=2,
        max_zoom=8,
        crs="Simple",
        tiles=None,
        zoomSnap=0.25,
        zoomDelta=0.25,
    )
 
    folium.Rectangle(
        bounds=[[bounds["min_y"], bounds["min_x"]], [bounds["max_y"], bounds["max_x"]]],
        color="#2B4154", weight=1, fill=True, fill_color="#0F1520", fill_opacity=1.0,
        interactive=False,
    ).add_to(tactical_map)
 
    grid_line_color = "#1C2733"
    for step in range(0, 101, 10):
        folium.PolyLine(
            [[bounds["min_y"], step], [bounds["max_y"], step]],
            color=grid_line_color, weight=1, opacity=0.6, interactive=False,
        ).add_to(tactical_map)
        folium.PolyLine(
            [[step, bounds["min_x"]], [step, bounds["max_x"]]],
            color=grid_line_color, weight=1, opacity=0.6, interactive=False,
        ).add_to(tactical_map)
    bounds = FRONTEND_MAP_LAYOUT["bounds"]

    tactical_map.fit_bounds(
        [
            [bounds["min_y"], bounds["min_x"]],
            [bounds["max_y"], bounds["max_x"]],
        ]
    )
 
    return tactical_map
 
 
def _add_legend(tactical_map: folium.Map) -> None:
    """
    Embed the legend inside the map itself (a fixed-position overlay in
    the map's own corner) instead of a caption below it - the standard
    Folium technique for this is a branca MacroElement/Template injected
    into the map's root, since Folium has no built-in legend widget.
    """
    rows = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="color:{color};">&#9679;</span>&nbsp;{label}'
        f'</div>'
        for color, label in (
            (LEGEND_SWATCH_COLOR["facility"], "Medical Facility"),
            (INCIDENT_STATE_STYLE["Active"]["color"], "Active Incident"),
            (INCIDENT_STATE_STYLE["Resolved"]["color"], "Resolved Incident"),
            (LEGEND_SWATCH_COLOR["ambulance"], "Ambulance"),
            (LEGEND_SWATCH_COLOR["helicopter"], "Helicopter"),
            (LEGEND_SWATCH_COLOR["medical_team"], "Medical Team"),
            (STAGING_BASE_COLOR, "Operational Staging Base"),
        )
    )
    severity_rows = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="color:{CASUALTY_SEVERITY_COLOR[severity]};">&#9679;</span>&nbsp;Casualty - {severity}'
        f'</div>'
        for severity in ("Minor", "Moderate", "Severe", "Critical")
    )
    route_rows = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="color:{ROUTE_LEGEND_COLOR[mode]};">&#9473;&#9473;</span>&nbsp;{mode} Evacuation'
        f'</div>'
        for mode in ("Ground", "Air")
    )
    legend_html = (
        "{% macro html(this, kwargs) %}"
        '<div style="'
        "position:fixed;bottom:24px;left:24px;z-index:9999;"
        "background:rgba(15,21,32,0.92);color:#F4F6F8;"
        "padding:10px 14px;border-radius:6px;border:1px solid #2B4154;"
        'font-size:12px;line-height:1.6;font-family:sans-serif;">'
        '<b style="font-size:12px;">Legend</b>'
        f"{rows}"
        f"{severity_rows}"
        f"{route_rows}"
        "</div>"
        "{% endmacro %}"
    )
    legend = MacroElement()
    legend._template = Template(legend_html)
    tactical_map.get_root().add_child(legend)


def _add_facilities_layer(feature_group: folium.FeatureGroup, facilities: list[dict]) -> None:
    """Medical Facilities: circular badge, status-colored, fixed 'facility' size tier - a permanent treatment location, not a moving actor."""
    for facility in facilities:
        available_beds = facility["capacity"] - facility["occupied"]
        color = FACILITY_STATUS_COLOR.get(facility["status"], LAYER_COLOR["facility"])
        popup_html = _popup_html(
            facility["name"], color,
            [
                facility["full_name"],
                f"Status: {facility['status']}",
                f"Capacity: {facility['capacity']}",
                f"Occupied: {facility['occupied']}",
                f"Available Beds: {available_beds}",
                f"Waiting: {facility['waiting']}",
                f"Avg. Treatment: {facility['avg_treatment']}",
            ],
        )
        folium.Marker(
            location=[facility["grid_y"], facility["grid_x"]],
            tooltip=f"{facility['name']} \u2014 {facility['status']}",
            popup=folium.Popup(popup_html, max_width=260),
            icon=_build_badge_icon(LAYER_ICON_SYMBOL["facility"], color, MARKER_SIZE_PX["facility"]),
        ).add_to(feature_group)


def _add_incidents_layer(feature_group: folium.FeatureGroup, incidents: list[dict]) -> None:
    """
    Active Incidents. Phase 7D: visual treatment now depends on the
    provider-supplied `incident["incident_state"]` (Phase 7B) - this
    function CONSUMES that value only, via INCIDENT_STATE_STYLE; it never
    computes or infers Active/Resolved itself. Falls back to the Active
    style if `incident_state` is missing or an unrecognized value (never
    crash, and default toward MORE visible rather than silently hiding an
    incident that should have attention).
    """
    for incident in incidents:
        incident_state = incident.get("incident_state", "Active")
        style = INCIDENT_STATE_STYLE.get(incident_state, INCIDENT_STATE_STYLE["Active"])
        title = f"Incident \u2014 Sector {incident['battle_sector']} ({incident_state})"
        popup_html = _popup_html(
            f"Incident \u2014 Sector {incident['battle_sector']}", style["color"],
            [
                f"Casualties: {incident['casualty_count']}",
                incident["description"],
                f'Status: <span style="color:{style["color"]};font-weight:600;">{incident_state.upper()}</span>',
            ],
        )
        folium.Marker(
            location=[incident["grid_y"], incident["grid_x"]],
            tooltip=title,
            popup=folium.Popup(popup_html, max_width=260),
            icon=_build_incident_icon(LAYER_ICON_SYMBOL["incident"], style),
        ).add_to(feature_group)


def _add_units_layer(feature_group: folium.FeatureGroup, units: list[dict], unit_type_label: str, layer_key: str) -> None:
    """
    Ambulances/Helicopters/Medical Teams. Ambulances and Helicopters use
    the "vehicle" size tier (everything rendered here is actively
    Dispatched, per Phase 5A - a moving vehicle, sized accordingly).
    Medical Teams are a facility-support resource, not a moving vehicle,
    so they use their own, slightly smaller "medical_team" tier - closer
    to Facilities than to Ambulances/Helicopters in visual weight.
    """
    size_px = MARKER_SIZE_PX["medical_team"] if layer_key == "medical_team" else MARKER_SIZE_PX["vehicle"]
    for unit in units:
        status_color = RESOURCE_STATUS_COLOR.get(unit["status"])
        color = status_color if status_color else LAYER_COLOR[layer_key]
        popup_html = _popup_html(
            unit["call_sign"], color,
            [f"Type: {unit_type_label}", f"Status: {unit['status']}"],
        )
        folium.Marker(
            location=[unit["grid_y"], unit["grid_x"]],
            tooltip=f"{unit['call_sign']} \u2014 {unit['status']}",
            popup=folium.Popup(popup_html, max_width=220),
            icon=_build_badge_icon(LAYER_ICON_SYMBOL[layer_key], color, size_px),
        ).add_to(feature_group)


def _add_staging_bases_layer(feature_group: folium.FeatureGroup, staging_bases: list[dict]) -> None:
    """
    Draws the aggregate Operational Staging Base markers (Phase 5B,
    presentation refined 5C/7A) - reserve-capacity indicators, NOT
    individual vehicles.

    Operational Status (READY/DEPLETED) is a pure display label derived
    here, at render time, from the already-computed available_count -
    it is NOT a new count and does not change what "available" means;
    it only decides which word to print for a count of zero vs. non-zero.
    All other content (label, subtitle, count, position) is rendered
    exactly as the provider computed it; no business logic lives here,
    matching every other _add_*_layer() function in this renderer.

    Uses _build_staging_base_icon() (diamond shape) rather than
    _build_badge_icon() (circle) - the deliberate shape difference from
    every other layer that solves goal 4.
    """
    for base in staging_bases:
        status_word = "READY" if base["available_count"] > 0 else "DEPLETED"
        status_color = STAGING_BASE_STATUS_COLOR[status_word]
        popup_html = _popup_html(
            base["label"], STAGING_BASE_COLOR,
            [
                f"<i>{base['subtitle']}</i>",
                f"Available Units: {base['available_count']}",
                f'Operational Status: <span style="color:{status_color};font-weight:600;">{status_word}</span>',
            ],
        )
        folium.Marker(
            location=[base["grid_y"], base["grid_x"]],
            tooltip=f"{base['label']} \u2014 {base['subtitle']}",
            popup=folium.Popup(popup_html, max_width=240),
            icon=_build_staging_base_icon(STAGING_BASE_ICON_SYMBOL, STAGING_BASE_COLOR, MARKER_SIZE_PX["staging_base"]),
        ).add_to(feature_group)


def _add_casualties_layer(feature_group: folium.FeatureGroup, casualties: list[dict]) -> None:
    """Casualties: severity drives BOTH color and size (see MARKER_SIZE_PX) - a Critical casualty is simultaneously the reddest and the largest, reinforcing urgency without a popup."""
    for casualty in casualties:
        severity = casualty["severity"]
        color = CASUALTY_SEVERITY_COLOR[severity]
        size_px = MARKER_SIZE_PX[f"casualty_{severity.lower()}"]
        popup_html = _popup_html(
            casualty["casualty_ref"], color,
            [f"Severity: {severity}", f"Sector: {casualty['battle_sector']}"],
        )
        folium.Marker(
            location=[casualty["grid_y"], casualty["grid_x"]],
            tooltip=f"{casualty['casualty_ref']} \u2014 {severity}",
            popup=folium.Popup(popup_html, max_width=200),
            icon=_build_badge_icon(CASUALTY_ICON_SYMBOL, color, size_px),
        ).add_to(feature_group)


def _add_routes_layer(feature_group: folium.FeatureGroup, routes: list[dict]) -> None:
    """Draws exactly what the provider derived - no route computation here. Thinner/translucent (ROUTE_LINE_WEIGHT/OPACITY) - the lowest tier in the visual hierarchy, background context rather than a competing marker."""
    for route in routes:
        style = ROUTE_TRANSPORT_STYLE[route["transport_mode"]]
        popup_html = _popup_html(
            route["segment"], style["color"],
            [f"Destination: {route['destination']}", f"Transport Mode: {route['transport_mode']}"],
        )
        start_y, start_x = route["start"][1], route["start"][0]
        end_y, end_x = route["end"][1], route["end"][0]
        folium.PolyLine(
            locations=[[start_y, start_x], [end_y, end_x]],
            color=style["color"],
            weight=ROUTE_LINE_WEIGHT,
            opacity=ROUTE_LINE_OPACITY,
            dash_array=style["dash_array"],
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"{route['segment']} ({route['transport_mode']})",
        ).add_to(feature_group)


def render_tactical_map(
    map_data: MapData,
    mode: str = "simulation",
) -> None:
    """
    The renderer. Draws exactly what `map_data` contains - Facilities,
    Incident, Ambulances, Helicopters, Medical Teams, Operational Staging
    Bases layers, a layer control, marker popups, an embedded legend, and
    a Center Map control. Has no knowledge of where map_data came from.

    Phase 7A: marker size and z-order now express a deliberate visual
    hierarchy (Active Incidents > Casualties > Moving Vehicles > Medical
    Teams > Medical Facilities > Operational Staging Bases > Routes) -
    see MARKER_SIZE_PX and the `layers` list below. This is purely a
    presentation choice; map_data's contents and this function's inputs
    are unchanged.
    """
    if mode in ("simulation", "dashboard"):
        counter_key = f"{mode}_tactical_map_reset_counter"
        st.session_state.setdefault(
            counter_key,
            0,
        )

        if secondary_button(
            "🎯 Center Map",
            key="tactical_map_center_button",
            use_container_width=False,
        ):
            st.session_state[counter_key] += 1
            st.rerun()
 
    tactical_map = _build_base_map()
 
    facilities_layer = folium.FeatureGroup(name="Medical Facilities", show=True)
    incidents_layer = folium.FeatureGroup(name="Active Incidents", show=True)
    casualties_layer = folium.FeatureGroup(name="Casualties", show=True)
    routes_layer = folium.FeatureGroup(name="Evacuation Routes", show=True)
    ambulances_layer = folium.FeatureGroup(name="Ambulances", show=True)
    helicopters_layer = folium.FeatureGroup(name="Helicopters", show=True)
    medical_teams_layer = folium.FeatureGroup(name="Medical Teams", show=True)
    staging_bases_layer = folium.FeatureGroup(name="Operational Staging Bases", show=True)
 
    _add_facilities_layer(
        facilities_layer,
        map_data.facilities,
    )

    _add_incidents_layer(
        incidents_layer,
        map_data.incidents,
    )

    _add_units_layer(
        ambulances_layer,
        map_data.ambulances,
        "Ambulance",
        "ambulance",
    )

    _add_units_layer(
        helicopters_layer,
        map_data.helicopters,
        "Helicopter",
        "helicopter",
    )

    _add_units_layer(
        medical_teams_layer,
        map_data.medical_teams,
        "Medical Team",
        "medical_team",
    )

    _add_staging_bases_layer(
        staging_bases_layer,
        map_data.staging_bases,
    )

    if mode == "simulation":
        _add_casualties_layer(
            casualties_layer,
            map_data.casualties,
        )

        _add_routes_layer(
            routes_layer,
            map_data.routes,
        )
 
    # Phase 7A (goal 3): z-order is simply "the order FeatureGroups are
    # added to the map" - Leaflet stacks later-added markers on top of
    # earlier ones. This list is deliberately ordered BOTTOM -> TOP to
    # match the requested visual hierarchy, so higher-priority markers
    # are never hidden beneath lower-priority ones: Routes (background
    # linework) -> Operational Staging Bases -> Medical Facilities ->
    # Medical Teams -> Ambulances -> Helicopters -> Casualties ->
    # Active Incidents (always topmost, per goal 1's priority order).
    layers = []

    if mode == "simulation":
        layers.append(routes_layer)

    layers.extend(
        [
            staging_bases_layer,
            facilities_layer,
            medical_teams_layer,
            ambulances_layer,
            helicopters_layer,
        ]
    )

    if mode == "simulation":
        layers.append(casualties_layer)

    layers.append(incidents_layer)

    for layer in layers:
        layer.add_to(tactical_map)
 
    if mode == "simulation":
        folium.LayerControl(
            collapsed=False
        ).add_to(tactical_map)

        _add_legend(tactical_map)
 
    # Dashboard and Simulation use different target heights.
    # panel() auto-sizes to its content, so the Folium map height
    # determines the rendered panel height.
    height = 760 if mode == "simulation" else 480

    map_key = (
        f"{mode}_tactical_map_"
        f"{st.session_state[counter_key]}"
    )

    st_folium(
        tactical_map,
        width="100%",
        height=height,
        returned_objects=[],
        key=map_key,
    )