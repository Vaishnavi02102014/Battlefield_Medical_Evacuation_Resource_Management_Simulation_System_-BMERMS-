"""
ai_service.py

Service layer for AI Tactical Recommendation widgets. This is the ONLY
module frontend pages should import AI recommendation data from — pages
themselves must contain no direct backend.ai imports, mirroring the
pattern established by dashboard_service.py, facilities_service.py,
resources_service.py, and patients_service.py.

Required layering:

    Simulation Page (simulation.py) / Dashboard Page
            |
            v
    frontend/services/ai_service.py   <- this file
            |
            v
    backend/ai/recommendation_engine.py  (+ facilities_service /
    resources_service / patients_service, reused rather than
    re-deriving their data via crud.py directly)
            |
            v
    SQLite (bmerms.db), via the three services above

backend/ai/recommendation_engine.py already returns exactly the shape
this service passes straight through: {"recommendation", "reason",
"expected_benefit", "confidence"}. It is also already safe to call even
if the .pkl model files don't exist — _safe_predictions() and
_safe_resource_assessment() inside recommendation_engine.py both catch
failures internally and fall back to neutral values — so no additional
try/except wrapper is added here, consistent with every other service
in this codebase being a thin, unwrapped passthrough.

No module-level caching / no st.session_state writes: every call
re-derives simulation_state from live data, same reset-architecture
guarantee as every other service.
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
    capacity = facility.get("capacity") or 0
    occupied = facility.get("occupied") or 0
    return (occupied / capacity * 100) if capacity else 0.0

def _facility_summary(facilities: list) -> dict:
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
    Assembles the 5-key simulation_state dict resource_assessment.py's
    _extract_signals() reads (occupancy_rate, queue_length,
    critical_casualties, available_medical_teams,
    available_helicopters), sourced entirely from the three existing
    services — no crud.py calls here, no data derivation duplicated
    from what those services already correctly compute.
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

    Returns
    -------
    dict: {"recommendation": str, "reason": str, "expected_benefit": str, "confidence": float}
    """
    simulation_state = _build_simulation_state()
    return generate_recommendations(simulation_state)