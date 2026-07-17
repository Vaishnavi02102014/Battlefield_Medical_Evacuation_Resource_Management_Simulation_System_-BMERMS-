"""
map_constants.py

Shared, source-agnostic map geometry/lookup data used by both
components/map_adapter.py (the provider) and components/tactical_map.py
(the renderer). Split out from tactical_map.py so the provider does not
need to import from the render module to resolve coordinates.

Moved verbatim from tactical_map.py -- no values changed, no behavior
changed.
"""

# ==========================================================================
# FRONTEND_MAP_LAYOUT — visualization-only coordinate data.
#
# This entire block exists ONLY because the frontend is currently running
# on mock simulation state that carries no coordinates of its own
# (FACILITY_STATUS/RESOURCE_STATUS/MISSION_LOG_ENTRIES are plain
# name/stat/text data — none of it has a grid position). The numbers
# below mirror backend/Phase 1/constants.py's real AO_GRID_BOUNDS /
# FACILITY_CONFIG / SECTOR_GRID_ANCHORS values, so today's map looks
# geographically consistent with the eventual real system, but this is
# NOT a live import and NOT a second authoritative copy of backend data —
# it is temporary frontend plumbing, clearly named as such.
#
# When backend integration happens, get_map_data() below should be
# rewritten to read grid_x/grid_y directly from the backend's own
# Facility/Incident/Ambulance/Helicopter rows, and this entire dict
# should be deleted rather than kept "just in case."
# ==========================================================================
FRONTEND_MAP_LAYOUT: dict = {
    "bounds": {"min_x": 0.0, "max_x": 100.0, "min_y": 0.0, "max_y": 100.0},
    "center": (50.0, 50.0),  # (grid_y, grid_x) — Leaflet order under crs="Simple"
 
    # Keyed by the exact `name` strings FACILITY_STATUS already uses, so
    # the provider can look positions up with no translation layer.
    "facility_positions": {
        "RAP": (18.0, 18.0),
        "ADS": (38.0, 42.0),
        "HMV": (72.0, 70.0),
        "FDC": (85.0, 88.0),
    },
 
    # Which staging point each resource status category is plotted at.
    # "INCIDENT" resolves to whichever incident _derive_incidents() found
    # (falls back to the AO center if there is none this render).
    "resource_staging_points": {
        "available": "RAP", "busy": "INCIDENT", "returning": "ADS", "maintenance": "FDC",
    },
    "facility_code_to_name": {
        "RAP": "RAP — Alpha 1", "ADS": "ADS — Bravo 2", "HMV": "HMV — Delta 9", "FDC": "FDC — Foxtrot 3",
    },
}