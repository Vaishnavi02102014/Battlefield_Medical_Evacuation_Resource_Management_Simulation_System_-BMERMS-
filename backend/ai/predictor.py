"""
predictor.py
 
Prediction-serving layer for the BMERMS AI module.
 
Wires together feature_builder.py (simulation_state -> model-ready
feature dict) and model_loader.py (lazy, cached loading of the trained
sklearn pipelines) to produce predictions from a live simulation state.
 
Pipeline for every prediction:
 
    simulation_state (dict)
          |
          v
    feature_builder.build_*_features(simulation_state)  -> feature dict
          |
          v
    pandas.DataFrame([feature dict])                    -> single-row DataFrame
          |
          v
    model.predict(...) / model.predict_proba(...)        -> prediction (+confidence)
 
This module does not import database, simulation engine, or frontend
code. It only depends on model_loader.py, feature_builder.py, and
pandas.
"""
 
from typing import Any, Dict
 
import pandas as pd
 
from .feature_builder import (
    build_duty_features,
    build_recovery_features,
    build_transfer_features,
)
from .model_loader import load_duty_model, load_recovery_model, load_transfer_model
 
CLASS_LABELS = {0: "No", 1: "Yes"}

def _build_dataframe(features: Dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([features])
 
def _load_model_safe(loader, model_name: str):
    """Load a model via model_loader, converting any loading failure
    into a clear, descriptive RuntimeError rather than letting a raw
    FileNotFoundError (or other unexpected error) propagate."""
    try:
        return loader()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Could not load '{model_name}': {exc}. "
            f"Ensure train_models.py has been run to generate the model files."
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Unexpected error while loading '{model_name}': {exc}"
        ) from exc
 
 
def _predict_classification(model, features: Dict[str, Any]) -> Dict[str, Any]:
    """Runs a classifier on a single-row feature dict and returns the
    decoded label plus confidence (max predicted-class probability, as
    a percentage)."""
    X = _build_dataframe(features)
    prediction = model.predict(X)[0]
    probabilities = model.predict_proba(X)[0]
    confidence = max(0.0, min(100.0, round(max(probabilities) * 100, 2)))
    label = CLASS_LABELS.get(int(prediction), str(prediction))
    return {"label": label, "confidence": float(confidence)}
 
 
def predict_transfer_requirement(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict whether a transfer is required for the given simulation
    state.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See feature_builder.py for the recognized keys.
 
    Returns
    -------
    dict
        {
            "transfer_required": "Yes" | "No",
            "transfer_confidence": float  # percentage, 0-100
        }
    """
    model = _load_model_safe(load_transfer_model, "transfer_model")
    features = build_transfer_features(simulation_state)
    result = _predict_classification(model, features)
    return {
        "transfer_required": result["label"],
        "transfer_confidence": result["confidence"],
    }
 
 
def predict_recovery_days(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict the expected recovery duration (in days) for the given
    simulation state.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See feature_builder.py for the recognized keys.
 
    Returns
    -------
    dict
        {
            "predicted_recovery_days": float
        }
        (Regression output only - no confidence score is produced for
        regression predictions.)
    """
    model = _load_model_safe(load_recovery_model, "recovery_model")
    features = build_recovery_features(simulation_state)
    X = _build_dataframe(features)
    prediction = max(0.0, float(model.predict(X)[0]))

    return {
        "predicted_recovery_days":
            round(prediction, 1)
    }
 
 
def predict_return_to_duty(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Predict whether the casualty is expected to return to duty for the
    given simulation state.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See feature_builder.py for the recognized keys.
 
    Returns
    -------
    dict
        {
            "return_to_duty": "Yes" | "No",
            "duty_confidence": float  # percentage, 0-100
        }
    """
    model = _load_model_safe(load_duty_model, "duty_model")
    features = build_duty_features(simulation_state)
    result = _predict_classification(model, features)
    return {
        "return_to_duty": result["label"],
        "duty_confidence": result["confidence"],
    }
 
 
def generate_predictions(simulation_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run all three models against a single simulation state and return a
    combined prediction summary.
 
    Parameters
    ----------
    simulation_state : dict
        Plain dictionary describing the current casualty/facility state.
        See feature_builder.py for the recognized keys.
 
    Returns
    -------
    dict
        {
            "transfer_required": "Yes" | "No",
            "transfer_confidence": float,
            "predicted_recovery_days": float,
            "return_to_duty": "Yes" | "No",
            "duty_confidence": float
        }
 
    Raises
    ------
    RuntimeError
        If any of the three model files cannot be loaded (e.g. because
        train_models.py has not been run yet).
    """
    try:
        transfer_result = predict_transfer_requirement(simulation_state)
    except Exception:
        transfer_result = {
            "transfer_required": "Unknown",
            "transfer_confidence": 0.0,
        }

    try:
        recovery_result = predict_recovery_days(simulation_state)
    except Exception:
        recovery_result = {
            "predicted_recovery_days": 0.0,
        }

    try:
        duty_result = predict_return_to_duty(simulation_state)
    except Exception:
        duty_result = {
            "return_to_duty": "Unknown",
            "duty_confidence": 0.0,
        }
 
    return {
        "transfer_required": transfer_result["transfer_required"],
        "transfer_confidence": transfer_result["transfer_confidence"],
        "predicted_recovery_days": recovery_result["predicted_recovery_days"],
        "return_to_duty": duty_result["return_to_duty"],
        "duty_confidence": duty_result["duty_confidence"],
    }