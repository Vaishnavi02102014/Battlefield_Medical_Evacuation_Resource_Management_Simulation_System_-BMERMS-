"""
feature_builder.py
 
Converts live simulation-state dictionaries into the plain, model-ready
feature dictionaries expected by the BMERMS AI models (transfer_model.pkl,
recovery_model.pkl, duty_model.pkl).
 
This module is completely independent of the rest of the codebase:
    - It does NOT import database modules.
    - It does NOT import simulation engine modules.
    - It does NOT import frontend modules.
    - It does NOT import pandas, numpy, joblib, or any model-loading code.
 
It only performs dictionary-to-dictionary translation using the Python
standard library, so it can be safely imported and unit-tested in
isolation from the rest of the system.
 
--------------------------------------------------------------------------
Expected `simulation_state` structure
--------------------------------------------------------------------------
`simulation_state` is a plain Python dictionary produced by the simulation
engine (or any caller) describing the current state of a casualty and/or
the facility handling them. No key is required — every key is read
defensively with `.get(...)` and a sensible default is substituted when a
key is absent, so this function never raises KeyError.
 
The builder recognizes the following logical fields. For each, several
common aliases are accepted (snake_case naming, as the simulation engine
is expected to emit) since the exact key names used by the simulation
engine may vary:
 
    Casualty / soldier attributes:
        age                    -> "age"
        rank                   -> "rank"
        soldier_unit           -> "soldier_unit", "unit"
        injury_type            -> "injury_type", "injury"
        severity               -> "severity"                     (str: "Mild"/"Moderate"/"Serious"/"Critical"
                                                                    or already-numeric 0-3)
        triage_priority        -> "triage_priority", "triage"    (str: "P0"-"P3" or already-numeric 0-3)
 
    Location / sector attributes:
        battle_sector          -> "battle_sector", "sector"      (str name e.g. "Alpha", or int index 1-5)
        latitude                -> "latitude", "lat"
        longitude               -> "longitude", "lon", "lng"
 
    Facility / treatment attributes:
        initial_treatment_center    -> "initial_treatment_center"
        assigned_treatment_center   -> "assigned_treatment_center", "facility_type", "facility"
        treatment_duration_hours    -> "treatment_duration_hours", "treatment_hours"
        bed_status                  -> "bed_status"               (str: "Occupied"/"Vacated"; may be
                                                                     derived from "occupancy_rate" if absent)
        queue_wait_minutes           -> "queue_wait_minutes", "queue_length", "queue_minutes"
        evacuation_mode               -> "evacuation_mode"        (may be derived from
                                                                     "available_helicopters" if absent)
 
    System load attributes:
        resource_level          -> "resource_level"               (str: "Normal"/"High Load"/"Critical Load";
                                                                      may be derived from "occupancy_rate",
                                                                      "queue_length", and "critical_casualties"
                                                                      if not given directly)
        occupancy_rate           -> "occupancy_rate"               (0-100, used for derivations only)
        critical_casualties       -> "critical_casualties"         (int, used for derivations only)
        available_helicopters      -> "available_helicopters"      (int, used for derivations only)
 
Example simulation_state:
    {
        "battle_sector": 4,
        "facility_type": "ADS",
        "occupancy_rate": 92,
        "queue_length": 15,
        "critical_casualties": 5,
        "available_helicopters": 1,
    }
 
--------------------------------------------------------------------------
Output
--------------------------------------------------------------------------
Each `build_*_features` function returns a plain `dict` whose keys match
the raw column names the corresponding trained model pipeline expects
(the pipeline itself performs one-hot encoding of categorical values, so
categorical fields are returned as strings; `Severity` and
`Triage_Priority` are returned as already ordinal-encoded integers,
matching how the training data was prepared).
"""
 
from typing import Any, Dict, Optional
 
# --------------------------------------------------------------------------
# Constants (duplicated locally, not imported, to keep this module fully
# independent of train_models.py / model_loader.py)
# --------------------------------------------------------------------------
 
SEVERITY_ORDER = {"Mild": 0, "Moderate": 1, "Serious": 2, "Critical": 3}
TRIAGE_ORDER = {"P3": 0, "P2": 1, "P1": 2, "P0": 3}
 
# Battle_Sector categories as they actually appear in the synthetic
# dataset (Battlefield_Casualties sheet): {"Alpha", "Bravo", "Charlie",
# "Delta", "Echo"}. The integer keys below are only a convenience index
# for callers that supply a numeric sector (e.g. simulation_state
# {"battle_sector": 4}); the string values themselves are exactly the
# five categories observed in the training data - no sector name is
# invented.
BATTLE_SECTOR_NAMES = {1: "Alpha", 2: "Bravo", 3: "Charlie", 4: "Delta", 5: "Echo"}
 
# Resource_Level categories exactly as they appear in the training data.
VALID_RESOURCE_LEVELS = {"Normal", "High Load", "Critical Load"}
 
# Bed_Status categories exactly as they appear in the training data.
VALID_BED_STATUSES = {"Occupied", "Vacated"}
 
# Evacuation_Mode categories exactly as they appear in the training data.
VALID_EVACUATION_MODES = {"Ambulance", "Armoured Ambulance", "Helicopter", "Foot"}
 
# Sensible defaults for every raw feature, used whenever a value cannot
# be found or derived from simulation_state. Every categorical default
# is one of the exact categories observed by the synthetic training
# dataset; every numeric default is the median value observed for that
# column in the synthetic training dataset (so defaults fall inside the
# real, observed data range rather than an arbitrary placeholder).
DEFAULTS = {
    "Battle_Sector": "Alpha",
    "Latitude": 0.0,          # dataset median latitude (range ~26.0-31.0)
    "Longitude": 0.0,         # dataset median longitude (range ~68.0-77.0)
    "Soldier_Unit": "Infantry",
    "Rank": "Sepoy",
    "Age": 30,                  # dataset median age (range 20-45)
    "Injury_Type": "Laceration",
    "Severity": "Moderate",
    "Triage_Priority": "P2",
    "Initial_Treatment_Center": "RAP",
    "Assigned_Treatment_Center": "RAP",
    "Treatment_Duration_Hours": 0,    # dataset median (range 2-480)
    "Bed_Status": "Vacated",
    "Queue_Wait_Minutes": 0,          # dataset median (range 0-180)
    "Evacuation_Mode": "Ambulance",
    "Resource_Level": "Normal",
}
 
# --------------------------------------------------------------------------
# Per-model feature sets
# --------------------------------------------------------------------------
# Each model was trained on its own feature matrix (target columns and
# Current_Status removed as leakage). These lists mirror the feature columns used during model training. and reflect exactly the
# columns each model expects, in order.
 
TRANSFER_FEATURES = [
    "Battle_Sector",
    "Latitude",
    "Longitude",
    "Soldier_Unit",
    "Rank",
    "Age",
    "Injury_Type",
    "Severity",
    "Triage_Priority",
    "Initial_Treatment_Center",
    "Assigned_Treatment_Center",
    "Treatment_Duration_Hours",
    "Bed_Status",
    "Queue_Wait_Minutes",
    "Evacuation_Mode",
    "Resource_Level",
]
 
RECOVERY_FEATURES = [
    "Battle_Sector",
    "Latitude",
    "Longitude",
    "Soldier_Unit",
    "Rank",
    "Age",
    "Injury_Type",
    "Severity",
    "Triage_Priority",
    "Initial_Treatment_Center",
    "Assigned_Treatment_Center",
    "Treatment_Duration_Hours",
    "Bed_Status",
    "Queue_Wait_Minutes",
    "Evacuation_Mode",
    "Resource_Level",
]
 
DUTY_FEATURES = [
    "Battle_Sector",
    "Latitude",
    "Longitude",
    "Soldier_Unit",
    "Rank",
    "Age",
    "Injury_Type",
    "Severity",
    "Triage_Priority",
    "Initial_Treatment_Center",
    "Assigned_Treatment_Center",
    "Treatment_Duration_Hours",
    "Bed_Status",
    "Queue_Wait_Minutes",
    "Evacuation_Mode",
    "Resource_Level",
]
 
 
# --------------------------------------------------------------------------
# Small internal helpers
# --------------------------------------------------------------------------
 
def _get_first(state: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the value of the first key present (and not None) in
    `state` out of the given candidate `keys`. Falls back to `default`
    if none are present. Never raises KeyError."""
    if not isinstance(state, dict):
        return default
    for key in keys:
        value = state.get(key)
        if value is not None:
            return value
    return default
 
 
def _coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    try:
        text = str(value).strip()
        return text if text else default
    except Exception:
        return default
 
 
def _coerce_number(value: Any, default):
    if value is None:
        return default
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default
 
 
def _encode_severity(value: Any) -> int:
    """Accepts either a Severity label ("Mild".."Critical") or an
    already-numeric value (0-3) and returns the ordinal-encoded int
    used by the trained models. Falls back to the default severity."""
    if value is None:
        value = DEFAULTS["Severity"]
    if isinstance(value, (int, float)):
        numeric = int(value)
        return numeric if numeric in SEVERITY_ORDER.values() else SEVERITY_ORDER[DEFAULTS["Severity"]]
    label = _coerce_str(value, DEFAULTS["Severity"]).title()
    return SEVERITY_ORDER.get(label, SEVERITY_ORDER[DEFAULTS["Severity"]])
 
 
def _encode_triage(value: Any) -> int:
    """Accepts either a Triage_Priority label ("P0".."P3") or an
    already-numeric value (0-3) and returns the ordinal-encoded int
    used by the trained models. Falls back to the default priority."""
    if value is None:
        value = DEFAULTS["Triage_Priority"]
    if isinstance(value, (int, float)):
        numeric = int(value)
        return numeric if numeric in TRIAGE_ORDER.values() else TRIAGE_ORDER[DEFAULTS["Triage_Priority"]]
    label = _coerce_str(value, DEFAULTS["Triage_Priority"]).upper()
    return TRIAGE_ORDER.get(label, TRIAGE_ORDER[DEFAULTS["Triage_Priority"]])
 
 
def _resolve_battle_sector(value: Any) -> str:
    if value is None:
        return DEFAULTS["Battle_Sector"]
    if isinstance(value, (int, float)):
        return BATTLE_SECTOR_NAMES.get(int(value), DEFAULTS["Battle_Sector"])
    label = _coerce_str(value, DEFAULTS["Battle_Sector"]).title()
    return label if label in BATTLE_SECTOR_NAMES.values() else DEFAULTS["Battle_Sector"]
 
 
def _derive_resource_level(state: Dict[str, Any]) -> str:
    """Derives an approximate Resource_Level from occupancy/queue/
    critical-casualty signals when it is not supplied directly. This is
    a best-effort heuristic only, intended as a fallback."""
    explicit = _get_first(state, "resource_level")
    if explicit is not None:
        label = _coerce_str(explicit, DEFAULTS["Resource_Level"]).title()
        return label if label in VALID_RESOURCE_LEVELS else DEFAULTS["Resource_Level"]
 
    occupancy_rate = _coerce_number(_get_first(state, "occupancy_rate"), 0.0)
    queue_length = _coerce_number(_get_first(state, "queue_length", "queue_wait_minutes"), 0)
    critical_casualties = _coerce_number(_get_first(state, "critical_casualties"), 0)
 
    if occupancy_rate >= 90 or critical_casualties >= 5 or queue_length >= 15:
        return "Critical Load"
    if occupancy_rate >= 70 or critical_casualties >= 2 or queue_length >= 5:
        return "High Load"
    return "Normal"
 
 
def _derive_bed_status(state: Dict[str, Any]) -> str:
    explicit = _get_first(state, "bed_status")
    if explicit is not None:
        label = _coerce_str(explicit, DEFAULTS["Bed_Status"]).title()
        return label if label in VALID_BED_STATUSES else DEFAULTS["Bed_Status"]
 
    occupancy_rate = _coerce_number(_get_first(state, "occupancy_rate"), None)
    if occupancy_rate is not None:
        return "Occupied" if occupancy_rate >= 50 else "Vacated"
    return DEFAULTS["Bed_Status"]
 
 
def _derive_evacuation_mode(state: Dict[str, Any]) -> str:
    explicit = _get_first(state, "evacuation_mode")
    if explicit is not None:
        label = _coerce_str(explicit, DEFAULTS["Evacuation_Mode"]).title()
        return label if label in VALID_EVACUATION_MODES else DEFAULTS["Evacuation_Mode"]
 
    available_helicopters = _coerce_number(_get_first(state, "available_helicopters"), None)
    if available_helicopters is not None:
        return "Helicopter" if available_helicopters > 0 else "Ambulance"
    return DEFAULTS["Evacuation_Mode"]
 
 
# --------------------------------------------------------------------------
# Core shared feature extraction
# --------------------------------------------------------------------------
 
def _build_all_raw_features(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds the full raw feature set shared by all three models. Every
    lookup is defensive: missing or malformed values fall back to
    sensible defaults, and this function never raises KeyError."""
    state = simulation_state if isinstance(simulation_state, dict) else {}
 
    features = {
        "Battle_Sector": _resolve_battle_sector(
            _get_first(state, "battle_sector", "sector")
        ),
        "Latitude": _coerce_number(_get_first(state, "latitude", "lat"), DEFAULTS["Latitude"]),
        "Longitude": _coerce_number(_get_first(state, "longitude", "lon", "lng"), DEFAULTS["Longitude"]),
        "Soldier_Unit": _coerce_str(
            _get_first(state, "soldier_unit", "unit"), DEFAULTS["Soldier_Unit"]
        ),
        "Rank": _coerce_str(_get_first(state, "rank"), DEFAULTS["Rank"]),
        "Age": _coerce_number(_get_first(state, "age"), DEFAULTS["Age"]),
        "Injury_Type": _coerce_str(
            _get_first(state, "injury_type", "injury"), DEFAULTS["Injury_Type"]
        ),
        "Severity": _encode_severity(_get_first(state, "severity")),
        "Triage_Priority": _encode_triage(_get_first(state, "triage_priority", "triage")),
        "Initial_Treatment_Center": _coerce_str(
            _get_first(state, "initial_treatment_center"),
            DEFAULTS["Initial_Treatment_Center"],
        ),
        "Assigned_Treatment_Center": _coerce_str(
            _get_first(state, "assigned_treatment_center", "facility_type", "facility"),
            DEFAULTS["Assigned_Treatment_Center"],
        ),
        "Treatment_Duration_Hours": _coerce_number(
            _get_first(state, "treatment_duration_hours", "treatment_hours"),
            DEFAULTS["Treatment_Duration_Hours"],
        ),
        "Bed_Status": _derive_bed_status(state),
        "Queue_Wait_Minutes": _coerce_number(
            _get_first(state, "queue_wait_minutes", "queue_length", "queue_minutes"),
            DEFAULTS["Queue_Wait_Minutes"],
        ),
        "Evacuation_Mode": _derive_evacuation_mode(state),
        "Resource_Level": _derive_resource_level(state),
    }
    return features
 
 
# --------------------------------------------------------------------------
# Public builder functions
# --------------------------------------------------------------------------
 
def build_transfer_features(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the model-ready feature dictionary for the transfer model
    (predicts Transfer_Required).
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See module docstring for the full list of recognized keys.
        Any missing or malformed keys are filled with sensible defaults;
        this function never raises KeyError.
 
    Returns
    -------
    dict
        Plain dictionary of raw feature values, keyed by the same column
        names used to train transfer_model.pkl (Severity and
        Triage_Priority are ordinal-encoded integers; all other
        categorical fields are returned as strings for the model
        pipeline's own one-hot encoding step).
    """
    full = _build_all_raw_features(simulation_state)
    return {name: full[name] for name in TRANSFER_FEATURES}
 
 
def build_recovery_features(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the model-ready feature dictionary for the recovery model
    (predicts Predicted_Recovery_Days).
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See module docstring for the full list of recognized keys.
        Any missing or malformed keys are filled with sensible defaults;
        this function never raises KeyError.
 
    Returns
    -------
    dict
        Plain dictionary of raw feature values, keyed by the same column
        names used to train recovery_model.pkl.
    """
    full = _build_all_raw_features(simulation_state)
    return {name: full[name] for name in RECOVERY_FEATURES}
 
 
def build_duty_features(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the model-ready feature dictionary for the duty model
    (predicts Return_to_Duty).
 
    Note: Current_Status is intentionally excluded from the feature set
    (it was excluded during training to avoid target leakage), so it is
    never read from simulation_state here.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See module docstring for the full list of recognized keys.
        Any missing or malformed keys are filled with sensible defaults;
        this function never raises KeyError.
 
    Returns
    -------
    dict
        Plain dictionary of raw feature values, keyed by the same column
        names used to train duty_model.pkl.
    """
    full = _build_all_raw_features(simulation_state)
    return {name: full[name] for name in DUTY_FEATURES}
 
 
def build_feature_vector(
    simulation_state: Optional[Dict[str, Any]], prediction_type: str
) -> Dict[str, Any]:
    """
    Dispatch helper that builds the appropriate model-ready feature
    dictionary for a given prediction type.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See module docstring for the full list of recognized keys.
    prediction_type : str
        One of "transfer", "recovery", or "duty".
 
    Returns
    -------
    dict
        Plain dictionary of raw feature values appropriate for the
        requested prediction type.
 
    Raises
    ------
    ValueError
        If `prediction_type` is not one of "transfer", "recovery", or
        "duty". (This is the only error this module ever raises;
        missing/malformed simulation_state keys never raise.)
    """
    builders = {
        "transfer": build_transfer_features,
        "recovery": build_recovery_features,
        "duty": build_duty_features,
    }
 
    builder = builders.get(prediction_type)
    if builder is None:
        raise ValueError(
            f"Invalid prediction_type '{prediction_type}'. "
            f"Expected one of: {sorted(builders.keys())}."
        )
 
    return builder(simulation_state)