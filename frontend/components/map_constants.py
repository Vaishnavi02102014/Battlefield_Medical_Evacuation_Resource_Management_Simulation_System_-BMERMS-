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
# facility_positions is an independently maintained coordinate set, tuned
# for the rendered map canvas. It is not read from the backend's
# Facility.grid_x/grid_y columns, and the two coordinate sets do not
# currently agree numerically - this is presentation-layer data, not a
# second copy of database state.
#
# resource_staging_points and facility_code_to_name are keyed the same
# way (by facility_code) for the same reason: map layout is owned here,
# independent of backend storage.
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