"""
ai_service.py
 
Service layer for AI-backed widgets (AI Tactical Recommendation / AI
Model Performance). This is the only module frontend pages import AI
data from; pages contain no direct backend.ai imports.
 
Layering:
 
    Simulation Page / Dashboard Page / Analytics Page
            |
            v
    frontend/services/ai_service.py   <- this file
            |
            v
    backend/ai/recommendation_engine.py, backend/ai/model_loader.py
    (+ facilities_service / resources_service / patients_service,
    reused rather than re-deriving their data via crud.py directly)
            |
            v
    SQLite (bmerms.db), via the three services above, and
    backend/ai/metrics.json for model performance
 
backend.ai.recommendation_engine.generate_recommendations() returns the
shape this service passes through directly: {"recommendation", "reason",
"expected_benefit", "confidence"}. It handles its own missing-model
fallback internally, so no additional error handling is layered on top
here. get_model_performance_metrics() wraps
backend.ai.model_loader.load_metrics() and reports "Not Trained" per
field when metrics.json is unavailable.
 
Every call re-derives its data from live sources; no module-level
caching and no st.session_state writes occur in this file.
"""
 
from __future__ import annotations
 
import sys
from pathlib import Path
 
# --------------------------------------------------------------------------
# sys.path bootstrap (same pattern as the other four services)
# --------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../DRDO
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
 
from backend.ai.recommendation_engine import generate_recommendations  # noqa: E402
 
from services import facilities_service  # noqa: E402
from services import resources_service  # noqa: E402
from services import patients_service  # noqa: E402
 
def _facility_occupancy_pct(facility: dict) -> float:
    """Occupancy percentage for one facility record (0 if capacity is 0)."""
    capacity = facility.get("capacity") or 0
    occupied = facility.get("occupied") or 0
    return (occupied / capacity * 100) if capacity else 0.0
 
def _facility_summary(facilities: list) -> dict:
    """
    Identifies the highest/lowest occupancy and highest/lowest queue
    facility from a list of facility records, for inclusion in the
    simulation state passed to the recommendation engine.
 
    Returns a dict of four keys (highest_load_facility,
    lowest_load_facility, highest_queue_facility, lowest_queue_facility),
    each None if the facilities list is empty.
    """
    if not facilities:
        return {
            "highest_load_facility": None,
            "lowest_load_facility": None,
            "highest_queue_facility": None,
            "lowest_queue_facility": None,
        }
 
    return {
        "highest_load_facility": max(
            facilities,
            key=_facility_occupancy_pct,
        ),
        "lowest_load_facility": min(
            facilities,
            key=_facility_occupancy_pct,
        ),
        "highest_queue_facility": max(
            facilities,
            key=lambda f: f.get("queue") or 0,
        ),
        "lowest_queue_facility": min(
            facilities,
            key=lambda f: f.get("queue") or 0,
        ),
    }
 
def _build_simulation_state() -> dict:
    """
    Assembles the simulation_state dict that
    recommendation_engine._extract_signals() reads (occupancy_rate,
    queue_length, critical_casualties, available_medical_teams,
    available_helicopters, plus facility-level detail), sourced entirely
    through facilities_service, resources_service, and patients_service
    rather than querying the database directly.
    """
    facility_kpis = facilities_service.get_kpi_summary()
    total_beds = facility_kpis.get("available_beds", 0) + facility_kpis.get("occupied_beds", 0)
    occupancy_rate = (facility_kpis.get("occupied_beds", 0) / total_beds * 100) if total_beds else 0.0
 
    fleet = resources_service.get_fleet_status()
    teams = resources_service.get_medical_team_status()
 
    critical_casualties = sum(
        1 for casualty in patients_service.get_all_casualties()
        if casualty.get("severity") == "Critical"
    )
    facilities = facilities_service.get_facility_overview()
 
    return {
        "occupancy_rate": occupancy_rate,
        "queue_length": facility_kpis.get("waiting_casualties", 0),
        "critical_casualties": critical_casualties,
        "available_medical_teams": teams.get("available_teams", 0),
        "available_helicopters": fleet.get("helicopters", {}).get("available", 0),
        "available_ambulances": fleet.get("ambulances", {}).get("available", 0),
        "facilities": facilities,
        **_facility_summary(facilities),
    }
 
 
def get_ai_recommendation() -> dict:
    """
    Backs the AI Tactical Recommendation panel.
 
    Builds the current simulation state and passes it to
    backend.ai.recommendation_engine.generate_recommendations().
 
    Returns
    -------
    dict: {"recommendation": str, "reason": str, "expected_benefit": str, "confidence": float}
    """
    simulation_state = _build_simulation_state()
    return generate_recommendations(simulation_state)