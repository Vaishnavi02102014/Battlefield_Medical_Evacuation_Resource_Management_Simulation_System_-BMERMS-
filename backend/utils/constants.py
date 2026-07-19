"""
constants.py
 
Single source of truth for domain configuration used across the simulation,
database, and visualization layers. Nothing in this module has side effects —
it only defines static configuration and lookup tables.
 
Do NOT hardcode any of these values elsewhere in the codebase; import from here.
"""
 
from pathlib import Path
 
# --------------------------------------------------------------------------
# PATHS
# --------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent
DATABASE_PATH: Path = BASE_DIR / "data" / "bmermss.db"
SEED_DATASET_PATH: Path = BASE_DIR / "data" / "Battlefield_Medical_Evacuation_Synthetic_Dataset.xlsx"
 
# --------------------------------------------------------------------------
# FICTIONAL BATTLEFIELD GRID
# This is a synthetic Area of Operations, not a real-world location.
# Coordinates are expressed as a fictional local grid (grid_x, grid_y) in
# kilometers from a fictional origin point, deep inland from any real
# geography, purely for map/visualization purposes.
# --------------------------------------------------------------------------
AO_GRID_ORIGIN_LABEL: str = "Fictional Area of Operations - Grid Reference ZULU-9"
AO_GRID_BOUNDS: dict[str, float] = {"min_x": 0.0, "max_x": 100.0, "min_y": 0.0, "max_y": 100.0}
 
# --------------------------------------------------------------------------
# TREATMENT FACILITIES
# Fixed evacuation chain: RAP -> ADS -> HMV -> FDC
# treatment_duration_hours is the FIXED duration for that facility, per spec.
# grid_x / grid_y are fictional battlefield grid coordinates (km from origin),
# positioned progressively further from the front line (grid_y = 0) as the
# evacuation chain deepens, matching real-world MEDEVAC doctrine.
# --------------------------------------------------------------------------
FACILITY_CONFIG: dict[str, dict] = {
    "RAP": {
        "facility_name": "Regimental Aid Post",
        "capacity": 120,
        "treatment_duration_hours": 2,
        "handles": "Mild",
        "grid_x": 50.0,
        "grid_y": 8.0,
    },
    "ADS": {
        "facility_name": "Advanced Dressing Station",
        "capacity": 100,
        "treatment_duration_hours": 4,
        "handles": "Moderate",
        "grid_x": 55.0,
        "grid_y": 25.0,
    },
    "HMV": {
        "facility_name": "Hospital Medical Unit",
        "capacity": 300,
        "treatment_duration_hours": 4 * 24,       # 4 days
        "handles": "Serious",
        "grid_x": 62.0,
        "grid_y": 55.0,
    },
    "FDC": {
        "facility_name": "Field/Base Hospital",
        "capacity": 300,
        "treatment_duration_hours": 20 * 24,      # 20 days
        "handles": "Critical",
        "grid_x": 70.0,
        "grid_y": 85.0,
    },
}
 
# Order matters: index 0 = highest capacity tier reached first for mild cases.
FACILITY_ORDER: list[str] = ["RAP", "ADS", "HMV", "FDC"]
 
# --------------------------------------------------------------------------
# SEVERITY -> PRIORITY -> FACILITY MAPPING (immutable business rule)
# --------------------------------------------------------------------------
SEVERITY_CONFIG: dict[str, dict] = {
    "Critical": {"priority": "P0", "facility_code": "FDC", "rank": 0},
    "Serious":  {"priority": "P1", "facility_code": "HMV", "rank": 1},
    "Moderate": {"priority": "P2", "facility_code": "ADS", "rank": 2},
    "Mild":     {"priority": "P3", "facility_code": "RAP", "rank": 3},
}
 
SEVERITY_LIST: list[str] = ["Critical", "Serious", "Moderate", "Mild"]
SEVERITY_WEIGHTS: dict[str, int] = {
    "Critical": 5,
    "Serious": 15,
    "Moderate": 30,
    "Mild": 50,
}
 
# --------------------------------------------------------------------------
# INCIDENTS
# --------------------------------------------------------------------------
INCIDENT_TYPES: list[str] = [
    "Mortar Attack",
    "Artillery Strike",
    "IED Explosion",
    "Landmine Blast",
    "Sniper Fire",
    "Ambush",
    "Vehicle Explosion",
    "Convoy Attack",
    "Border Skirmish",
    "Random Patrol Clash",
]
 
INCIDENT_SIZE_BUCKETS: dict[str, dict] = {
    "Small": {
        "range": (2, 5),
        "weight": 70,
    },
    "Medium": {
        "range": (6, 12),
        "weight": 25,
    },
    "Mass Casualty": {
        "range": (13, 25),
        "weight": 5,
    },
}
 
MIN_CASUALTIES_PER_INCIDENT: int = 2
MAX_CASUALTIES_PER_INCIDENT: int = 25
 
INJURY_TYPES: list[str] = [
    "Gunshot",
    "Shrapnel",
    "Blast Injury",
    "Burn",
    "Fracture",
    "Concussion",
    "Laceration",
    "Internal Injury",
]
 
BATTLE_SECTORS: list[str] = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
 
# Fictional front-line grid position (km) for each battle sector, spread
# along grid_y = 0-5 (the front line) at different grid_x offsets. Incident
# generation jitters around these anchor points for visual variety.
SECTOR_GRID_ANCHORS: dict[str, dict] = {
    "Alpha":   {"grid_x": 20.0, "grid_y": 3.0},
    "Bravo":   {"grid_x": 35.0, "grid_y": 4.0},
    "Charlie": {"grid_x": 50.0, "grid_y": 2.0},
    "Delta":   {"grid_x": 65.0, "grid_y": 5.0},
    "Echo":    {"grid_x": 80.0, "grid_y": 3.0},
    "Foxtrot": {"grid_x": 95.0, "grid_y": 4.0},
}
 
RANKS: list[str] = [
    "Sepoy", "Naik", "Havildar", "Lieutenant", "Captain", "Major", "Colonel",
]
 
UNITS: list[str] = [
    "Infantry", "Artillery", "Armoured", "Engineers", "Signals", "Medical Corps",
]
 
EVACUATION_MODES: list[str] = ["Ambulance", "Helicopter"]
 
# --------------------------------------------------------------------------
# CASUALTY STATUS (closed set — do not extend)
# --------------------------------------------------------------------------
CASUALTY_STATUSES: list[str] = [
    "Awaiting Transport",
    "Being Evacuated",
    "Under Treatment",
    "Transferred",
    "Recovered",
    "Returned To Duty",
]
 
# --------------------------------------------------------------------------
# SCENARIO / OPERATION HIERARCHY
# --------------------------------------------------------------------------
SCENARIO_STATUSES: list[str] = ["Planned", "Active", "Concluded"]
OPERATION_STATUSES: list[str] = ["Planned", "Active", "Concluded"]
 
THREAT_LEVELS: list[str] = ["Low", "Moderate", "High", "Severe"]
WEATHER_CONDITIONS: list[str] = ["Clear", "Overcast", "Rain", "Fog", "Storm"]
VISIBILITY_LEVELS: list[str] = ["Good", "Moderate", "Poor", "Zero"]
 
# --------------------------------------------------------------------------
# RESOURCE FLEETS (fixed pool sizes)
# --------------------------------------------------------------------------
AMBULANCE_FLEET_SIZE: int = 20
HELICOPTER_FLEET_SIZE: int = 6
MEDICAL_TEAM_COUNT: int = 16
 
RESOURCE_STATUSES: list[str] = ["Available", "Dispatched", "Returning", "Under Maintenance"]
 
# Medical team roles (distinct from combat UNITS list above, which describes
# the casualty's own soldier_unit, not the responding medical team's role).
MEDICAL_TEAM_ROLES: list[str] = [
    "Trauma Team",
    "Emergency Team",
    "Surgical Team",
    "Critical Care Team",
    "General Medical Team",
]
 
# NOTE: Simulation clock speed, refresh interval, mission log capacity, and
# random seed are RUNTIME-CONFIGURABLE parameters, not fixed business rules.
# They live in config.py, not here. See config.py.
 
# --------------------------------------------------------------------------
# ALERT THRESHOLDS
# --------------------------------------------------------------------------
UTILIZATION_WARNING_THRESHOLD: float = 60.0
UTILIZATION_HIGH_THRESHOLD: float = 80.0
UTILIZATION_CRITICAL_THRESHOLD: float = 90.0
 
# --------------------------------------------------------------------------
# FACILITY OPERATIONAL STATUS
# facility_status stores the operational LABEL (not a color name). The UI
# layer maps label -> color independently via FACILITY_STATUS_COLOR_MAP,
# so the underlying data model stays presentation-agnostic.
# --------------------------------------------------------------------------
FACILITY_STATUS_OPERATIONAL: str = "Operational"   # < 60% utilization
FACILITY_STATUS_BUSY: str = "Busy"                 # 60-80%
FACILITY_STATUS_HIGH_LOAD: str = "High Load"       # 80-90%
FACILITY_STATUS_CRITICAL: str = "Critical"         # >= 90%
 
FACILITY_STATUS_COLOR_MAP: dict[str, str] = {
    FACILITY_STATUS_OPERATIONAL: "#3E8E5A",  # green
    FACILITY_STATUS_BUSY: "#E0A526",         # yellow/amber
    FACILITY_STATUS_HIGH_LOAD: "#E07B26",    # orange
    FACILITY_STATUS_CRITICAL: "#C0392B",     # red
}
 
# --------------------------------------------------------------------------
# UI THEME (military dark theme)
# --------------------------------------------------------------------------
THEME_COLORS: dict[str, str] = {
    "background": "#0B0F17",
    "card": "#171F2F",
    "border": "#2A3346",
    "text_primary": "#FFFFFF",
    "text_secondary": "#C8CDD5",
    "primary": "#4B7F52",     # military green
    "secondary": "#4A6FA5",   # steel blue
    "warning": "#E0A526",     # amber
    "danger": "#C0392B",      # red
    "success": "#3E8E5A",     # green
}
 
SEVERITY_COLORS: dict[str, str] = {
    "Critical": THEME_COLORS["danger"],
    "Serious": "#E07B26",     # orange
    "Moderate": THEME_COLORS["warning"],
    "Mild": THEME_COLORS["success"],
}
 
# --------------------------------------------------------------------------
# MEDICAL TEAM SURGE EFFECTS
# Each dispatched medical team reduces treatment duration by a fixed amount,
# but the reduction is capped so treatment never becomes unrealistically short.
# --------------------------------------------------------------------------
MEDICAL_TEAM_TREATMENT_REDUCTION_PER_TEAM: float = 0.10  # 10%
 
MEDICAL_TEAM_MAX_TREATMENT_REDUCTION: float = 0.50       # max 50%
 
# --------------------------------------------------------------------------
# EVACUATION TRANSIT TIMES (simulated minutes)
# Represents the total time for casualty evacuation to reach the assigned
# facility. Also used as the vehicle release timer.
# --------------------------------------------------------------------------
TRANSPORT_TIME: dict[str, dict[str, int]] = {
    "Ambulance": {
        "RAP": 15,
        "ADS": 25,
        "HMV": 40,
        "FDC": 60,
    },
    "Helicopter": {
        "RAP": 8,
        "ADS": 12,
        "HMV": 18,
        "FDC": 25,
    },
}
 
# --------------------------------------------------------------------------
# VEHICLE INITIAL POSITIONS
#
# Backend-owned, deterministic starting position for each vehicle type.
# Used only at fleet-seeding time (database.init_db.seed_resource_fleets)
# so every ambulance/helicopter row has a valid grid_x/grid_y from the
# moment it is created, ensuring resource_manager.py's dispatch-origin
# capture never reads a NULL grid_x/grid_y on a vehicle's first trip.
#
# Deliberately backend-owned: resource_manager.py never imports this
# constant directly - it only ever reads vehicle.grid_x/grid_y, which
# this constant is used to initialize once, at seed time. This module
# (utils/constants.py) is the shared source of truth used across the
# simulation, database, and visualization layers, so it - not a
# frontend module - is the correct home for this value.
#
# Depth follows the same MEDEVAC-doctrine reasoning as FACILITY_CONFIG
# (front line y=2-5, RAP y=8, ADS y=25, HMV y=55, FDC y=85): ambulances
# stage forward, helicopters stage further back. These coordinates also
# match the tactical map's Operational Staging Base markers
# (map_adapter.STAGING_BASE_LAYOUT): map_adapter.py imports this dict
# directly for its "ambulance"/"helicopter" entries rather than
# redefining the values, so a freshly seeded or released vehicle's
# backend position always lines up with its visual staging-base marker.
# ("medical_team" has no entry here and keeps its own presentation-only
# coordinate in map_adapter.py, since medical teams have no travel/motion
# concept or backend grid_x/grid_y in this data model.)
# --------------------------------------------------------------------------
VEHICLE_INITIAL_POSITIONS: dict[str, dict[str, float]] = {
    "Ambulance": {"grid_x": 5.0, "grid_y": 30.0},
    "Helicopter": {"grid_x": 88.0, "grid_y": 52.0},
}