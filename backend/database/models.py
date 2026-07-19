"""
models.py
 
Plain dataclasses representing rows returned from the database.
 
IMPORTANT: These are NOT an ORM. They carry no query or persistence behaviour.
Their only job is to give the rest of the codebase typed, named access to
row data instead of passing raw sqlite3.Row / tuple objects around.
 
Each dataclass has a `from_row` classmethod that builds an instance from a
sqlite3.Row (which supports dict-style key access when the connection's
row_factory is set to sqlite3.Row — see database/db.py).
"""
 
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import sqlite3
 
 
@dataclass
class Facility:
    facility_id: int
    facility_name: str
    facility_code: str
    capacity: int
    occupied_beds: int
    available_beds: int
    queue_length: int
    treatment_duration_hours: float
    facility_status: str
    grid_x: float
    grid_y: float
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Facility":
        return cls(**{k: row[k] for k in row.keys()})
 
    @property
    def utilization_percent(self) -> float:
        if self.capacity == 0:
            return 0.0
        return round((self.occupied_beds / self.capacity) * 100, 1)
 
 
@dataclass
class Bed:
    bed_id: int
    facility_id: int
    bed_number: int
    status: str                              # "Available" | "Occupied"
    current_casualty: Optional[str]
    occupied_since: Optional[str]
    expected_release_time: Optional[str]
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Bed":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Scenario:
    scenario_id: int
    scenario_name: str
    start_time: str
    status: str
    description: Optional[str]
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Scenario":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Operation:
    operation_id: int
    scenario_id: int
    operation_name: str
    start_time: str
    end_time: Optional[str]
    status: str
    description: Optional[str]
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Operation":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Incident:
    incident_id: str
    operation_id: int
    incident_time: str
    event_type: str
    battle_sector: str
    grid_x: float
    grid_y: float
    number_of_casualties: int
    status: str
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Incident":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Casualty:
    casualty_id: str
    incident_id: str
    battle_sector: str
    grid_x: float
    grid_y: float
    soldier_unit: str
    rank: str
    age: int
    injury_type: str
    severity: str
    priority: str
    arrival_time: str
    assigned_facility: Optional[int]
    bed_id: Optional[int]
    queue_position: Optional[int]
    evacuation_mode: Optional[str]   # None for casualties still "Awaiting Transport" in the queue
    evacuation_arrival_time: Optional[str]
    medical_officer: Optional[str]
    status: str
    expected_recovery: Optional[str]
    return_to_duty: Optional[str]
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Casualty":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Treatment:
    treatment_id: int
    casualty_id: str
    facility_id: int
    treatment_start: str
    treatment_end: Optional[str]
    treatment_duration: float
    current_status: str
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Treatment":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class QueueEntry:
    queue_id: int
    facility_id: int
    casualty_id: str
    priority: str
    arrival_time: str
    waiting_time: Optional[float]
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "QueueEntry":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Ambulance:
    ambulance_id: int
    call_sign: str
    status: str
    assigned_casualty: Optional[str]
    release_time: Optional[str]
    grid_x: float
    grid_y: float
    dispatch_time: Optional[str] = None      # Phase 6A: when this vehicle's current trip departed
    origin_grid_x: Optional[float] = None    # Phase 6A: where this vehicle's current trip departed from
    origin_grid_y: Optional[float] = None
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Ambulance":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class Helicopter:
    helicopter_id: int
    call_sign: str
    status: str
    assigned_casualty: Optional[str]
    release_time: Optional[str]
    grid_x: float
    grid_y: float
    dispatch_time: Optional[str] = None      # Phase 6A: when this vehicle's current trip departed
    origin_grid_x: Optional[float] = None    # Phase 6A: where this vehicle's current trip departed from
    origin_grid_y: Optional[float] = None
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Helicopter":
        return cls(**{k: row[k] for k in row.keys()})
 
 
@dataclass
class MedicalTeam:
    team_id: int
    team_name: str
    status: str
    assigned_facility: Optional[int]
    specialization: str
 
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MedicalTeam":
        return cls(**{k: row[k] for k in row.keys()})