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




































