"""
facilities_mock_data.py
 
Single centralized mock data provider for the Facilities page. Every
widget on that page reads from these accessor functions — nothing is
hardcoded elsewhere on the page. When backend integration happens, only
this file needs to be replaced (same function signatures, real queries).
 
Facility identity/codes/capacities match the same 4 facilities already
established on the Dashboard and Simulation pages (RAP/ADS/HMV/FDC), for
consistency across the app. No "Level" field is included — the backend's    
Facility model has no such column, so it's omitted rather than invented.
"""
 
from __future__ import annotations
 
FACILITY_OVERVIEW: list[dict] = [
    {"name": "RAP", "facility_type": "Regimental Aid Post",
     "capacity": 120, "occupied": 54, "queue": 8, "avg_treatment": "2 hrs",
     "medical_teams": 4, "status": "Operational"},
    {"name": "ADS", "facility_type": "Advanced Dressing Station",
     "capacity": 100, "occupied": 82, "queue": 15, "avg_treatment": "4 hrs",
     "medical_teams": 3, "status": "High Load"},
    {"name": "HMV", "facility_type": "Hospital Medical Unit",
     "capacity": 300, "occupied": 294, "queue": 22, "avg_treatment": "4 days",
     "medical_teams": 6, "status": "Critical"},
    {"name": "FDC", "facility_type": "Field/Base Hospital",
     "capacity": 300, "occupied": 100, "queue": 2, "avg_treatment": "20 days",
     "medical_teams": 3, "status": "Operational"},
]
 
STATUS_COLOR: dict[str, str] = {"Operational": "primary", "Busy": "info", "High Load": "warning", "Critical": "danger"}
 
 
def get_facility_overview() -> list[dict]:
    """All facilities with beds/queue/status — the Operational Facility Overview table's source."""
    return FACILITY_OVERVIEW
 
 
def get_facility_detail(name: str) -> dict | None:
    """One facility's full record by name, or None if not found."""
    return next((f for f in FACILITY_OVERVIEW if f["name"] == name), None)
 
def get_kpi_summary() -> dict:
    """Aggregate counts for the top KPI row — derived from FACILITY_OVERVIEW, never a separate hardcoded set."""
    total = len(FACILITY_OVERVIEW)
    operational = sum(1 for f in FACILITY_OVERVIEW if f["status"] == "Operational")
    heavy_load = sum(1 for f in FACILITY_OVERVIEW if f["status"] in ("High Load", "Critical"))
    available_beds = sum(f["capacity"] - f["occupied"] for f in FACILITY_OVERVIEW)
    occupied_beds = sum(f["occupied"] for f in FACILITY_OVERVIEW)
    waiting_casualties = sum(f["queue"] for f in FACILITY_OVERVIEW)
    return {
        "total_facilities": total,
        "operational_facilities": operational,
        "heavy_load_facilities": heavy_load,
        "available_beds": available_beds,
        "occupied_beds": occupied_beds,
        "waiting_casualties": waiting_casualties,
    }