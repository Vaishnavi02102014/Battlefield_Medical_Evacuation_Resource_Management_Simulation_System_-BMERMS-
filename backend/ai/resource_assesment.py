"""
resource_assessment.py
 
Centralized, rule-based resource load assessment for the BMERMS AI
module.
 
Computes a weighted 0-100 load score from live operational signals
(occupancy, queue, critical casualties, available resources) and maps
that score onto a Resource_Level category using configurable
thresholds. Weights and thresholds are stored in resource_rules.json
so they can be tuned without touching code.
 
This module is completely independent of the rest of the codebase:
    - It does NOT import database modules.
    - It does NOT import simulation engine modules.
    - It does NOT import frontend modules.
    - It only depends on the Python standard library (json, pathlib).
"""
 
import json
from pathlib import Path
from typing import Any, Dict, Optional
 
BASE_DIR = Path(__file__).resolve().parent
RESOURCE_RULES_PATH = BASE_DIR / "resource_rules.json"
 
DEFAULT_RULES = {
    "weights": {
        "occupancy": 0.5,
        "queue": 0.2,
        "critical": 0.2,
        "resources": 0.1,
    },
    "thresholds": {
        "high": 70,
        "critical": 90,
    },
}
 
# Normalization caps used to scale raw operational signals onto a 0-100
# range before weighting. These are fixed, documented assumptions:
QUEUE_NORMALIZATION_CAP = 30       # queue_length at/above this scores 100
CRITICAL_NORMALIZATION_CAP = 10    # critical_casualties at/above this scores 100
RESOURCE_UNIT_RELIEF = 20          # each available team/helicopter reduces shortage score by this much
 
 
# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
 
def _coerce_number(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
 
 
def _load_rules() -> Dict[str, Any]:
    """Loads weights/thresholds from resource_rules.json if present,
    otherwise falls back to DEFAULT_RULES. Never raises."""
    if RESOURCE_RULES_PATH.exists():
        try:
            with open(RESOURCE_RULES_PATH, "r") as f:
                rules = json.load(f)
            weights = rules.get("weights", DEFAULT_RULES["weights"])
            thresholds = rules.get("thresholds", DEFAULT_RULES["thresholds"])
            return {"weights": weights, "thresholds": thresholds}
        except (json.JSONDecodeError, OSError):
            return DEFAULT_RULES
    return DEFAULT_RULES
 
 
def _extract_signals(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Safely extracts the raw operational signals used for scoring.
    Missing or malformed values default to 0, and this function never
    raises KeyError."""
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return {
        "occupancy_rate": _coerce_number(state.get("occupancy_rate"), 0.0),
        "queue_length": _coerce_number(state.get("queue_length"), 0.0),
        "critical_casualties": _coerce_number(state.get("critical_casualties"), 0.0),
        "available_medical_teams": _coerce_number(state.get("available_medical_teams"), 0.0),
        "available_helicopters": _coerce_number(state.get("available_helicopters"), 0.0),
    }
 
 
def _normalize(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return max(0.0, min(value / cap, 1.0)) * 100
 
 
def _resource_shortage_score(available_medical_teams: float, available_helicopters: float) -> float:
    relief = (available_medical_teams + available_helicopters) * RESOURCE_UNIT_RELIEF
    return max(0.0, 100.0 - relief)
 
 
# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
 
def assess_resource_load(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Assess the current resource load from a simulation state using
    weighted, rule-based scoring.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current facility/system state.
        Recognized keys:
            occupancy_rate           (0-100)
            queue_length
            critical_casualties
            available_medical_teams
            available_helicopters
        Any missing or malformed values default to 0 and never raise
        KeyError.
 
    Returns
    -------
    dict
        {
            "resource_level": "Normal" | "High Load" | "Critical Load",
            "score": float,
            "reason": str
        }
    """
    rules = _load_rules()
    weights = rules["weights"]
    thresholds = rules["thresholds"]
 
    signals = _extract_signals(simulation_state)
 
    occupancy_component = max(0.0, min(signals["occupancy_rate"], 100.0))
    queue_component = _normalize(signals["queue_length"], QUEUE_NORMALIZATION_CAP)
    critical_component = _normalize(signals["critical_casualties"], CRITICAL_NORMALIZATION_CAP)
    resource_component = _resource_shortage_score(
        signals["available_medical_teams"], signals["available_helicopters"]
    )
 
    components = {
        "occupancy": occupancy_component,
        "queue": queue_component,
        "critical": critical_component,
        "resources": resource_component,
    }
 
    score = (
        components["occupancy"] * weights.get("occupancy", 0.0)
        + components["queue"] * weights.get("queue", 0.0)
        + components["critical"] * weights.get("critical", 0.0)
        + components["resources"] * weights.get("resources", 0.0)
    )
    score = round(max(0.0, min(score, 100.0)), 2)
 
    if score >= thresholds.get("critical", 90):
        resource_level = "Critical Load"
    elif score >= thresholds.get("high", 70):
        resource_level = "High Load"
    else:
        resource_level = "Normal"
 
    top_factor = max(components, key=components.get)
    reason = (
        f"Weighted load score is {score:.2f} "
        f"(occupancy={components['occupancy']:.0f}, queue={components['queue']:.0f}, "
        f"critical={components['critical']:.0f}, resources={components['resources']:.0f}); "
        f"primary driver: {top_factor}."
    )
 
    return {
        "resource_level": resource_level,
        "score": score,
        "reason": reason,
        "primary_driver": top_factor,
    }
 
 
def save_default_rules() -> None:
    """
    Writes the default weights/thresholds configuration to
    resource_rules.json in this module's directory, creating or
    overwriting the file.
    """
    with open(RESOURCE_RULES_PATH, "w") as f:
        json.dump(DEFAULT_RULES, f, indent=2)
 
 
if __name__ == "__main__":
    save_default_rules()