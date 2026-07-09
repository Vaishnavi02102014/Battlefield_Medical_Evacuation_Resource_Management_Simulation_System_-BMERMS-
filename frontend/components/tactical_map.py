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
Helicopters, Medical Teams, layer control, popups, an in-map legend, and
a Center Map control. NOT this phase: Evacuation Routes, live tracking,
animation, or backend integration — still entirely frontend-only.
 
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
 
 
# Folium's built-in Icon() color palette is a fixed named set — these are
# the closest matches to the originally suggested colors (Facilities/
# Blue, Incidents/Red, Ambulances/Green, Helicopters/Orange, Medical
# Teams/Cyan -> "cadetblue", the closest built-in to cyan). Presentation
# only — the provider never needs to know these.
LAYER_ICON_COLOR: dict[str, str] = {
    "facility": "blue", "incident": "red", "ambulance": "green",
    "helicopter": "orange", "medical_team": "cadetblue",
}
LAYER_ICON_SYMBOL: dict[str, str] = {
    "facility": "plus-square", "incident": "warning", "ambulance": "ambulance",
    "helicopter": "plane", "medical_team": "user-md",
}
# Approximate hex swatches matching the palette above, for the in-map
# legend (Folium's named Icon colors don't expose their hex directly).
LEGEND_SWATCH_COLOR: dict[str, str] = {
    "facility": "#2A81CB", "incident": "#CB2B3E", "ambulance": "#2AAD27",
    "helicopter": "#CB8427", "medical_team": "#3D6570",
}
 
# Facility marker color by operational status, so Operational/High Load/
# Critical are recognizable at a glance (icon symbol stays "plus-square"
# for all three — only color changes). Falls back to "facility" base
# color for any status string not listed.
FACILITY_STATUS_ICON_COLOR: dict[str, str] = {
    "Operational": "green", "Busy": "orange", "High Load": "orange", "Critical": "red",
}
 
# Resource unit marker color by status, applied uniformly across
# Ambulances/Helicopters/Medical Teams so the same 4 colors always mean
# the same 4 statuses regardless of resource type. "Available" keeps
# each layer's own base type color (None below means "use the base").
RESOURCE_STATUS_ICON_COLOR: dict[str, str | None] = {
    "Available": None, "Busy": "purple", "Returning": "lightblue", "Maintenance": "gray",
}
 
# Casualty severity -> (marker color, legend swatch hex). Minor->Critical
# is an escalating color ladder using Folium's built-in palette.
CASUALTY_SEVERITY_ICON_COLOR: dict[str, str] = {
    "Minor": "lightgreen", "Moderate": "orange", "Severe": "lightred", "Critical": "darkred",
}
CASUALTY_SEVERITY_LEGEND_COLOR: dict[str, str] = {
    "Minor": "#8FBC6B", "Moderate": "#CB8427", "Severe": "#E0774F", "Critical": "#8B1E1E",
}
CASUALTY_ICON_SYMBOL: str = "plus"
 
 
# Evacuation route styling by transport mode — color + dash pattern so
# Ground/Air are distinguishable even without hovering for the popup.
ROUTE_TRANSPORT_STYLE: dict[str, dict] = {
    "Ground": {"color": "#4A6FA5", "dash_array": None},
    "Air": {"color": "#8B5FBF", "dash_array": "8,6"},
}
ROUTE_LEGEND_COLOR: dict[str, str] = {"Ground": "#4A6FA5", "Air": "#8B5FBF"}
 
 
def _build_base_map() -> folium.Map:
    """A blank, offline tactical canvas — crs='Simple' (non-geographic plane), no tile server, dark background + gridlines."""
    bounds = FRONTEND_MAP_LAYOUT["bounds"]
    tactical_map = folium.Map(
        location=list(FRONTEND_MAP_LAYOUT["center"]),
        zoom_start=3,
        min_zoom=2,
        max_zoom=8,
        crs="Simple",
        tiles=None,
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
    tactical_map.fit_bounds(
        [
            [0, 0],
            [100, 100],
        ]
    )
 
    return tactical_map
 
 
def _add_legend(tactical_map: folium.Map) -> None:
    """
    Embed the legend inside the map itself (a fixed-position overlay in
    the map's own corner) instead of a caption below it — the standard
    Folium technique for this is a branca MacroElement/Template injected
    into the map's root, since Folium has no built-in legend widget.
    """
    rows = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="color:{color};">&#9679;</span>&nbsp;{label}'
        f'</div>'
        for color, label in (
            (LEGEND_SWATCH_COLOR["facility"], "Medical Facility"),
            (LEGEND_SWATCH_COLOR["incident"], "Active Incident"),
            (LEGEND_SWATCH_COLOR["ambulance"], "Ambulance"),
            (LEGEND_SWATCH_COLOR["helicopter"], "Helicopter"),
            (LEGEND_SWATCH_COLOR["medical_team"], "Medical Team"),
        )
    )
    severity_rows = "".join(
        f'<div style="margin:2px 0;">'
        f'<span style="color:{CASUALTY_SEVERITY_LEGEND_COLOR[severity]};">&#9679;</span>&nbsp;Casualty — {severity}'
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
    for facility in facilities:
        available_beds = facility["capacity"] - facility["occupied"]
        popup_html = (
            f"<b>{facility['name']}</b><br>"
            f"{facility['full_name']}<br>"
            f"Status: {facility['status']}<br>"
            f"Capacity: {facility['capacity']}<br>"
            f"Occupied: {facility['occupied']}<br>"
            f"Available Beds: {available_beds}<br>"
            f"Waiting: {facility['waiting']}<br>"
            f"Avg. Treatment: {facility['avg_treatment']}"
        )
        icon_color = FACILITY_STATUS_ICON_COLOR.get(facility["status"], LAYER_ICON_COLOR["facility"])
        folium.Marker(
            location=[facility["grid_y"], facility["grid_x"]],
            tooltip=f"{facility['name']} — {facility['status']}",
            popup=folium.Popup(popup_html, max_width=260),
            icon=folium.Icon(color=icon_color, icon=LAYER_ICON_SYMBOL["facility"], prefix="fa"),
        ).add_to(feature_group)
 
 
def _add_incidents_layer(feature_group: folium.FeatureGroup, incidents: list[dict]) -> None:
    for incident in incidents:
        popup_html = (
            f"<b>Incident — Sector {incident['battle_sector']}</b><br>"
            f"Casualties: {incident['casualty_count']}<br>"
            f"{incident['description']}"
        )
        folium.Marker(
            location=[incident["grid_y"], incident["grid_x"]],
            tooltip=f"Incident — Sector {incident['battle_sector']}",
            popup=folium.Popup(popup_html, max_width=260),
            icon=folium.Icon(color=LAYER_ICON_COLOR["incident"], icon=LAYER_ICON_SYMBOL["incident"], prefix="fa"),
        ).add_to(feature_group)
 
 
def _add_units_layer(feature_group: folium.FeatureGroup, units: list[dict], unit_type_label: str, layer_key: str) -> None:
    for unit in units:
        popup_html = (
            f"<b>{unit['call_sign']}</b><br>"
            f"Type: {unit_type_label}<br>"
            f"Status: {unit['status']}"
        )
        status_color = RESOURCE_STATUS_ICON_COLOR.get(unit["status"])
        icon_color = status_color if status_color else LAYER_ICON_COLOR[layer_key]
        folium.Marker(
            location=[unit["grid_y"], unit["grid_x"]],
            tooltip=f"{unit['call_sign']} — {unit['status']}",
            popup=folium.Popup(popup_html, max_width=220),
            icon=folium.Icon(color=icon_color, icon=LAYER_ICON_SYMBOL[layer_key], prefix="fa"),
        ).add_to(feature_group)
 
 
def _add_casualties_layer(feature_group: folium.FeatureGroup, casualties: list[dict]) -> None:
    for casualty in casualties:
        popup_html = (
            f"<b>{casualty['casualty_ref']}</b><br>"
            f"Severity: {casualty['severity']}<br>"
            f"Sector: {casualty['battle_sector']}"
        )
        folium.Marker(
            location=[casualty["grid_y"], casualty["grid_x"]],
            tooltip=f"{casualty['casualty_ref']} — {casualty['severity']}",
            popup=folium.Popup(popup_html, max_width=200),
            icon=folium.Icon(
                color=CASUALTY_SEVERITY_ICON_COLOR[casualty["severity"]],
                icon=CASUALTY_ICON_SYMBOL, prefix="fa",
            ),
        ).add_to(feature_group)
 
 
def _add_routes_layer(feature_group: folium.FeatureGroup, routes: list[dict]) -> None:
    """Draws exactly what the provider derived — no route computation here."""
    for route in routes:
        style = ROUTE_TRANSPORT_STYLE[route["transport_mode"]]
        popup_html = (
            f"<b>{route['segment']}</b><br>"
            f"Destination: {route['destination']}<br>"
            f"Transport Mode: {route['transport_mode']}"
        )
        start_y, start_x = route["start"][1], route["start"][0]
        end_y, end_x = route["end"][1], route["end"][0]
        folium.PolyLine(
            locations=[[start_y, start_x], [end_y, end_x]],
            color=style["color"],
            weight=3,
            dash_array=style["dash_array"],
            popup=folium.Popup(popup_html, max_width=220),
            tooltip=f"{route['segment']} ({route['transport_mode']})",
        ).add_to(feature_group)
 
 
def render_tactical_map(
    map_data: MapData,
    mode: str = "simulation",
) -> None:
    """
    The renderer. Draws exactly what `map_data` contains — Facilities,
    Incident, Ambulances, Helicopters, Medical Teams layers, a layer
    control, marker popups, an embedded legend, and a Center Map control.
    Has no knowledge of where map_data came from.
    """
    if mode == "simulation":
        st.session_state.setdefault("tactical_map_reset_counter", 0)

        if secondary_button(
            "🎯 Center Map",
            key="tactical_map_center_button",
            use_container_width=False,
        ):
            st.session_state["tactical_map_reset_counter"] += 1
            st.rerun()
 
    tactical_map = _build_base_map()
 
    facilities_layer = folium.FeatureGroup(name="Medical Facilities", show=True)
    incidents_layer = folium.FeatureGroup(name="Active Incidents", show=True)
    casualties_layer = folium.FeatureGroup(name="Casualties", show=True)
    routes_layer = folium.FeatureGroup(name="Evacuation Routes", show=True)
    ambulances_layer = folium.FeatureGroup(name="Ambulances", show=True)
    helicopters_layer = folium.FeatureGroup(name="Helicopters", show=True)
    medical_teams_layer = folium.FeatureGroup(name="Medical Teams", show=True)
 
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

    if mode == "simulation":
        _add_casualties_layer(
            casualties_layer,
            map_data.casualties,
        )

        _add_routes_layer(
            routes_layer,
            map_data.routes,
        )
 
    layers = [
        facilities_layer,
        incidents_layer,
        ambulances_layer,
        helicopters_layer,
        medical_teams_layer,
    ]

    if mode == "simulation":
        layers.extend(
            [
                casualties_layer,
                routes_layer,
            ]
        )

    for layer in layers:
        layer.add_to(tactical_map)
 
    if mode == "simulation":
        folium.LayerControl(
            collapsed=False
        ).add_to(tactical_map)

        _add_legend(tactical_map)
 
    height = 620 if mode == "simulation" else 300

    map_key = (
        f"simulation_tactical_map_{st.session_state['tactical_map_reset_counter']}"
        if mode == "simulation"
        else "dashboard_tactical_map"
    )

    st_folium(
        tactical_map,
        width="100%",
        height=height,
        returned_objects=[],
        key=map_key,
    )




































# """
# tactical_map.py
 
# Dedicated, reusable Battlefield Map component for the Simulation page.
# Kept out of simulation.py per "avoid putting all map logic inside
# simulation.py... create a dedicated reusable Battlefield Map component."
 
# ARCHITECTURE — provider / renderer split
# -----------------------------------------------------------------------
# get_map_data(...)      the ONE provider. Takes simulation.py's existing
#                         mock state (FACILITY_STATUS, RESOURCE_STATUS,
#                         MISSION_LOG_ENTRIES) and returns a single MapData
#                         object with every coordinate already resolved.
#                         This is the ONLY function that knows where data
#                         comes from.
# render_tactical_map(map_data)
#                         the renderer. Takes ONE MapData object and draws
#                         it. It has no idea whether that MapData was built
#                         from frontend mock state or, later, from live
#                         backend queries — it just renders whatever it's
#                         given. When backend integration happens, only
#                         get_map_data() (or a new provider with the same
#                         MapData return shape) needs to change; this
#                         function does not.
 
# Nothing in this file duplicates a "simulation concept" that already
# exists in simulation.py: incidents are DERIVED from MISSION_LOG_ENTRIES's
# own "Incident"-category entries (not a second, separately-maintained
# incident list), and facility/resource identity, names, and stats are
# read directly from FACILITY_STATUS/RESOURCE_STATUS, never copied.
 
# Scope for this phase: interactive map, Facilities, Incident, Ambulances,
# Helicopters, Medical Teams, layer control, popups, an in-map legend, and
# a Center Map control. NOT this phase: Evacuation Routes, live tracking,
# animation, or backend integration — still entirely frontend-only.
 
# No backend imports of any kind.
# """
 
# from __future__ import annotations
# import math
# import re
# from dataclasses import dataclass, field
 
# import folium
# from branca.element import MacroElement, Template
# import streamlit as st
# from streamlit_folium import st_folium
 
# from components.buttons import secondary_button
 
# # ==========================================================================
# # FRONTEND_MAP_LAYOUT — visualization-only coordinate data.
# #
# # This entire block exists ONLY because the frontend is currently running
# # on mock simulation state that carries no coordinates of its own
# # (FACILITY_STATUS/RESOURCE_STATUS/MISSION_LOG_ENTRIES are plain
# # name/stat/text data — none of it has a grid position). The numbers
# # below mirror backend/Phase 1/constants.py's real AO_GRID_BOUNDS /
# # FACILITY_CONFIG / SECTOR_GRID_ANCHORS values, so today's map looks
# # geographically consistent with the eventual real system, but this is
# # NOT a live import and NOT a second authoritative copy of backend data —
# # it is temporary frontend plumbing, clearly named as such.
# #
# # When backend integration happens, get_map_data() below should be
# # rewritten to read grid_x/grid_y directly from the backend's own
# # Facility/Incident/Ambulance/Helicopter rows, and this entire dict
# # should be deleted rather than kept "just in case."
# # ==========================================================================
# FRONTEND_MAP_LAYOUT: dict = {
#     "bounds": {"min_x": 0.0, "max_x": 100.0, "min_y": 0.0, "max_y": 100.0},
#     "center": (50.0, 50.0),  # (grid_y, grid_x) — Leaflet order under crs="Simple"
 
#     # Keyed by the exact `name` strings FACILITY_STATUS already uses, so
#     # the provider can look positions up with no translation layer.
#     "facility_positions": {
#         "RAP — Alpha 1": (18.0, 18.0),
#         "ADS — Bravo 2": (38.0, 42.0),
#         "HMV — Delta 9": (72.0, 70.0),
#         "FDC — Foxtrot 3": (85.0, 88.0),
#     },
 
#     # Used only to plot an Incident-category mission log entry that
#     # mentions one of these sector names — see _derive_incidents().
#     "sector_anchors": {
#         "Alpha": (20.0, 3.0), "Bravo": (48.0, 28.0), "Charlie": (50.0, 2.0),
#         "Delta": (65.0, 5.0), "Echo": (80.0, 3.0), "Foxtrot": (95.0, 4.0),
#     },
 
#     # Which staging point each resource status category is plotted at.
#     # "INCIDENT" resolves to whichever incident _derive_incidents() found
#     # (falls back to the AO center if there is none this render).
#     "resource_staging_points": {
#         "available": "RAP", "busy": "INCIDENT", "returning": "ADS", "maintenance": "FDC",
#     },
#     "facility_code_to_name": {
#         "RAP": "RAP — Alpha 1", "ADS": "ADS — Bravo 2", "HMV": "HMV — Delta 9", "FDC": "FDC — Foxtrot 3",
#     },
# }
 
# # Folium's built-in Icon() color palette is a fixed named set — these are
# # the closest matches to the originally suggested colors (Facilities/
# # Blue, Incidents/Red, Ambulances/Green, Helicopters/Orange, Medical
# # Teams/Cyan -> "cadetblue", the closest built-in to cyan). Presentation
# # only — the provider never needs to know these.
# LAYER_ICON_COLOR: dict[str, str] = {
#     "facility": "blue", "incident": "red", "ambulance": "green",
#     "helicopter": "orange", "medical_team": "cadetblue",
# }
# LAYER_ICON_SYMBOL: dict[str, str] = {
#     "facility": "plus-square", "incident": "warning", "ambulance": "ambulance",
#     "helicopter": "plane", "medical_team": "user-md",
# }
# # Approximate hex swatches matching the palette above, for the in-map
# # legend (Folium's named Icon colors don't expose their hex directly).
# LEGEND_SWATCH_COLOR: dict[str, str] = {
#     "facility": "#2A81CB", "incident": "#CB2B3E", "ambulance": "#2AAD27",
#     "helicopter": "#CB8427", "medical_team": "#3D6570",
# }
 
# # Facility marker color by operational status, so Operational/High Load/
# # Critical are recognizable at a glance (icon symbol stays "plus-square"
# # for all three — only color changes). Falls back to "facility" base
# # color for any status string not listed.
# FACILITY_STATUS_ICON_COLOR: dict[str, str] = {
#     "Operational": "green", "Busy": "orange", "High Load": "orange", "Critical": "red",
# }
 
# # Resource unit marker color by status, applied uniformly across
# # Ambulances/Helicopters/Medical Teams so the same 4 colors always mean
# # the same 4 statuses regardless of resource type. "Available" keeps
# # each layer's own base type color (None below means "use the base").
# RESOURCE_STATUS_ICON_COLOR: dict[str, str | None] = {
#     "Available": None, "Busy": "purple", "Returning": "lightblue", "Maintenance": "gray",
# }
 
# # Casualty severity -> (marker color, legend swatch hex). Minor->Critical
# # is an escalating color ladder using Folium's built-in palette.
# CASUALTY_SEVERITY_CYCLE: list[str] = ["Critical", "Severe", "Moderate", "Minor"]
# CASUALTY_SEVERITY_ICON_COLOR: dict[str, str] = {
#     "Minor": "lightgreen", "Moderate": "orange", "Severe": "lightred", "Critical": "darkred",
# }
# CASUALTY_SEVERITY_LEGEND_COLOR: dict[str, str] = {
#     "Minor": "#8FBC6B", "Moderate": "#CB8427", "Severe": "#E0774F", "Critical": "#8B1E1E",
# }
# CASUALTY_ICON_SYMBOL: str = "plus"
 
# # Frontend-only fallback used only if an Incident-category mission log
# # entry doesn't mention a numeric casualty count in its text.
# DEFAULT_CASUALTY_COUNT_PER_INCIDENT: int = 2
 
# # Evacuation route styling by transport mode — color + dash pattern so
# # Ground/Air are distinguishable even without hovering for the popup.
# ROUTE_TRANSPORT_STYLE: dict[str, dict] = {
#     "Ground": {"color": "#4A6FA5", "dash_array": None},
#     "Air": {"color": "#8B5FBF", "dash_array": "8,6"},
# }
# ROUTE_LEGEND_COLOR: dict[str, str] = {"Ground": "#4A6FA5", "Air": "#8B5FBF"}
 
# # Deterministic evacuation chain (matches backend's real RAP->ADS->HMV
# # progression) with each leg's transport mode — provider-derived mock
# # values only, not a new simulation state.
# EVACUATION_CHAIN: list[dict] = [
#     {"segment": "Incident to RAP", "facility_code": "RAP", "transport_mode": "Ground"},
#     {"segment": "RAP to ADS", "facility_code": "ADS", "transport_mode": "Ground"},
#     {"segment": "ADS to HMV", "facility_code": "HMV", "transport_mode": "Air"},
# ]
 
 
# @dataclass
# class MapData:
#     """
#     Everything render_tactical_map() needs, fully resolved (coordinates
#     included) — the single object the renderer depends on. Built by
#     get_map_data() today from frontend mock state; a future backend-
#     integrated provider should return this exact same shape.
#     """
#     facilities: list[dict] = field(default_factory=list)
#     incidents: list[dict] = field(default_factory=list)
#     ambulances: list[dict] = field(default_factory=list)
#     helicopters: list[dict] = field(default_factory=list)
#     medical_teams: list[dict] = field(default_factory=list)
#     casualties: list[dict] = field(default_factory=list)
#     routes: list[dict] = field(default_factory=list)
 
 
# def _spread_positions(base_grid_x: float, base_grid_y: float, count: int, radius: float = 5.0) -> list[tuple[float, float]]:
#     """
#     Deterministic (never random) placement for `count` units around one
#     staging point, so multiple units at the same facility/incident don't
#     render as a single overlapping marker. Same input always produces the
#     same output.
#     """
#     if count <= 0:
#         return []
#     if count == 1:
#         return [(base_grid_x, base_grid_y)]
#     positions = []
#     for index in range(count):
#         angle = (2 * math.pi / count) * index
#         positions.append((
#             base_grid_x + radius * math.cos(angle),
#             base_grid_y + radius * math.sin(angle),
#         ))
#     return positions
 
 
# def _derive_incidents(mission_log_entries: list[dict]) -> list[dict]:
#     """
#     Derive incident markers from simulation.py's own MISSION_LOG_ENTRIES
#     — its "Incident"-category entries — instead of maintaining a second,
#     separately-hardcoded incident list. The mission log entry's own
#     description is used verbatim as the popup text, so that narrative
#     exists in exactly one place (the mission log), not two.
 
#     The mission log only carries free text, not a structured battle
#     sector or coordinates, so a sector name is matched by simple
#     substring search against the known sector list — the map layout
#     dict's sector_anchors keys — which is how a plot position is
#     resolved. An entry that doesn't mention a known sector by name is
#     skipped rather than guessed at.
#     """
#     known_sectors = FRONTEND_MAP_LAYOUT["sector_anchors"].keys()
#     incidents = []
#     for entry in mission_log_entries:
#         if entry.get("category") != "Incident":
#             continue
#         matched_sector = next((sector for sector in known_sectors if sector in entry["description"]), None)
#         if matched_sector is None:
#             continue
#         grid_x, grid_y = FRONTEND_MAP_LAYOUT["sector_anchors"][matched_sector]
#         # Casualty count for the popup/casualty markers: the mission log
#         # only carries prose, so the number is picked out of the existing
#         # description text (e.g. "4 casualties confirmed") with a simple
#         # pattern match rather than inventing a separate figure. Falls
#         # back to DEFAULT_CASUALTY_COUNT_PER_INCIDENT if no number is
#         # mentioned.
#         casualty_match = re.search(r"(\d+)\s+casualt", entry["description"], re.IGNORECASE)
#         casualty_count = int(casualty_match.group(1)) if casualty_match else DEFAULT_CASUALTY_COUNT_PER_INCIDENT
#         incidents.append({
#             "battle_sector": matched_sector,
#             "description": entry["description"],
#             "casualty_count": casualty_count,
#             "grid_x": grid_x,
#             "grid_y": grid_y,
#         })
#     return incidents
 
 
# def _derive_casualties(incidents: list[dict]) -> list[dict]:
#     """
#     Minimal visualization-only casualty representation, derived here
#     inside the provider — not a second global simulation state. The mock
#     state has no individual Casualty objects, only each incident's
#     casualty_count (see _derive_incidents), so that many points are
#     plotted clustered around the incident's own location, with severity
#     assigned by cycling a fixed order (CASUALTY_SEVERITY_CYCLE) —
#     deterministic, never random. This list exists only for the duration
#     of one get_map_data() call and is not stored anywhere else; it
#     disappears entirely once backend integration supplies real Casualty
#     rows with their own grid_x/grid_y/severity.
#     """
#     casualties = []
#     casualty_sequence = 1
#     for incident in incidents:
#         positions = _spread_positions(
#             incident["grid_x"], incident["grid_y"], incident["casualty_count"], radius=3.5,
#         )
#         for index, (grid_x, grid_y) in enumerate(positions):
#             casualties.append({
#                 "casualty_ref": f"CAS-{casualty_sequence:03d}",
#                 "severity": CASUALTY_SEVERITY_CYCLE[index % len(CASUALTY_SEVERITY_CYCLE)],
#                 "battle_sector": incident["battle_sector"],
#                 "grid_x": grid_x,
#                 "grid_y": grid_y,
#             })
#             casualty_sequence += 1
#     return casualties
 
 
# def _derive_routes(incidents: list[dict]) -> list[dict]:
#     """
#     Evacuation route segments (Incident -> RAP -> ADS -> HMV), derived
#     entirely inside the provider from data already resolved here — the
#     incident's own location plus FRONTEND_MAP_LAYOUT's facility
#     positions. Not a new simulation state: EVACUATION_CHAIN is a fixed,
#     deterministic presentation of the same evacuation order the backend
#     already documents (FACILITY_ORDER), with transport mode assigned
#     per-leg, never randomly.
#     """
#     routes = []
#     for incident in incidents:
#         previous_point = (incident["grid_x"], incident["grid_y"])
#         for leg in EVACUATION_CHAIN:
#             facility_name = FRONTEND_MAP_LAYOUT["facility_code_to_name"][leg["facility_code"]]
#             facility_y, facility_x = FRONTEND_MAP_LAYOUT["facility_positions"][facility_name]
#             routes.append({
#                 "segment": leg["segment"],
#                 "destination": facility_name,
#                 "transport_mode": leg["transport_mode"],
#                 "battle_sector": incident["battle_sector"],
#                 "start": previous_point,
#                 "end": (facility_x, facility_y),
#             })
#             previous_point = (facility_x, facility_y)
#     return routes
 
 
# def _resolve_staging_point(staging_key: str, incidents: list[dict]) -> tuple[float, float]:
#     """Resolve a resource_staging_points value ('RAP'/'ADS'/'FDC'/'INCIDENT') to grid (x, y)."""
#     if staging_key == "INCIDENT":
#         if incidents:
#             return incidents[0]["grid_x"], incidents[0]["grid_y"]
#         return FRONTEND_MAP_LAYOUT["center"][1], FRONTEND_MAP_LAYOUT["center"][0]
#     facility_name = FRONTEND_MAP_LAYOUT["facility_code_to_name"][staging_key]
#     facility_y, facility_x = FRONTEND_MAP_LAYOUT["facility_positions"][facility_name]
#     return facility_x, facility_y
 
 
# def _derive_resource_units(resource_entry: dict, call_sign_prefix: str, incidents: list[dict]) -> list[dict]:
#     """Expand one RESOURCE_STATUS entry's available/busy/returning/maintenance counts into individual, positioned units."""
#     units = []
#     unit_index = 1
#     for status_key, count in (
#         ("available", resource_entry["available"]),
#         ("busy", resource_entry["busy"]),
#         ("returning", resource_entry["returning"]),
#         ("maintenance", resource_entry["maintenance"]),
#     ):
#         staging_key = FRONTEND_MAP_LAYOUT["resource_staging_points"][status_key]
#         base_x, base_y = _resolve_staging_point(staging_key, incidents)
#         for grid_x, grid_y in _spread_positions(base_x, base_y, count):
#             units.append({
#                 "call_sign": f"{call_sign_prefix}-{unit_index:02d}",
#                 "status": status_key.capitalize(),
#                 "grid_x": grid_x,
#                 "grid_y": grid_y,
#             })
#             unit_index += 1
#     return units
 
 
# def get_map_data(facility_status: list[dict], resource_status: list[dict], mission_log_entries: list[dict]) -> MapData:
#     """
#     THE single map data provider. Packages simulation.py's existing mock
#     state into one fully-resolved MapData object — the only thing
#     render_tactical_map() depends on.
 
#     Args:
#         facility_status: simulation.py's existing FACILITY_STATUS list.
#         resource_status: simulation.py's existing RESOURCE_STATUS list.
#         mission_log_entries: simulation.py's existing MISSION_LOG_ENTRIES
#                               list (used to derive incidents — see
#                               _derive_incidents()).
 
#     Today this simply packages frontend mock state plus the frontend-only
#     FRONTEND_MAP_LAYOUT coordinates. Later, an alternate provider (or this
#     same function, rewritten) can build the identical MapData shape from
#     live backend queries instead — render_tactical_map() would not need
#     to change at all.
#     """
#     facilities = []
#     for facility in facility_status:
#         position = FRONTEND_MAP_LAYOUT["facility_positions"].get(facility["name"])
#         if position is None:
#             continue
#         grid_y, grid_x = position
#         facilities.append({**facility, "grid_x": grid_x, "grid_y": grid_y})
 
#     incidents = _derive_incidents(mission_log_entries)
#     casualties = _derive_casualties(incidents)
#     routes = _derive_routes(incidents)
 
#     resource_by_name = {entry["name"]: entry for entry in resource_status}
#     ambulances = (
#         _derive_resource_units(resource_by_name["Ambulances"], "AMB", incidents)
#         if "Ambulances" in resource_by_name else []
#     )
#     helicopters = (
#         _derive_resource_units(resource_by_name["Helicopters"], "HELI", incidents)
#         if "Helicopters" in resource_by_name else []
#     )
#     medical_teams = (
#         _derive_resource_units(resource_by_name["Medical Teams"], "MED-TEAM", incidents)
#         if "Medical Teams" in resource_by_name else []
#     )
 
#     return MapData(
#         facilities=facilities,
#         incidents=incidents,
#         ambulances=ambulances,
#         helicopters=helicopters,
#         medical_teams=medical_teams,
#         casualties=casualties,
#         routes=routes,
#     )
 
 
# def _build_base_map() -> folium.Map:
#     """A blank, offline tactical canvas — crs='Simple' (non-geographic plane), no tile server, dark background + gridlines."""
#     bounds = FRONTEND_MAP_LAYOUT["bounds"]
#     tactical_map = folium.Map(
#         location=list(FRONTEND_MAP_LAYOUT["center"]),
#         zoom_start=3,
#         min_zoom=2,
#         max_zoom=8,
#         crs="Simple",
#         tiles=None,
#     )
 
#     folium.Rectangle(
#         bounds=[[bounds["min_y"], bounds["min_x"]], [bounds["max_y"], bounds["max_x"]]],
#         color="#2B4154", weight=1, fill=True, fill_color="#0F1520", fill_opacity=1.0,
#         interactive=False,
#     ).add_to(tactical_map)
 
#     grid_line_color = "#1C2733"
#     for step in range(0, 101, 10):
#         folium.PolyLine(
#             [[bounds["min_y"], step], [bounds["max_y"], step]],
#             color=grid_line_color, weight=1, opacity=0.6, interactive=False,
#         ).add_to(tactical_map)
#         folium.PolyLine(
#             [[step, bounds["min_x"]], [step, bounds["max_x"]]],
#             color=grid_line_color, weight=1, opacity=0.6, interactive=False,
#         ).add_to(tactical_map)
#     tactical_map.fit_bounds(
#         [
#             [0, 0],
#             [100, 100],
#         ]
#     )
 
#     return tactical_map
 
 
# def _add_legend(tactical_map: folium.Map) -> None:
#     """
#     Embed the legend inside the map itself (a fixed-position overlay in
#     the map's own corner) instead of a caption below it — the standard
#     Folium technique for this is a branca MacroElement/Template injected
#     into the map's root, since Folium has no built-in legend widget.
#     """
#     rows = "".join(
#         f'<div style="margin:2px 0;">'
#         f'<span style="color:{color};">&#9679;</span>&nbsp;{label}'
#         f'</div>'
#         for color, label in (
#             (LEGEND_SWATCH_COLOR["facility"], "Medical Facility"),
#             (LEGEND_SWATCH_COLOR["incident"], "Active Incident"),
#             (LEGEND_SWATCH_COLOR["ambulance"], "Ambulance"),
#             (LEGEND_SWATCH_COLOR["helicopter"], "Helicopter"),
#             (LEGEND_SWATCH_COLOR["medical_team"], "Medical Team"),
#         )
#     )
#     severity_rows = "".join(
#         f'<div style="margin:2px 0;">'
#         f'<span style="color:{CASUALTY_SEVERITY_LEGEND_COLOR[severity]};">&#9679;</span>&nbsp;Casualty — {severity}'
#         f'</div>'
#         for severity in ("Minor", "Moderate", "Severe", "Critical")
#     )
#     route_rows = "".join(
#         f'<div style="margin:2px 0;">'
#         f'<span style="color:{ROUTE_LEGEND_COLOR[mode]};">&#9473;&#9473;</span>&nbsp;{mode} Evacuation'
#         f'</div>'
#         for mode in ("Ground", "Air")
#     )
#     legend_html = (
#         "{% macro html(this, kwargs) %}"
#         '<div style="'
#         "position:fixed;bottom:24px;left:24px;z-index:9999;"
#         "background:rgba(15,21,32,0.92);color:#F4F6F8;"
#         "padding:10px 14px;border-radius:6px;border:1px solid #2B4154;"
#         'font-size:12px;line-height:1.6;font-family:sans-serif;">'
#         '<b style="font-size:12px;">Legend</b>'
#         f"{rows}"
#         f"{severity_rows}"
#         f"{route_rows}"
#         "</div>"
#         "{% endmacro %}"
#     )
#     legend = MacroElement()
#     legend._template = Template(legend_html)
#     tactical_map.get_root().add_child(legend)
 
 
# def _add_facilities_layer(feature_group: folium.FeatureGroup, facilities: list[dict]) -> None:
#     for facility in facilities:
#         available_beds = facility["capacity"] - facility["occupied"]
#         popup_html = (
#             f"<b>{facility['name']}</b><br>"
#             f"{facility['full_name']}<br>"
#             f"Status: {facility['status']}<br>"
#             f"Capacity: {facility['capacity']}<br>"
#             f"Occupied: {facility['occupied']}<br>"
#             f"Available Beds: {available_beds}<br>"
#             f"Waiting: {facility['waiting']}<br>"
#             f"Avg. Treatment: {facility['avg_treatment']}"
#         )
#         icon_color = FACILITY_STATUS_ICON_COLOR.get(facility["status"], LAYER_ICON_COLOR["facility"])
#         folium.Marker(
#             location=[facility["grid_y"], facility["grid_x"]],
#             tooltip=f"{facility['name']} — {facility['status']}",
#             popup=folium.Popup(popup_html, max_width=260),
#             icon=folium.Icon(color=icon_color, icon=LAYER_ICON_SYMBOL["facility"], prefix="fa"),
#         ).add_to(feature_group)
 
 
# def _add_incidents_layer(feature_group: folium.FeatureGroup, incidents: list[dict]) -> None:
#     for incident in incidents:
#         popup_html = (
#             f"<b>Incident — Sector {incident['battle_sector']}</b><br>"
#             f"Casualties: {incident['casualty_count']}<br>"
#             f"{incident['description']}"
#         )
#         folium.Marker(
#             location=[incident["grid_y"], incident["grid_x"]],
#             tooltip=f"Incident — Sector {incident['battle_sector']}",
#             popup=folium.Popup(popup_html, max_width=260),
#             icon=folium.Icon(color=LAYER_ICON_COLOR["incident"], icon=LAYER_ICON_SYMBOL["incident"], prefix="fa"),
#         ).add_to(feature_group)
 
 
# def _add_units_layer(feature_group: folium.FeatureGroup, units: list[dict], unit_type_label: str, layer_key: str) -> None:
#     for unit in units:
#         popup_html = (
#             f"<b>{unit['call_sign']}</b><br>"
#             f"Type: {unit_type_label}<br>"
#             f"Status: {unit['status']}"
#         )
#         status_color = RESOURCE_STATUS_ICON_COLOR.get(unit["status"])
#         icon_color = status_color if status_color else LAYER_ICON_COLOR[layer_key]
#         folium.Marker(
#             location=[unit["grid_y"], unit["grid_x"]],
#             tooltip=f"{unit['call_sign']} — {unit['status']}",
#             popup=folium.Popup(popup_html, max_width=220),
#             icon=folium.Icon(color=icon_color, icon=LAYER_ICON_SYMBOL[layer_key], prefix="fa"),
#         ).add_to(feature_group)
 
 
# def _add_casualties_layer(feature_group: folium.FeatureGroup, casualties: list[dict]) -> None:
#     for casualty in casualties:
#         popup_html = (
#             f"<b>{casualty['casualty_ref']}</b><br>"
#             f"Severity: {casualty['severity']}<br>"
#             f"Sector: {casualty['battle_sector']}"
#         )
#         folium.Marker(
#             location=[casualty["grid_y"], casualty["grid_x"]],
#             tooltip=f"{casualty['casualty_ref']} — {casualty['severity']}",
#             popup=folium.Popup(popup_html, max_width=200),
#             icon=folium.Icon(
#                 color=CASUALTY_SEVERITY_ICON_COLOR[casualty["severity"]],
#                 icon=CASUALTY_ICON_SYMBOL, prefix="fa",
#             ),
#         ).add_to(feature_group)
 
 
# def _add_routes_layer(feature_group: folium.FeatureGroup, routes: list[dict]) -> None:
#     """Draws exactly what the provider derived — no route computation here."""
#     for route in routes:
#         style = ROUTE_TRANSPORT_STYLE[route["transport_mode"]]
#         popup_html = (
#             f"<b>{route['segment']}</b><br>"
#             f"Destination: {route['destination']}<br>"
#             f"Transport Mode: {route['transport_mode']}"
#         )
#         start_y, start_x = route["start"][1], route["start"][0]
#         end_y, end_x = route["end"][1], route["end"][0]
#         folium.PolyLine(
#             locations=[[start_y, start_x], [end_y, end_x]],
#             color=style["color"],
#             weight=3,
#             dash_array=style["dash_array"],
#             popup=folium.Popup(popup_html, max_width=220),
#             tooltip=f"{route['segment']} ({route['transport_mode']})",
#         ).add_to(feature_group)
 
 
# def render_tactical_map(
#     map_data: MapData,
#     mode: str = "simulation",
# ) -> None:
#     """
#     The renderer. Draws exactly what `map_data` contains — Facilities,
#     Incident, Ambulances, Helicopters, Medical Teams layers, a layer
#     control, marker popups, an embedded legend, and a Center Map control.
#     Has no knowledge of where map_data came from.
#     """
#     if mode == "simulation":
#         st.session_state.setdefault("tactical_map_reset_counter", 0)

#         if secondary_button(
#             "🎯 Center Map",
#             key="tactical_map_center_button",
#             use_container_width=False,
#         ):
#             st.session_state["tactical_map_reset_counter"] += 1
#             st.rerun()
 
#     tactical_map = _build_base_map()
 
#     facilities_layer = folium.FeatureGroup(name="Medical Facilities", show=True)
#     incidents_layer = folium.FeatureGroup(name="Active Incidents", show=True)
#     casualties_layer = folium.FeatureGroup(name="Casualties", show=True)
#     routes_layer = folium.FeatureGroup(name="Evacuation Routes", show=True)
#     ambulances_layer = folium.FeatureGroup(name="Ambulances", show=True)
#     helicopters_layer = folium.FeatureGroup(name="Helicopters", show=True)
#     medical_teams_layer = folium.FeatureGroup(name="Medical Teams", show=True)
 
#     _add_facilities_layer(
#         facilities_layer,
#         map_data.facilities,
#     )

#     _add_incidents_layer(
#         incidents_layer,
#         map_data.incidents,
#     )

#     _add_units_layer(
#         ambulances_layer,
#         map_data.ambulances,
#         "Ambulance",
#         "ambulance",
#     )

#     _add_units_layer(
#         helicopters_layer,
#         map_data.helicopters,
#         "Helicopter",
#         "helicopter",
#     )

#     _add_units_layer(
#         medical_teams_layer,
#         map_data.medical_teams,
#         "Medical Team",
#         "medical_team",
#     )

#     if mode == "simulation":
#         _add_casualties_layer(
#             casualties_layer,
#             map_data.casualties,
#         )

#         _add_routes_layer(
#             routes_layer,
#             map_data.routes,
#         )
 
#     layers = [
#         facilities_layer,
#         incidents_layer,
#         ambulances_layer,
#         helicopters_layer,
#         medical_teams_layer,
#     ]

#     if mode == "simulation":
#         layers.extend(
#             [
#                 casualties_layer,
#                 routes_layer,
#             ]
#         )

#     for layer in layers:
#         layer.add_to(tactical_map)
 
#     if mode == "simulation":
#         folium.LayerControl(
#             collapsed=False
#         ).add_to(tactical_map)

#         _add_legend(tactical_map)
 
#     height = 620 if mode == "simulation" else 300

#     map_key = (
#         f"simulation_tactical_map_{st.session_state['tactical_map_reset_counter']}"
#         if mode == "simulation"
#         else "dashboard_tactical_map"
#     )

#     st_folium(
#         tactical_map,
#         width="100%",
#         height=height,
#         returned_objects=[],
#         key=map_key,
#     )
    