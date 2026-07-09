"""
recommendation_engine.py
 
Rule-based recommendation layer for the BMERMS AI module.
 
Combines the model predictions produced by predictor.py (transfer
requirement, predicted recovery days, return-to-duty likelihood) with
the centralized resource load assessment produced by
resource_assessment.py (resource_level, score, reason) to produce a
single, prioritized, human-readable recommendation.
 
This module is completely independent of the rest of the codebase:
    - It does NOT import database modules.
    - It does NOT import simulation engine modules.
    - It does NOT import frontend modules.
    - Its only project dependencies are predictor.py (which itself
      depends only on feature_builder.py, model_loader.py, and pandas)
      and resource_assessment.py (which depends only on the standard
      library).
 
Pipeline:
 
    simulation_state (dict)
          |
          +--> predictor.generate_predictions(simulation_state)   -> model predictions
          |
          +--> resource_assessment.assess_resource_load(simulation_state) -> resource_level, score, reason
          |
          v
    rule evaluation against predictions + resource assessment -> single recommendation
"""
 
from typing import Any, Dict, Optional
 
from .predictor import generate_predictions
from .resource_assessment import assess_resource_load
 
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
 
 
def _available_helicopters(simulation_state: Optional[Dict[str, Any]]) -> float:
    """Reads available_helicopters directly from simulation_state. This
    signal is not part of the centralized resource load score (which
    covers occupancy, queue, critical casualties, and overall resource
    shortage), so it is still read here for the evacuation-specific
    overflow-bed rule."""
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("available_helicopters"), 0.0)
  
def _safe_predictions(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Runs the prediction engine defensively: if the trained models
    cannot be loaded or prediction otherwise fails, falls back to a
    neutral prediction set rather than raising, so a recommendation can
    still be produced from the resource assessment alone."""
    try:
        return generate_predictions(simulation_state)
    except Exception:
        return {
            "transfer_required": "Unknown",
            "transfer_confidence": 0.0,
            "predicted_recovery_days": None,
            "return_to_duty": "Unknown",
            "duty_confidence": 0.0,
        }
 
 
def _safe_resource_assessment(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Runs the resource assessment defensively: falls back to a
    neutral 'Normal' assessment rather than raising, so a recommendation
    can still be produced."""
    try:
        return assess_resource_load(simulation_state)
    except Exception:
        return {
            "resource_level": "Normal",
            "score": 0.0,
            "reason": "Resource assessment unavailable.",
            "primary_driver": "",
        }
 
 
# --------------------------------------------------------------------------
# Rule definitions
# --------------------------------------------------------------------------
# Rules are evaluated in priority order (most urgent first). The first
# rule whose condition is met produces the returned recommendation.
# All rules use resource["resource_level"], resource["score"], and
# resource["reason"] rather than checking occupancy_rate, queue_length,
# or critical_casualties directly.
 
def _rule_critical_casualties(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if resource["resource_level"] == "Critical Load" and resource["primary_driver"] == "critical":
        return {
            "recommendation": "Pre-stage helicopter support.",
            "reason": (
                f"{resource['reason']} "
                f"The transfer model predicts transfer_required={predictions['transfer_required']}."
            ),
            "expected_benefit": "Reduces evacuation delay for critical casualties and improves transfer readiness.",
            "confidence": round(predictions["transfer_confidence"], 2),
        }
    return None
 
 
def _rule_high_occupancy(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if resource["resource_level"] in ("High Load", "Critical Load") and resource["primary_driver"] == "occupancy":
        return {
            "recommendation": "Deploy additional medical team to ADS.",
            "reason": resource["reason"],
            "expected_benefit": "Increases treatment throughput and reduces risk of care delays under high occupancy.",
            "confidence": predictions["duty_confidence"],
        }
    return None
 
 
def _rule_high_queue(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if resource["resource_level"] in ("High Load", "Critical Load") and resource["primary_driver"] == "queue":
        return {
            "recommendation": "Reroute casualties to RAP-2.",
            "reason": resource["reason"],
            "expected_benefit": "Balances patient load across facilities and reduces average wait time.",
            "confidence": predictions["transfer_confidence"],
        }
    return None
 
 
def _rule_resource_shortage(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if _available_helicopters(simulation_state) <= 0 and (
        resource["resource_level"] == "Critical Load" or predictions["transfer_required"] == "Yes"
    ):
        return {
            "recommendation": "Prepare overflow beds.",
            "reason": (
                "No helicopters are currently available while resource load is elevated "
                f"({resource['reason']})."
            ),
            "expected_benefit": "Ensures continuity of care while evacuation resources are unavailable.",
            "confidence": predictions["duty_confidence"],
        }
    return None
 
 
def _rule_default(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "recommendation": "Continue standard operations and monitoring.",
        "reason": resource["reason"],
        "expected_benefit": "Maintains current operational efficiency with no additional resource reallocation required.",
        "confidence": max(
            predictions.get("transfer_confidence") or 0.0,
            predictions.get("duty_confidence") or 0.0,
        ),
    }
 
 
RULES = [
    _rule_critical_casualties,
    _rule_high_occupancy,
    _rule_high_queue,
    _rule_resource_shortage,
]
 
 
# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
 
def generate_recommendations(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate a single, prioritized, rule-based recommendation for the
    given simulation state.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        Resource load signals (occupancy_rate, queue_length,
        critical_casualties, available_medical_teams,
        available_helicopters) are documented in resource_assessment.py.
        The full set of keys used for model predictions is documented
        in feature_builder.py. Any missing or malformed values default
        safely and never raise KeyError.
 
    Returns
    -------
    dict
        {
            "recommendation": str,
            "reason": str,
            "expected_benefit": str,
            "confidence": float
        }
    """
    resource = _safe_resource_assessment(simulation_state)
    predictions = _safe_predictions(simulation_state)
 
    for rule in RULES:
        result = rule(simulation_state, resource, predictions)
        if result is not None:
            return result
 
    return _rule_default(simulation_state, resource, predictions)

def get_dashboard_recommendation(simulation_state: dict) -> dict:
    """
    Lightweight wrapper used by the Dashboard page.
    Returns a recommendation dictionary safe for frontend rendering.
    """
    recommendation = generate_recommendations(simulation_state)

    return {
        "recommendation": recommendation.get(
            "recommendation",
            "Continue standard operations and monitoring."
        ),
        "reason": recommendation.get(
            "reason",
            "No recommendation available."
        ),
        "expected_benefit": recommendation.get(
            "expected_benefit",
            ""
        ),
        "confidence": round(
            recommendation.get("confidence", 0.0),
            1
        ),
    }