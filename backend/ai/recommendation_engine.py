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
CONFIDENCE_HIGH = 90.0
CONFIDENCE_MEDIUM_HIGH = 75.0
CONFIDENCE_MEDIUM = 65.0

CONFIDENCE_CORROBORATION_BONUS = 5.0
CONFIDENCE_ACTIONABILITY_BONUS = 10.0
CONFIDENCE_ACTIONABILITY_PENALTY = 15.0

CONFIDENCE_FLOOR_HIGH = 85.0
CONFIDENCE_FLOOR_MEDIUM = 65.0
CONFIDENCE_FLOOR_LOW = 50.0
CONFIDENCE_CEILING = 100.0
 
def _coerce_number(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
    
def _clamp_confidence(value: float, floor: float) -> float:
    return round(
        max(floor, min(value, CONFIDENCE_CEILING)),
        2,
    )
 
 
def _available_helicopters(simulation_state: Optional[Dict[str, Any]]) -> float:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("available_helicopters"), 0.0)

def _available_ambulances(simulation_state: Optional[Dict[str, Any]]) -> float:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("available_ambulances"), 0.0)


def _critical_casualties(simulation_state: Optional[Dict[str, Any]]) -> float:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("critical_casualties"), 0.0)

def _occupancy_rate(simulation_state: Optional[Dict[str, Any]]) -> float:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("occupancy_rate"), 0.0)


def _queue_length(simulation_state: Optional[Dict[str, Any]]) -> float:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("queue_length"), 0.0)

def _highest_load_facility(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return state.get("highest_load_facility") or {}


def _lowest_load_facility(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return state.get("lowest_load_facility") or {}


def _casualty_word(count: float) -> str:
    return "casualty" if round(count) == 1 else "casualties"

def _available_medical_teams(simulation_state: Optional[Dict[str, Any]]) -> float:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return _coerce_number(state.get("available_medical_teams"), 0.0)

def _highest_queue_facility(simulation_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    state = simulation_state if isinstance(simulation_state, dict) else {}
    return state.get("highest_queue_facility") or {}


def _humanize_transfer_prediction(predictions: Dict[str, Any]) -> str:
    status = predictions.get("transfer_required")

    if status == "Yes":
        return "the transfer model predicts an evacuation transfer will be required"

    if status == "No":
        return "the transfer model predicts an evacuation transfer will not be required"

    return "the transfer model prediction is currently unavailable"
  
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
        critical = _critical_casualties(simulation_state)
        word = _casualty_word(critical)
        transfer_clause = _humanize_transfer_prediction(predictions)

        confidence = CONFIDENCE_HIGH

        if predictions.get("transfer_required") == "Yes":
            confidence += CONFIDENCE_CORROBORATION_BONUS

        confidence = _clamp_confidence(
            confidence,
            CONFIDENCE_FLOOR_HIGH,
        )

        return {
            "recommendation":
                "Pre-stage additional helicopter support for critical casualty evacuation.",

            "reason":
                f"Critical casualty count has reached {int(critical)} {word}, the primary driver behind the current {resource['resource_level']} classification, and {transfer_clause}.",

            "expected_benefit":
                f"Commits helicopter capacity to the {int(critical)} critical {word} while it remains available, ahead of any subsequent shortage that would otherwise force evacuation onto slower ground transport.",

            "confidence": confidence,
        }
    return None

def _rule_no_evacuation_assets(
    simulation_state: Optional[Dict[str, Any]],
    resource: Dict[str, Any],
    predictions: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    if (
        _available_helicopters(simulation_state) <= 0
        and _available_ambulances(simulation_state) <= 0
        and _critical_casualties(simulation_state) > 0
    ):
        critical = _critical_casualties(simulation_state)
        word = _casualty_word(critical)
        confidence = CONFIDENCE_HIGH

        if resource["resource_level"] in ("High Load", "Critical Load"):
            confidence += CONFIDENCE_CORROBORATION_BONUS

        if resource["primary_driver"] in ("critical", "resources"):
            confidence += CONFIDENCE_CORROBORATION_BONUS

        confidence = _clamp_confidence(
            confidence,
            CONFIDENCE_FLOOR_HIGH,
        )

        return {
            "recommendation":
                "Activate contingency evacuation protocol for critical casualty transport.",

            "reason":
                f"No helicopters or ambulances are currently available while "
                f"{int(critical)} critical {word} require evacuation. "
                f"Resource load is classified as {resource['resource_level']}.",

            "expected_benefit":
                f"Restores the ability to evacuate the {int(critical)} critical {word} to their designated treatment facility instead of leaving them without any evacuation option.",

            "confidence": confidence,

                }

    return None
 
 
def _rule_high_occupancy(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if resource["resource_level"] in ("High Load", "Critical Load") and resource["primary_driver"] == "occupancy":
        occupancy = _occupancy_rate(simulation_state)

        facility = _highest_load_facility(simulation_state)

        facility_name = (
            facility.get("name")
            or facility.get("facility_type")
            or "the highest-load facility"
        )
        confidence = (
                CONFIDENCE_HIGH
                if resource["resource_level"] == "Critical Load"
                else CONFIDENCE_MEDIUM_HIGH
            )

        if _available_medical_teams(simulation_state) > 0:
            confidence += CONFIDENCE_ACTIONABILITY_BONUS
        else:
            confidence -= CONFIDENCE_ACTIONABILITY_PENALTY

        confidence = _clamp_confidence(
            confidence,
            CONFIDENCE_FLOOR_LOW,
        )

        return {
            "recommendation":
                f"Deploy an additional medical team to {facility_name}.",

            "reason":
                f"{facility_name} is currently the highest-load facility while theatre-wide occupancy has reached "
                f"{occupancy:.0f}%, the primary driver behind the current {resource['resource_level']} classification.",

            "expected_benefit":
                 f"Shortens treatment duration at {facility_name}, freeing beds more quickly for incoming casualties.",

            "confidence": confidence,
                }
    
    return None
 
 
def _rule_high_queue(
    simulation_state: Optional[Dict[str, Any]],
    resource: Dict[str, Any],
    predictions: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    if (
        resource["resource_level"] in ("High Load", "Critical Load")
        and resource["primary_driver"] == "queue"
    ):
        queue = _queue_length(simulation_state)
        word = _casualty_word(queue)
        facility = _highest_queue_facility(simulation_state)

        facility_name = (
            facility.get("name")
            or facility.get("facility_type")
            or "the affected facility"
        )

        # Is a medical team currently available?
        teams_available = _available_medical_teams(simulation_state) > 0

        # Base confidence
        confidence = (
            CONFIDENCE_HIGH
            if resource["resource_level"] == "Critical Load"
            else CONFIDENCE_MEDIUM_HIGH
        )

        # Actionability adjustment
        if teams_available:
            confidence += CONFIDENCE_ACTIONABILITY_BONUS
        else:
            confidence -= CONFIDENCE_ACTIONABILITY_PENALTY

        confidence = _clamp_confidence(
            confidence,
            CONFIDENCE_FLOOR_LOW,
        )

        # Medical teams available
        if teams_available:
            return {
                "recommendation":
                    f"Deploy additional medical team support at {facility_name} to increase treatment throughput.",

                "reason":
                    f"Casualty queue length has reached {int(queue)} {word} at {facility_name}, the primary driver behind the current {resource['resource_level']} classification.",

                "expected_benefit":
                    f"Speeds treatment turnover at {facility_name}, reducing casualty waiting time without "
                    f"reassigning casualties across the fixed severity-based evacuation chain.",

                "confidence": confidence,
            }

        # No medical teams available
        return {
            "recommendation":
                f"Request additional medical team allocation — no teams are currently available "
                f"for automatic surge dispatch at {facility_name}.",

            "reason":
                f"Casualty queue length has reached {int(queue)} {word} at {facility_name}, the primary driver behind the current {resource['resource_level']} classification, and no medical teams remain available for surge dispatch.",

            "expected_benefit":
                f"Restores the ability to automatically dispatch a medical team to {facility_name}, reducing treatment backlog and casualty waiting time.",

            "confidence": confidence,
        }

    return None
 
 
def _rule_resource_shortage(
    simulation_state: Optional[Dict[str, Any]], resource: Dict[str, Any], predictions: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if (
        _available_helicopters(simulation_state) <= 0
        and _critical_casualties(simulation_state) > 0
    ):
        
        critical = _critical_casualties(simulation_state)
        word = _casualty_word(critical)

        confidence = CONFIDENCE_MEDIUM

        if resource["resource_level"] == "Critical Load":
            confidence += CONFIDENCE_CORROBORATION_BONUS

        confidence = _clamp_confidence(
            confidence,
            CONFIDENCE_FLOOR_MEDIUM,
        )

        return {
            "recommendation":
                "Request helicopter reinforcement and prioritize remaining evacuation assets for critical and serious casualties.",

            "reason":
                f"Overall resource availability is classified as {resource['resource_level']}, while "
                f"{int(critical)} critical {word} continue to require helicopter evacuation.",

            "expected_benefit":
                f"Restores helicopter availability for rapid evacuation of {int(critical)} critical {word} while allowing available ground evacuation assets to continue supporting lower-priority transports.",

            "confidence": confidence,  
        }
    return None
 
def _rule_ambulance_shortage(
    simulation_state: Optional[Dict[str, Any]],
    resource: Dict[str, Any],
    predictions: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    if (
        _available_ambulances(simulation_state) <= 0
        and _available_helicopters(simulation_state) > 0
    ):
        
        confidence = CONFIDENCE_MEDIUM

        if resource["resource_level"] != "Normal":
            confidence += CONFIDENCE_CORROBORATION_BONUS

        if resource["primary_driver"] == "resources":
            confidence += CONFIDENCE_CORROBORATION_BONUS

        confidence = _clamp_confidence(
            confidence,
            CONFIDENCE_FLOOR_MEDIUM,
        )

        return {
            "recommendation":
                "Request ambulance reinforcement and prioritize available ground evacuation resources for moderate casualties.",

            "reason":
                f"All ambulances are currently committed while helicopter resources remain available for critical casualty evacuation.",

            "expected_benefit":
                "Restores dedicated ground evacuation capacity for future casualty transports while helicopters remain focused on critical evacuations.",
            
            "confidence": confidence,
        }

    return None

def _rule_default(
    simulation_state: Optional[Dict[str, Any]],
    resource: Dict[str, Any],
    predictions: Dict[str, Any],
) -> Dict[str, Any]:

    occupancy = _occupancy_rate(simulation_state)
    queue = _queue_length(simulation_state)

    # Compute confidence BEFORE returning
    if resource["resource_level"] == "Normal":
        confidence = CONFIDENCE_HIGH

        if (
            _available_helicopters(simulation_state) > 0
            and _available_ambulances(simulation_state) > 0
            and _available_medical_teams(simulation_state) > 0
        ):
            confidence += CONFIDENCE_CORROBORATION_BONUS
    else:
        confidence = CONFIDENCE_MEDIUM

    confidence = _clamp_confidence(
        confidence,
        CONFIDENCE_FLOOR_LOW,
    )

    return {
        "recommendation":
            "Continue current evacuation and treatment operations.",

        "reason":
            "No operational thresholds requiring intervention have been exceeded, and evacuation and treatment resources remain within expected operating limits.",

        "expected_benefit":
            "Maintains stable casualty evacuation and treatment flow without unnecessary resource redistribution.",

        "confidence": confidence,
    }
    
 
 
RULES = [
    _rule_no_evacuation_assets,
    _rule_critical_casualties,
    _rule_ambulance_shortage,
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