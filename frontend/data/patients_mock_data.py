"""
patients_mock_data.py

Temporary mock data provider for the Patients page. Field names in every
record below match the real backend dataclasses (models.py) exactly —
Casualty, Facility, Bed, QueueEntry, Treatment — so replacing this file
with real queries later requires no changes to patients.py's field
access.

No fields are invented beyond what those dataclasses declare. This file
is self-contained (its own facility/bed/queue/treatment mock rows) rather
than importing facilities_mock_data.py, since that provider uses a
different, page-local shape (name/facility_type) — not the real Facility
model's fields.
"""

from __future__ import annotations

MOCK_FACILITIES: list[dict] = [
    {"facility_id": 1, "facility_name": "RAP — Alpha 1", "facility_code": "RAP",
     "capacity": 120, "occupied_beds": 54, "available_beds": 66, "queue_length": 8,
     "treatment_duration_hours": 2.0, "facility_status": "Operational"},
    {"facility_id": 2, "facility_name": "ADS — Bravo 2", "facility_code": "ADS",
     "capacity": 100, "occupied_beds": 82, "available_beds": 18, "queue_length": 15,
     "treatment_duration_hours": 4.0, "facility_status": "High Load"},
    {"facility_id": 3, "facility_name": "HMV — Delta 9", "facility_code": "HMV",
     "capacity": 300, "occupied_beds": 294, "available_beds": 6, "queue_length": 22,
     "treatment_duration_hours": 96.0, "facility_status": "Critical"},
    {"facility_id": 4, "facility_name": "FDC — Foxtrot 3", "facility_code": "FDC",
     "capacity": 300, "occupied_beds": 100, "available_beds": 200, "queue_length": 2,
     "treatment_duration_hours": 480.0, "facility_status": "Operational"},
]

MOCK_BEDS: list[dict] = [
    {"bed_id": 101, "facility_id": 1, "bed_number": 14, "status": "Occupied",
     "current_casualty": "CAS-1001", "occupied_since": "08:40", "expected_release_time": "10:40"},
    {"bed_id": 205, "facility_id": 2, "bed_number": 22, "status": "Occupied",
     "current_casualty": "CAS-1002", "occupied_since": "07:55", "expected_release_time": "11:55"},
    {"bed_id": 309, "facility_id": 3, "bed_number": 61, "status": "Occupied",
     "current_casualty": "CAS-1003", "occupied_since": "06:10", "expected_release_time": None},
]

MOCK_QUEUE_ENTRIES: list[dict] = [
    {"queue_id": 1, "facility_id": 1, "casualty_id": "CAS-1004", "priority": "P2",
     "arrival_time": "09:05", "waiting_time": 18.0},
    {"queue_id": 2, "facility_id": 2, "casualty_id": "CAS-1005", "priority": "P1",
     "arrival_time": "08:50", "waiting_time": 42.0},
    {"queue_id": 3, "facility_id": 3, "casualty_id": "CAS-1006", "priority": "P1",
     "arrival_time": "07:30", "waiting_time": 65.0},
]

MOCK_CASUALTIES: list[dict] = [
    {"casualty_id": "CAS-1001", "incident_id": "INC-021", "battle_sector": "Bravo",
     "grid_x": 36.0, "grid_y": 5.0, "soldier_unit": "2 Rajputana Rifles", "rank": "Naik",
     "age": 27, "injury_type": "Blast Injury", "severity": "Critical", "priority": "P1",
     "arrival_time": "08:40", "assigned_facility": 1, "bed_id": 101, "queue_position": None,
     "evacuation_mode": "Air", "medical_officer": "Capt. R. Nair", "status": "In Treatment",
     "expected_recovery": "2026-07-14", "return_to_duty": None},
    {"casualty_id": "CAS-1002", "incident_id": "INC-021", "battle_sector": "Bravo",
     "grid_x": 35.5, "grid_y": 4.5, "soldier_unit": "2 Rajputana Rifles", "rank": "Sepoy",
     "age": 24, "injury_type": "Shrapnel Wound", "severity": "Serious", "priority": "P2",
     "arrival_time": "07:50", "assigned_facility": 2, "bed_id": 205, "queue_position": None,
     "evacuation_mode": "Ground", "medical_officer": "Lt. S. Verma", "status": "In Treatment",
     "expected_recovery": "2026-07-11", "return_to_duty": None},
    {"casualty_id": "CAS-1003", "incident_id": "INC-019", "battle_sector": "Charlie",
     "grid_x": 51.0, "grid_y": 3.0, "soldier_unit": "4 Grenadiers", "rank": "Havildar",
     "age": 31, "injury_type": "Gunshot Wound", "severity": "Critical", "priority": "P1",
     "arrival_time": "06:05", "assigned_facility": 3, "bed_id": 309, "queue_position": None,
     "evacuation_mode": "Air", "medical_officer": "Maj. A. Bose", "status": "In Treatment",
     "expected_recovery": None, "return_to_duty": None},
    {"casualty_id": "CAS-1004", "incident_id": "INC-021", "battle_sector": "Bravo",
     "grid_x": 36.2, "grid_y": 5.1, "soldier_unit": "2 Rajputana Rifles", "rank": "Sepoy",
     "age": 23, "injury_type": "Fracture", "severity": "Moderate", "priority": "P2",
     "arrival_time": "09:00", "assigned_facility": 1, "bed_id": None, "queue_position": 3,
     "evacuation_mode": "Ground", "medical_officer": None, "status": "Waiting",
     "expected_recovery": None, "return_to_duty": None},
    {"casualty_id": "CAS-1005", "incident_id": "INC-020", "battle_sector": "Delta",
     "grid_x": 66.0, "grid_y": 6.0, "soldier_unit": "9 Para", "rank": "Naik",
     "age": 29, "injury_type": "Blast Injury", "severity": "Serious", "priority": "P1",
     "arrival_time": "08:45", "assigned_facility": 2, "bed_id": None, "queue_position": 1,
     "evacuation_mode": "Air", "medical_officer": None, "status": "Waiting",
     "expected_recovery": None, "return_to_duty": None},
    {"casualty_id": "CAS-1006", "incident_id": "INC-019", "battle_sector": "Charlie",
     "grid_x": 50.8, "grid_y": 2.9, "soldier_unit": "4 Grenadiers", "rank": "Sepoy",
     "age": 22, "injury_type": "Gunshot Wound", "severity": "Critical", "priority": "P1",
     "arrival_time": "07:25", "assigned_facility": 3, "bed_id": None, "queue_position": 1,
     "evacuation_mode": "Ground", "medical_officer": None, "status": "Waiting",
     "expected_recovery": None, "return_to_duty": None},
    {"casualty_id": "CAS-0997", "incident_id": "INC-015", "battle_sector": "Alpha",
     "grid_x": 21.0, "grid_y": 3.0, "soldier_unit": "5 Assam Rifles", "rank": "Sepoy",
     "age": 26, "injury_type": "Fracture", "severity": "Moderate", "priority": "P3",
     "arrival_time": "yesterday 14:10", "assigned_facility": 4, "bed_id": None,
     "queue_position": None, "evacuation_mode": "Ground", "medical_officer": "Lt. K. Iyer",
     "status": "Recovered", "expected_recovery": "2026-07-08", "return_to_duty": None},
    {"casualty_id": "CAS-0982", "incident_id": "INC-012", "battle_sector": "Echo",
     "grid_x": 81.0, "grid_y": 4.0, "soldier_unit": "6 Gorkha Rifles", "rank": "Havildar",
     "age": 33, "injury_type": "Shrapnel Wound", "severity": "Mild", "priority": "P3",
     "arrival_time": "2 days ago", "assigned_facility": 4, "bed_id": None,
     "queue_position": None, "evacuation_mode": "Ground", "medical_officer": "Lt. K. Iyer",
     "status": "Returned to Duty", "expected_recovery": None, "return_to_duty": "2026-07-06"},
]

MOCK_TREATMENTS: list[dict] = [
    {"treatment_id": 5001, "casualty_id": "CAS-1001", "facility_id": 1,
     "treatment_start": "08:45", "treatment_end": None, "treatment_duration": None,
     "current_status": "In Progress"},
    {"treatment_id": 5002, "casualty_id": "CAS-1002", "facility_id": 2,
     "treatment_start": "08:00", "treatment_end": None, "treatment_duration": None,
     "current_status": "In Progress"},
    {"treatment_id": 5003, "casualty_id": "CAS-1003", "facility_id": 3,
     "treatment_start": "06:15", "treatment_end": None, "treatment_duration": None,
     "current_status": "In Progress"},
    {"treatment_id": 4991, "casualty_id": "CAS-0997", "facility_id": 4,
     "treatment_start": "yesterday 14:20", "treatment_end": "yesterday 16:05",
     "treatment_duration": 1.75, "current_status": "Completed"},
    {"treatment_id": 4980, "casualty_id": "CAS-0982", "facility_id": 4,
     "treatment_start": "2 days ago", "treatment_end": "2 days ago", "treatment_duration": 3.0,
     "current_status": "Completed"},
]


def get_all_casualties() -> list[dict]:
    return MOCK_CASUALTIES


def get_facility_name(facility_id: int | None) -> str | None:
    if facility_id is None:
        return None
    return next((f["facility_name"] for f in MOCK_FACILITIES if f["facility_id"] == facility_id), None)


def get_all_facility_names() -> list[str]:
    return [f["facility_name"] for f in MOCK_FACILITIES]


def get_bed_number(bed_id: int | None) -> int | None:
    if bed_id is None:
        return None
    return next((b["bed_number"] for b in MOCK_BEDS if b["bed_id"] == bed_id), None)


def get_queue_entry(casualty_id: str) -> dict | None:
    return next((q for q in MOCK_QUEUE_ENTRIES if q["casualty_id"] == casualty_id), None)


def get_latest_treatment(casualty_id: str) -> dict | None:
    """The in-progress treatment (treatment_end is None) if one exists, else the most recent by treatment_start."""
    candidates = [t for t in MOCK_TREATMENTS if t["casualty_id"] == casualty_id]
    if not candidates:
        return None
    in_progress = next((t for t in candidates if t["treatment_end"] is None), None)
    return in_progress if in_progress else candidates[-1]