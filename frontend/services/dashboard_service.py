"""
dashboard_service.py

Service layer for the Dashboard page. This is the only module
frontend/app_pages/dashboard.py imports dashboard data from; the page
contains no direct backend imports and no SQL.

Layering:

    Dashboard Page (dashboard.py)
            |
            v
    frontend/services/dashboard_service.py
            |
            v
    backend/database/crud.py
            |
            v
    SQLite (bmerms.db)

This service provides the data required by the Dashboard's operational
overview components, including:

• KPI Summary
• Battlefield Evacuation Workflow
• Asset Inventory

Each public function is a read-only adapter over the backend data layer.
Existing CRUD functions are reused wherever possible and their results
are reshaped into the dictionaries and lists expected by the frontend.

No business logic is duplicated in this module.

Import bootstrap note:

Streamlit adds only the frontend/ directory to sys.path at runtime.
Because backend/ is a sibling of frontend/, the project root is added
to sys.path before importing backend modules.
""" 
 
from __future__ import annotations
 
import sys
from pathlib import Path
from typing import Optional
 
# --------------------------------------------------------------------------
# sys.path bootstrap (see module docstring above)
# --------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../DRDO
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
 
from backend.database import crud 
from backend.utils.constants import FACILITY_ORDER
  
# ==========================================================================
# 1. KPI SUMMARY
# ==========================================================================
 
def get_kpi_summary() -> dict:
    """
    Backs the 6 KPI cards.
 
    Wraps crud.get_dashboard_stats() and relabels the aggregate for the
    Dashboard's KPI row. "Total Casualties Processed" is backed by
    stats["total_casualties"]; there is no separate roster/troop-strength
    table in the schema, so this is the headline count available.
 
    Returns
    -------
    dict with keys:
        total_casualties_processed : int
        in_treatment               : int
        waiting_in_queue           : int
        recovered                  : int
        returned_to_duty           : int
        active_incidents           : int
        critical_casualties        : int
        average_waiting_minutes    : float
    """
    stats = crud.get_dashboard_stats()
    return {
        "total_casualties_processed": stats.get("total_casualties", 0),
        "in_treatment": stats.get("in_treatment", 0),
        "waiting_in_queue": stats.get("waiting_total", 0),
        "recovered": stats.get("recovered", 0),
        "returned_to_duty": stats.get("returned_to_duty", 0),
        "active_incidents": stats.get("active_incidents", 0),
        "critical_casualties": stats.get("critical_active", 0),
        "average_waiting_minutes": stats.get("average_waiting_minutes", 0.0),
    }
 
 
# ==========================================================================
# 2. EVACUATION WORKFLOW
# ==========================================================================
 
def get_evacuation_workflow() -> list[dict]:
    """
    Backs the Battlefield Evacuation Workflow strip's facility stages
    (RAP -> ADS -> HMV -> FDC). The static "Battlefield" and "Recovery"
    endpoint bookends are structural display elements defined in
    dashboard.py and are not data-backed.
 
    Wraps crud.get_all_facilities() and orders the result against
    backend.utils.constants.FACILITY_ORDER rather than relying on
    row/insertion order.
 
    Returns
    -------
    list[dict], one entry per facility, each:
        code             : str   e.g. "RAP"
        name             : str   e.g. "RAP" (short code, matches on-screen label)
        facility_name    : str   e.g. "Regimental Aid Post" (full name)
        occupied         : int
        capacity         : int
        occupancy_label  : str   e.g. "58 / 100"
    """
    facilities = crud.get_all_facilities()
    by_code = {f.facility_code: f for f in facilities}
 
    stages: list[dict] = []
    for code in FACILITY_ORDER:
        facility = by_code.get(code)
        if facility is None:
            continue
        stages.append(
            {
                "code": facility.facility_code,
                "name": facility.facility_code,
                "facility_name": facility.facility_name,
                "occupied": facility.occupied_beds,
                "capacity": facility.capacity,
                "occupancy_label": f"{facility.occupied_beds} / {facility.capacity}",
            }
        )
    return stages
 
 
# ==========================================================================
# 3. ASSET INVENTORY
# ==========================================================================
 
# Presentation-only icon lookup for the three known resource types. Not
# derived from the database.
_ASSET_ICON_MAP: dict[str, str] = {
    "Ambulances": "◈",
    "Helicopters": "△",
    "Medical Teams": "✚",
}
 
# (service key in crud.get_resource_availability_counts(), display label)
_ASSET_TYPES: list[tuple[str, str]] = [
    ("ambulances", "Ambulances"),
    ("helicopters", "Helicopters"),
    ("medical_teams", "Medical Teams"),
]
 
 
def get_asset_inventory() -> list[dict]:
    """
    Backs the Asset Inventory panel (Ambulances / Helicopters / Medical
    Teams).
 
    Wraps crud.get_resource_availability_counts(), which returns
    {available, total} per resource type. busy = total - available.
    maintenance is always reported as 0: no status in the schema is ever
    set to "Under Maintenance" by any simulation or CRUD code path, so
    this field reflects that current state honestly rather than
    fabricating a value.
 
    Returns
    -------
    list[dict], one entry per resource type, each:
        name        : str   e.g. "Ambulances"
        icon        : str
        available   : int
        busy        : int
        maintenance : int   (always 0, see note above)
        total       : int
    """
    counts = crud.get_resource_availability_counts()
 
    inventory: list[dict] = []
    for counts_key, label in _ASSET_TYPES:
        data = counts.get(counts_key, {"available": 0, "total": 0})
        available = data.get("available", 0)
        total = data.get("total", 0)
        busy = max(total - available, 0)
        inventory.append(
            {
                "name": label,
                "icon": _ASSET_ICON_MAP.get(label, "■"),
                "available": available,
                "busy": busy,
                "maintenance": 0,
                "total": total,
            }
        )
    return inventory 
 
 
